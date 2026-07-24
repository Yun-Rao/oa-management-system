import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_by_department(
        self, dept_id: uuid.UUID, offset: int, limit: int
    ) -> tuple[list[User], int]:
        condition = User.department_id == dept_id
        total = (
            await self.db.execute(
                select(func.count()).select_from(User).where(condition)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(User)
            .where(condition)
            .order_by(User.created_at)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list(
        self, keyword: str | None, offset: int, limit: int
    ) -> tuple[list[User], int]:
        query = select(User)
        count_query = select(func.count()).select_from(User)
        if keyword:
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            condition = User.name.ilike(like, escape="\\") | User.email.ilike(
                like, escape="\\"
            )
            query = query.where(condition)
            count_query = count_query.where(condition)
        total = (await self.db.execute(count_query)).scalar_one()
        result = await self.db.execute(
            query.order_by(User.created_at).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def create(self, user: User) -> User:
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def save(self, user: User) -> User:
        await self.db.commit()
        await self.db.refresh(user)
        return user
