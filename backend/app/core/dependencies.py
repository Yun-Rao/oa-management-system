import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("未登录")
    try:
        user_id = decode_access_token(credentials.credentials)
        parsed_id = uuid.UUID(user_id)
    except (jwt.PyJWTError, KeyError, ValueError):
        raise UnauthorizedError("Token 无效或已过期")
    user = await UserRepository(db).get_by_id(parsed_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("用户不存在或已被禁用")
    return user


def require_permission(permission_code: str):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        owned = {p.code for role in current_user.roles for p in role.permissions}
        if permission_code not in owned:
            raise ForbiddenError("无权限执行此操作")
        return current_user

    return checker
