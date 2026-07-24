from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role


class RoleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> list[Role]:
        result = await self.db.execute(select(Role).order_by(Role.code))
        return list(result.scalars().all())

    async def get_by_codes(self, codes: list[str]) -> list[Role]:
        if not codes:
            return []
        result = await self.db.execute(select(Role).where(Role.code.in_(codes)))
        return list(result.scalars().all())
