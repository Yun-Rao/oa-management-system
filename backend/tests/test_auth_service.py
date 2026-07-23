import jwt
import pytest

from app.core.config import settings
from app.core.exceptions import InvalidCredentialsError
from app.services.auth_service import AuthService
from tests.conftest import make_user


async def test_login_success(db):
    user = await make_user(db, email="u@x.com", password="Secret123")
    resp = await AuthService(db).login("u@x.com", "Secret123")
    assert resp.token_type == "bearer"
    assert resp.expires_in == settings.JWT_EXPIRE_MINUTES * 60
    payload = jwt.decode(
        resp.access_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    assert payload["sub"] == str(user.id)


async def test_login_wrong_password(db):
    await make_user(db, email="u@x.com", password="Secret123")
    with pytest.raises(InvalidCredentialsError):
        await AuthService(db).login("u@x.com", "wrong")


async def test_login_unknown_email(db):
    with pytest.raises(InvalidCredentialsError):
        await AuthService(db).login("nobody@x.com", "Secret123")


async def test_login_disabled_user(db):
    await make_user(db, email="u@x.com", password="Secret123", is_active=False)
    with pytest.raises(InvalidCredentialsError):
        await AuthService(db).login("u@x.com", "Secret123")


async def test_change_password(db):
    user = await make_user(db, email="u@x.com", password="Old12345")
    service = AuthService(db)
    await service.change_password(user.id, "Old12345", "New12345")
    resp = await service.login("u@x.com", "New12345")
    assert resp.access_token


async def test_change_password_wrong_old(db):
    user = await make_user(db, email="u@x.com", password="Old12345")
    with pytest.raises(InvalidCredentialsError):
        await AuthService(db).change_password(user.id, "wrong", "New12345")
