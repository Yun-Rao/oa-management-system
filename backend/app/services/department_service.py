import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.department import Department
from app.models.user import User
from app.repositories.department_repository import DepartmentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.department import DepartmentCreate, DepartmentNode, DepartmentUpdate


class DepartmentService:
    def __init__(self, db: AsyncSession):
        self.departments = DepartmentRepository(db)
        self.users = UserRepository(db)

    async def create_department(self, data: DepartmentCreate) -> Department:
        if data.parent_id is not None:
            parent = await self.departments.get_by_id(data.parent_id)
            if parent is None:
                raise NotFoundError("父部门不存在")
        if await self.departments.get_sibling_by_name(data.name, data.parent_id):
            raise ConflictError("同级部门下已存在同名部门")
        return await self.departments.create(
            Department(name=data.name, parent_id=data.parent_id)
        )

    async def get_tree(self) -> list[DepartmentNode]:
        departments = await self.departments.list_all()
        counts = await self.departments.member_counts()
        nodes = {
            d.id: DepartmentNode(
                id=d.id,
                name=d.name,
                parent_id=d.parent_id,
                member_count=counts.get(d.id, 0),
                children=[],
            )
            for d in departments
        }
        roots: list[DepartmentNode] = []
        for d in departments:
            node = nodes[d.id]
            if d.parent_id is not None and d.parent_id in nodes:
                nodes[d.parent_id].children.append(node)
            else:
                roots.append(node)
        return roots

    async def update_department(
        self, dept_id: uuid.UUID, data: DepartmentUpdate
    ) -> Department:
        dept = await self.departments.get_by_id(dept_id)
        if dept is None:
            raise NotFoundError("部门不存在")
        new_name = data.name if data.name is not None else dept.name
        new_parent = dept.parent_id
        if "parent_id" in data.model_fields_set:
            new_parent = data.parent_id
            if new_parent is not None:
                parent = await self.departments.get_by_id(new_parent)
                if parent is None:
                    raise NotFoundError("父部门不存在")
                descendants = await self.departments.descendant_ids(dept.id)
                if new_parent in descendants:
                    raise ConflictError("不能将部门移动到其自身或子部门下")
        if new_name != dept.name or new_parent != dept.parent_id:
            sibling = await self.departments.get_sibling_by_name(new_name, new_parent)
            if sibling is not None and sibling.id != dept.id:
                raise ConflictError("同级部门下已存在同名部门")
        dept.name = new_name
        dept.parent_id = new_parent
        return await self.departments.save(dept)

    async def delete_department(self, dept_id: uuid.UUID) -> None:
        dept = await self.departments.get_by_id(dept_id)
        if dept is None:
            raise NotFoundError("部门不存在")
        if await self.departments.count_children(dept_id) > 0:
            raise ConflictError("请先删除或移动子部门")
        if await self.departments.count_members(dept_id) > 0:
            raise ConflictError("部门下还有员工,无法删除")
        await self.departments.delete(dept)

    async def list_members(
        self, dept_id: uuid.UUID, page: int, page_size: int, requester: User
    ) -> tuple[list[User], int]:
        dept = await self.departments.get_by_id(dept_id)
        if dept is None:
            raise NotFoundError("部门不存在")
        perms = {p.code for role in requester.roles for p in role.permissions}
        if "user:list" not in perms and requester.department_id != dept_id:
            raise ForbiddenError("无权查看其他部门的人员")
        return await self.users.list_by_department(
            dept_id, (page - 1) * page_size, page_size
        )
