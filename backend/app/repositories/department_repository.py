import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.user import User


class DepartmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, dept_id: uuid.UUID) -> Department | None:
        return await self.db.get(Department, dept_id)

    async def get_sibling_by_name(
        self, name: str, parent_id: uuid.UUID | None
    ) -> Department | None:
        query = select(Department).where(Department.name == name)
        if parent_id is None:
            query = query.where(Department.parent_id.is_(None))
        else:
            query = query.where(Department.parent_id == parent_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Department]:
        result = await self.db.execute(
            select(Department).order_by(Department.created_at)
        )
        return list(result.scalars().all())

    async def descendant_ids(self, dept_id: uuid.UUID) -> set[uuid.UUID]:
        base = (
            select(Department.id).where(Department.id == dept_id).cte(recursive=True)
        )
        children = select(Department.id).where(Department.parent_id == base.c.id)
        cte = base.union_all(children)
        result = await self.db.execute(select(cte.c.id))
        return {row[0] for row in result.all()}

    async def member_counts(self) -> dict[uuid.UUID, int]:
        result = await self.db.execute(
            select(User.department_id, func.count())
            .where(User.department_id.is_not(None))
            .group_by(User.department_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_children(self, dept_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Department)
            .where(Department.parent_id == dept_id)
        )
        return result.scalar_one()

    async def count_members(self, dept_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(User)
            .where(User.department_id == dept_id)
        )
        return result.scalar_one()

    async def create(self, department: Department) -> Department:
        self.db.add(department)
        await self.db.commit()
        await self.db.refresh(department)
        return department

    async def save(self, department: Department) -> Department:
        await self.db.commit()
        await self.db.refresh(department)
        return department

    async def delete(self, department: Department) -> None:
        await self.db.delete(department)
        await self.db.commit()
