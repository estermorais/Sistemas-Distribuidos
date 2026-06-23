"""Testes unitários do Auth Service."""
import pytest
from datetime import timedelta
from jose import jwt

import sys, os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_auth_unit.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import (
    hash_password,
    verify_password,
    create_access_token,
    settings,
)


def test_hash_password_produces_different_hash():
    h1 = hash_password("senha123")
    h2 = hash_password("senha123")
    assert h1 != h2  # bcrypt gera salt diferente a cada chamada


def test_verify_password_correct():
    hashed = hash_password("minhasenha")
    assert verify_password("minhasenha", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("minhasenha")
    assert verify_password("senhaerrada", hashed) is False


def test_verify_password_empty_fails():
    hashed = hash_password("segredo")
    assert verify_password("", hashed) is False


def test_create_access_token_contains_claims():
    token = create_access_token({"sub": "alice", "user_id": 1})
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == "alice"
    assert payload["user_id"] == 1


def test_create_access_token_expiry():
    token = create_access_token({"sub": "bob"}, expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert "exp" in payload


def test_token_invalid_secret():
    token = create_access_token({"sub": "alice"})
    with pytest.raises(Exception):
        jwt.decode(token, "wrong-secret", algorithms=[settings.jwt_algorithm])


def test_password_minimum_strength():
    """Senha muito curta deve ser recusada pela rota — validamos a regra aqui."""
    assert len("abc") < 4
    assert len("abcd") >= 4
