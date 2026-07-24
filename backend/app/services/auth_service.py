import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import InvalidCredentialsError
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse

_GENERIC_FAIL = "邮箱或密码错误"
# 预生成 dummy hash,使"用户不存在"路径也执行一次 bcrypt 校验,
# 消除计时侧信道导致的用户枚举。
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class AuthService:
    def __init__(self, db: AsyncSession):
        self.users = UserRepository(db)

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self.users.get_by_email(email)
        if user is None:
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentialsError(_GENERIC_FAIL)
        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError(_GENERIC_FAIL)
        if not user.is_active:
            raise InvalidCredentialsError(_GENERIC_FAIL)
        return TokenResponse(
            access_token=create_access_token(str(user.id)),
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        )

    async def change_password(
        self, user_id: uuid.UUID, old_password: str, new_password: str
    ) -> None:
        user = await self.users.get_by_id(user_id)
        if user is None or not verify_password(old_password, user.hashed_password):
            raise InvalidCredentialsError("旧密码错误")
        user.hashed_password = hash_password(new_password)
        await self.users.save(user)
