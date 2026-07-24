import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password
from app.models.user import User
from app.repositories.department_repository import DepartmentRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserOrgUpdate, UserUpdate


class UserService:
    def __init__(self, db: AsyncSession):
        self.users = UserRepository(db)
        self.roles = RoleRepository(db)
        self.departments = DepartmentRepository(db)

    async def create_user(self, data: UserCreate) -> User:
        if await self.users.get_by_email(data.email):
            raise ConflictError("邮箱已被使用")
        user = User(
            email=data.email,
            name=data.name,
            hashed_password=hash_password(data.password),
        )
        return await self.users.create(user)

    async def list_users(
        self, keyword: str | None, page: int, page_size: int
    ) -> tuple[list[User], int]:
        return await self.users.list(keyword, (page - 1) * page_size, page_size)

    async def update_user(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        if data.email and data.email != user.email:
            if await self.users.get_by_email(data.email):
                raise ConflictError("邮箱已被使用")
            user.email = data.email
        if data.name:
            user.name = data.name
        return await self.users.save(user)

    async def set_status(self, user_id: uuid.UUID, is_active: bool) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        user.is_active = is_active
        return await self.users.save(user)

    async def assign_roles(
        self, user_id: uuid.UUID, role_codes: list[str], operator: User
    ) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        roles = await self.roles.get_by_codes(role_codes)
        missing = set(role_codes) - {r.code for r in roles}
        if missing:
            raise NotFoundError(f"角色不存在: {', '.join(sorted(missing))}")
        if user.id == operator.id:
            operator_codes = {r.code for r in operator.roles}
            new_codes = {r.code for r in roles}
            if "admin" in operator_codes and "admin" not in new_codes:
                raise ConflictError("不能移除自己的 admin 角色")
        user.roles = roles
        return await self.users.save(user)

    async def set_org(self, user_id: uuid.UUID, data: UserOrgUpdate) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        new_dept = (
            data.department_id
            if "department_id" in data.model_fields_set
            else user.department_id
        )
        new_mgr = (
            data.manager_id
            if "manager_id" in data.model_fields_set
            else user.manager_id
        )
        if new_dept is not None:
            dept = await self.departments.get_by_id(new_dept)
            if dept is None:
                raise NotFoundError("部门不存在")
        if new_mgr is not None:
            if new_dept is None:
                raise ValidationError("用户需先分配部门,才能设置直属上级")
            if new_mgr == user.id:
                raise ValidationError("直属上级不能是自己")
            manager = await self.users.get_by_id(new_mgr)
            if manager is None:
                raise NotFoundError("上级用户不存在")
            if manager.department_id != new_dept:
                raise ValidationError("直属上级必须与用户在同一部门")
        user.department_id = new_dept
        user.manager_id = new_mgr
        return await self.users.save(user)
