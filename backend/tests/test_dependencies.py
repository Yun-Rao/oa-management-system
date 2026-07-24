import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.core.dependencies import get_current_user, require_permission
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import create_access_token
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from tests.conftest import make_user


def creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_no_token_raises_401(db):
    with pytest.raises(UnauthorizedError):
        await get_current_user(credentials=None, db=db)


async def test_bad_token_raises_401(db):
    with pytest.raises(UnauthorizedError):
        await get_current_user(credentials=creds("not-a-token"), db=db)


async def test_token_with_malformed_sub_raises_401(db):
    with pytest.raises(UnauthorizedError):
        await get_current_user(
            credentials=creds(create_access_token("not-a-uuid")), db=db
        )


async def test_valid_token_returns_user(db):
    user = await make_user(db)
    result = await get_current_user(
        credentials=creds(create_access_token(str(user.id))), db=db
    )
    assert result.id == user.id


async def test_disabled_user_raises_401(db):
    user = await make_user(db, is_active=False)
    with pytest.raises(UnauthorizedError):
        await get_current_user(
            credentials=creds(create_access_token(str(user.id))), db=db
        )


def build_user_with_perms(codes: list[str]) -> User:
    perms = [Permission(code=c, name=c) for c in codes]
    role = Role(code="r1", name="r1", permissions=perms)
    return User(email="a@b.c", name="n", hashed_password="h", roles=[role])


async def test_require_permission_allows():
    checker = require_permission("user:create")
    user = build_user_with_perms(["user:create"])
    assert await checker(current_user=user) is user


async def test_require_permission_denies():
    checker = require_permission("user:create")
    with pytest.raises(ForbiddenError):
        await checker(current_user=build_user_with_perms([]))
