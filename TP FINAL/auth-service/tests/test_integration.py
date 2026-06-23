"""Testes de integração do Auth Service usando banco SQLite em memória."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys, os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_auth.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app, Base, get_db, User, hash_password

TEST_DB_URL = "sqlite:///./test_auth.db"
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


@pytest.fixture(autouse=True)
def clean_db():
    yield
    # Limpa usuários após cada teste
    db = TestSession()
    db.query(User).delete()
    db.commit()
    db.close()


class TestRegister:
    def test_register_success(self):
        res = client.post("/register", json={"username": "alice", "password": "alice123"})
        assert res.status_code == 201
        body = res.json()
        assert body["username"] == "alice"
        assert "id" in body

    def test_register_duplicate_username(self):
        client.post("/register", json={"username": "alice", "password": "alice123"})
        res = client.post("/register", json={"username": "alice", "password": "outra"})
        assert res.status_code == 400
        assert "já cadastrado" in res.json()["detail"]

    def test_register_short_password(self):
        res = client.post("/register", json={"username": "bob", "password": "abc"})
        assert res.status_code == 400

    def test_register_with_email(self):
        res = client.post("/register", json={"username": "carol", "password": "carol123", "email": "carol@example.com"})
        assert res.status_code == 201
        assert res.json()["email"] == "carol@example.com"


class TestLogin:
    def setup_method(self):
        db = TestSession()
        user = User(username="testuser", hashed_password=hash_password("senha123"), is_active=True)
        db.add(user)
        db.commit()
        db.close()

    def test_login_success(self):
        res = client.post("/login", data={"username": "testuser", "password": "senha123"})
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["username"] == "testuser"

    def test_login_wrong_password(self):
        res = client.post("/login", data={"username": "testuser", "password": "errada"})
        assert res.status_code == 401

    def test_login_unknown_user(self):
        res = client.post("/login", data={"username": "naoexiste", "password": "qualquer"})
        assert res.status_code == 401


class TestProtectedRoutes:
    def _get_token(self):
        client.post("/register", json={"username": "dave", "password": "dave123"})
        res = client.post("/login", data={"username": "dave", "password": "dave123"})
        return res.json()["access_token"]

    def test_me_with_valid_token(self):
        token = self._get_token()
        res = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["username"] == "dave"

    def test_me_without_token(self):
        res = client.get("/me")
        assert res.status_code == 401

    def test_verify_token(self):
        token = self._get_token()
        res = client.get("/verify", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["valid"] is True

    def test_list_users(self):
        token = self._get_token()
        res = client.get("/users", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)
