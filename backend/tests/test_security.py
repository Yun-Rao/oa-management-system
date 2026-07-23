import time

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_is_not_plaintext():
    hashed = hash_password("Secret123")
    assert hashed != "Secret123"
    assert hashed.startswith("$2b$")


def test_verify_password():
    hashed = hash_password("Secret123")
    assert verify_password("Secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_access_token_roundtrip():
    token = create_access_token("some-user-id")
    assert decode_access_token(token) == "some-user-id"


def test_decode_rejects_tampered_token():
    token = create_access_token("some-user-id")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token + "tampered")


def test_decode_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(settings, "JWT_EXPIRE_MINUTES", -1)
    token = create_access_token("some-user-id")
    time.sleep(1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)
