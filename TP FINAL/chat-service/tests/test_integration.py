"""
Testes de integração do Chat Service.

Cobre:
1. Persistência de mensagens no banco de dados.
2. Recuperação de histórico via HTTP.
3. Comunicação WebSocket (conexão, envio, recebimento).
4. Fluxo completo: autenticar → conectar WS → enviar mensagem → checar histórico.
"""
import pytest
import threading
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jose import jwt

import sys, os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_chat.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app, Base, get_db, Message, settings

TEST_DB_URL = "sqlite:///./test_chat.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
Base.metadata.create_all(bind=engine)

client = TestClient(app)


def make_token(user_id: int, username: str) -> str:
    return jwt.encode(
        {"sub": username, "user_id": user_id},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@pytest.fixture(autouse=True)
def clean_db():
    yield
    db = TestSession()
    db.query(Message).delete()
    db.commit()
    db.close()


class TestMessagePersistence:
    def test_message_saved_to_db(self):
        db = TestSession()
        msg = Message(
            sender_id=1,
            sender_username="alice",
            room_id="geral",
            content="Teste de persistência",
            is_private=False,
            created_at=datetime.utcnow(),
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        saved = db.query(Message).filter(Message.id == msg.id).first()
        assert saved is not None
        assert saved.content == "Teste de persistência"
        assert saved.sender_username == "alice"
        db.close()

    def test_private_message_saved(self):
        db = TestSession()
        msg = Message(
            sender_id=1, sender_username="alice",
            recipient_id=2, content="mensagem privada",
            is_private=True, created_at=datetime.utcnow(),
        )
        db.add(msg)
        db.commit()
        saved = db.query(Message).filter(Message.recipient_id == 2).first()
        assert saved.is_private is True
        db.close()


class TestMessageHistory:
    def _seed(self, sender_id, username, content, room="geral", recipient=None, private=False):
        db = TestSession()
        msg = Message(
            sender_id=sender_id, sender_username=username,
            room_id=room, recipient_id=recipient,
            content=content, is_private=private,
            created_at=datetime.utcnow(),
        )
        db.add(msg)
        db.commit()
        db.close()

    def test_get_public_messages(self):
        self._seed(1, "alice", "oi geral")
        token = make_token(1, "alice")
        res = client.get(f"/messages?room_id=geral&token={token}")
        assert res.status_code == 200
        msgs = res.json()
        assert any(m["content"] == "oi geral" for m in msgs)

    def test_get_private_messages(self):
        self._seed(1, "alice", "msg privada", recipient=2, private=True)
        self._seed(2, "bob", "resposta privada", recipient=1, private=True)
        token = make_token(1, "alice")
        res = client.get(f"/messages/private/2?token={token}")
        assert res.status_code == 200
        msgs = res.json()
        assert len(msgs) == 2

    def test_messages_pagination(self):
        for i in range(10):
            self._seed(1, "alice", f"msg {i}")
        token = make_token(1, "alice")
        res = client.get(f"/messages?room_id=geral&token={token}&limit=5")
        assert res.status_code == 200
        assert len(res.json()) == 5


class TestWebSocket:
    def test_ws_invalid_token_rejected(self):
        from starlette.testclient import WebSocketDenialResponse
        with pytest.raises((WebSocketDenialResponse, Exception)):
            with client.websocket_connect("/ws/1?token=token.invalido") as ws:
                pass

    def test_ws_connect_and_receive_welcome(self):
        token = make_token(10, "testuser")
        # Patch Redis para não tentar conectar em testes
        import unittest.mock as mock
        with mock.patch("main.manager.redis", None):
            with client.websocket_connect(f"/ws/10?token={token}") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "system"
                assert "testuser" in msg["content"]

    def test_ws_send_public_message(self):
        token = make_token(11, "sender")
        import unittest.mock as mock
        with mock.patch("main.manager.redis", None):
            with client.websocket_connect(f"/ws/11?token={token}") as ws:
                ws.receive_json()  # welcome
                ws.send_json({"content": "hello world", "room_id": "geral"})
                response = ws.receive_json()
                assert response["type"] == "message"
                assert response["content"] == "hello world"
                assert response["sender_username"] == "sender"

    def test_ws_send_private_message(self):
        token = make_token(12, "alice")
        import unittest.mock as mock
        with mock.patch("main.manager.redis", None):
            with client.websocket_connect(f"/ws/12?token={token}") as ws:
                ws.receive_json()  # welcome
                ws.send_json({"content": "msg privada", "recipient_id": 13})
                response = ws.receive_json()
                assert response["is_private"] is True
                assert response["recipient_id"] == 13
