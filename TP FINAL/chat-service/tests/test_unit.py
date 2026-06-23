"""Testes unitários do Chat Service."""
import pytest
from datetime import datetime

import sys, os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_chat_unit.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import decode_token, settings
from jose import jwt


def make_token(user_id: int, username: str) -> str:
    return jwt.encode(
        {"sub": username, "user_id": user_id},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def test_decode_valid_token():
    token = make_token(42, "alice")
    payload = decode_token(token)
    assert payload["user_id"] == 42
    assert payload["sub"] == "alice"


def test_decode_invalid_token_raises():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        decode_token("token.invalido.aqui")
    assert exc_info.value.status_code == 401


def test_decode_wrong_secret_raises():
    from fastapi import HTTPException
    bad_token = jwt.encode({"sub": "hacker", "user_id": 99}, "wrong-secret", algorithm="HS256")
    with pytest.raises(HTTPException):
        decode_token(bad_token)


def test_message_private_flag():
    """Mensagem com recipient_id deve ser marcada como privada."""
    from main import Message
    msg = Message(
        sender_id=1,
        sender_username="alice",
        recipient_id=2,
        content="oi",
        is_private=True,
        created_at=datetime.utcnow(),
    )
    assert msg.is_private is True


def test_message_public_flag():
    from main import Message
    msg = Message(
        sender_id=1,
        sender_username="alice",
        room_id="geral",
        content="oi geral",
        is_private=False,
        created_at=datetime.utcnow(),
    )
    assert msg.is_private is False
