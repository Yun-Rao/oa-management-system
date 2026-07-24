# 组织架构模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现部门树管理(创建/编辑/移动/删除/查看)与人员归属(部门 + 直属上级),含 Manager 数据范围过滤。

**Architecture:** 沿用现有三层结构(api/v1 → services → repositories)。部门树用邻接表(parent_id)+ PostgreSQL 递归 CTE 查后代;同级重名、防环、删除校验、同部门上级校验全部在 service 层强制;Manager 数据范围通过权限点 + service 层过滤实现。

**Tech Stack:** FastAPI、SQLAlchemy 2.0 Async、Alembic、Pydantic v2、pytest + httpx(测试库 SQLite + StaticPool)。

**Spec:** `docs/superpowers/specs/2026-07-24-org-structure-design.md`(验收标准见 §9)

**执行纪律(继承上一模块):**
- 每步 TDD:先写失败测试 → 确认失败 → 实现 → 确认通过 → 提交
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`;根目录 `.gitignore` 有用户未提交修改,不得 stage
- 设计决策级变更必须同步 spec;实现细节修复不动 spec
- 所有命令在 `backend/` 目录下执行(pytest、alembic),git 命令在仓库根执行

---

## Task 1: Department 模型 + User 组织字段 + conftest 扩展

**Files:**
- Create: `backend/app/models/department.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_models.py`
- Modify: `backend/alembic/env.py`(模型导入行)

- [ ] **Step 1: 写失败测试(追加到 `backend/tests/test_models.py`)**

```python
async def test_department_create_with_parent(db):
    from app.models.department import Department

    parent = Department(name="技术部")
    db.add(parent)
    await db.commit()
    child = Department(name="后端组", parent_id=parent.id)
    db.add(child)
    await db.commit()
    await db.refresh(child)
    assert child.parent_id == parent.id


async def test_user_org_fields_default_none(db):
    user = User(
        email="org@x.com",
        name="Org",
        hashed_password="x",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    assert user.department_id is None
    assert user.manager_id is None
```

(若 `test_models.py` 顶部未导入 `User`,沿用该文件现有导入方式;`User` 已在现有测试中导入过,直接复用。)

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.models.department'`

- [ ] **Step 3: 创建 `backend/app/models/department.py`**

```python
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Department(Base, TimestampMixin):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )

    parent: Mapped["Department | None"] = relationship(
        back_populates="children", remote_side="Department.id"
    )
    children: Mapped[list["Department"]] = relationship(back_populates="parent")
    members: Mapped[list["User"]] = relationship(back_populates="department")

    __table_args__ = (
        Index(
            "uq_departments_parent_name",
            "parent_id",
            "name",
            unique=True,
            postgresql_where=text("parent_id IS NOT NULL"),
        ),
    )
```

- [ ] **Step 4: 修改 `backend/app/models/user.py`**

在文件顶部追加导入:

```python
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey

if TYPE_CHECKING:
    from app.models.department import Department
```

在 `roles` 关系定义后追加:

```python
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    department: Mapped["Department | None"] = relationship(
        back_populates="members", lazy="selectin"
    )
    manager: Mapped["User | None"] = relationship(
        remote_side="User.id", foreign_keys=[manager_id], lazy="selectin"
    )
```

注意:`department`/`manager` 必须 `lazy="selectin"`——响应序列化时会在 greenlet 外访问,默认 lazy 加载会抛 MissingGreenlet。

- [ ] **Step 5: 修改 `backend/alembic/env.py`**

把模型导入行:

```python
from app.models import associations, permission, role, user  # noqa: F401
```

改为:

```python
from app.models import associations, department, permission, role, user  # noqa: F401
```

- [ ] **Step 6: 修改 `backend/tests/conftest.py`**

在 `ALL_PERMISSIONS` 列表末尾追加 5 个新权限点:

```python
ALL_PERMISSIONS = [
    ("user:create", "创建用户"),
    ("user:list", "查看用户列表"),
    ("user:update", "编辑用户"),
    ("user:disable", "启用/禁用用户"),
    ("role:list", "查看角色列表"),
    ("role:assign", "分配角色"),
    ("department:create", "创建部门"),
    ("department:update", "编辑/移动部门"),
    ("department:delete", "删除部门"),
    ("department:list", "查看部门树"),
    ("department:members", "查看部门人员"),
]
```

在文件顶部导入区追加:

```python
from app.models.department import Department
```

`make_user` 签名扩展为(新增两个可选参数,传入 User 构造):

```python
async def make_user(
    db,
    email="user@example.com",
    password="Passw0rd!",
    name="测试用户",
    roles=None,
    is_active=True,
    department_id=None,
    manager_id=None,
) -> User:
    u = User(
        email=email,
        name=name,
        hashed_password=hash_password(password),
        roles=roles or [],
        is_active=is_active,
        department_id=department_id,
        manager_id=manager_id,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u
```

在 `make_user` 后追加 `make_department`:

```python
async def make_department(db, name="技术部", parent_id=None) -> Department:
    d = Department(name=name, parent_id=parent_id)
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d
```

- [ ] **Step 7: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: PASS(含新旧全部用例)

- [ ] **Step 8: 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过(80 个左右),0 failed

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/department.py backend/app/models/user.py backend/tests/conftest.py backend/tests/test_models.py backend/alembic/env.py
git commit -m "feat(backend): 添加 Department 模型与 User 组织归属字段"
```

---

## Task 2: Alembic 迁移

**Files:**
- Create: `backend/alembic/versions/9c8e2f4a1b07_add_org_structure.py`

- [ ] **Step 1: 创建迁移文件 `backend/alembic/versions/9c8e2f4a1b07_add_org_structure.py`**

```python
"""add org structure

Revision ID: 9c8e2f4a1b07
Revises: f70a6caabc83
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c8e2f4a1b07"
down_revision: Union[str, None] = "f70a6caabc83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["departments.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_departments_parent_id"), "departments", ["parent_id"], unique=False
    )
    op.create_index(
        "uq_departments_parent_name",
        "departments",
        ["parent_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )
    op.add_column("users", sa.Column("department_id", sa.Uuid(), nullable=True))
    op.add_column("users", sa.Column("manager_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_users_department_id"), "users", ["department_id"], unique=False
    )
    op.create_index(op.f("ix_users_manager_id"), "users", ["manager_id"], unique=False)
    op.create_foreign_key(
        "fk_users_department_id",
        "users",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_users_manager_id",
        "users",
        "users",
        ["manager_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_manager_id", "users", type_="foreignkey")
    op.drop_constraint("fk_users_department_id", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_manager_id"), table_name="users")
    op.drop_index(op.f("ix_users_department_id"), table_name="users")
    op.drop_column("users", "manager_id")
    op.drop_column("users", "department_id")
    op.drop_index("uq_departments_parent_name", table_name="departments")
    op.drop_index(op.f("ix_departments_parent_id"), table_name="departments")
    op.drop_table("departments")
```

- [ ] **Step 2: 起开发库并执行迁移**

前置:`docker compose up -d db`(若本地 PG 已在运行可跳过)

Run: `cd backend && alembic upgrade head`
Expected: 输出 `Running upgrade f70a6caabc83 -> 9c8e2f4a1b07, add org structure`

- [ ] **Step 3: 校验模型与迁移无漂移**

Run: `cd backend && alembic check`
Expected: 无 diff 输出,退出码 0

- [ ] **Step 4: 回滚再重放,验证可逆**

Run: `cd backend && alembic downgrade -1 && alembic upgrade head`
Expected: 两条命令均成功

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/9c8e2f4a1b07_add_org_structure.py
git commit -m "feat(backend): 添加组织架构 Alembic 迁移"
```

---

## Task 3: DepartmentRepository

**Files:**
- Create: `backend/app/repositories/department_repository.py`
- Test: `backend/tests/test_department_repository.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_department_repository.py`**

```python
from app.repositories.department_repository import DepartmentRepository
from tests.conftest import make_department, make_user


async def test_get_sibling_by_name_root(db):
    from app.repositories.department_repository import DepartmentRepository

    dept = await make_department(db, name="技术部")
    repo = DepartmentRepository(db)
    found = await repo.get_sibling_by_name("技术部", None)
    assert found is not None and found.id == dept.id
    assert await repo.get_sibling_by_name("不存在", None) is None


async def test_descendant_ids_includes_self_and_all_descendants(db):
    repo = DepartmentRepository(db)
    root = await make_department(db, name="技术部")
    child = await make_department(db, name="后端组", parent_id=root.id)
    grandchild = await make_department(db, name="平台组", parent_id=child.id)
    other = await make_department(db, name="市场部")

    ids = await repo.descendant_ids(root.id)
    assert ids == {root.id, child.id, grandchild.id}
    assert other.id not in ids


async def test_member_counts(db):
    repo = DepartmentRepository(db)
    dept = await make_department(db, name="技术部")
    await make_user(db, email="a@x.com", department_id=dept.id)
    await make_user(db, email="b@x.com", department_id=dept.id)
    await make_user(db, email="c@x.com")

    counts = await repo.member_counts()
    assert counts[dept.id] == 2


async def test_count_children_and_members(db):
    repo = DepartmentRepository(db)
    dept = await make_department(db, name="技术部")
    await make_department(db, name="后端组", parent_id=dept.id)
    await make_user(db, email="a@x.com", department_id=dept.id)

    assert await repo.count_children(dept.id) == 1
    assert await repo.count_members(dept.id) == 1
```

注意:文件顶部若从 `tests.conftest` 导入失败,参照现有测试文件的导入方式(现有测试直接 `from tests.conftest import ...` 或同目录隐式可用,以 `test_repositories.py` 的写法为准)。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_department_repository.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.repositories.department_repository'`

- [ ] **Step 3: 创建 `backend/app/repositories/department_repository.py`**

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_department_repository.py -v`
Expected: PASS(4 个用例)

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/department_repository.py backend/tests/test_department_repository.py
git commit -m "feat(backend): 添加 DepartmentRepository(含递归后代查询)"
```

---

## Task 4: ValidationError 异常 + 组织架构 Schemas

**Files:**
- Modify: `backend/app/core/exceptions.py`
- Create: `backend/app/schemas/department.py`
- Modify: `backend/app/schemas/user.py`
- Test: `backend/tests/test_exceptions.py`(追加)、`backend/tests/test_schemas_org.py`(新建)

- [ ] **Step 1: 写失败测试**

`backend/tests/test_exceptions.py` 追加(参照该文件现有用例风格):

```python
def test_validation_error_status_and_code():
    from app.core.exceptions import ValidationError

    err = ValidationError("直属上级不能是自己")
    assert err.status_code == 422
    assert err.code == "VALIDATION_ERROR"
    assert err.message == "直属上级不能是自己"
```

新建 `backend/tests/test_schemas_org.py`:

```python
import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.department import DepartmentCreate, DepartmentNode, DepartmentUpdate
from app.schemas.user import UserOrgUpdate


def test_department_create_validates_name_length():
    with pytest.raises(PydanticValidationError):
        DepartmentCreate(name="")
    with pytest.raises(PydanticValidationError):
        DepartmentCreate(name="x" * 101)
    ok = DepartmentCreate(name="技术部", parent_id=None)
    assert ok.parent_id is None


def test_department_node_recursive():
    child = DepartmentNode(
        id=uuid.uuid4(), name="后端组", parent_id=None, member_count=3, children=[]
    )
    root = DepartmentNode(
        id=uuid.uuid4(),
        name="技术部",
        parent_id=None,
        member_count=10,
        children=[child],
    )
    assert root.children[0].name == "后端组"


def test_user_org_update_distinguishes_unset_and_null():
    empty = UserOrgUpdate()
    assert "department_id" not in empty.model_fields_set
    cleared = UserOrgUpdate(manager_id=None)
    assert "manager_id" in cleared.model_fields_set
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_exceptions.py tests/test_schemas_org.py -v`
Expected: FAIL(ImportError: ValidationError / No module named app.schemas.department)

- [ ] **Step 3: 修改 `backend/app/core/exceptions.py`,文件末尾追加**

```python
class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
```

- [ ] **Step 4: 创建 `backend/app/schemas/department.py`**

```python
import uuid

from pydantic import BaseModel, ConfigDict, Field


class DepartmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: uuid.UUID | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: uuid.UUID | None = None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None


class DepartmentNode(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    member_count: int
    children: list["DepartmentNode"] = []
```

- [ ] **Step 5: 修改 `backend/app/schemas/user.py`**

导入区追加:

```python
from app.schemas.department import DepartmentBrief
```

`RoleBrief` 之后追加:

```python
class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class UserOrgUpdate(BaseModel):
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
```

`UserResponse` 增加两个字段(放在 `roles` 之后):

```python
    department: DepartmentBrief | None = None
    manager: UserBrief | None = None
```

`MeResponse` 同样增加这两个字段。

- [ ] **Step 6: 运行确认通过 + 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed(UserResponse/MeResponse 新增可选字段不破坏既有用例)

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/exceptions.py backend/app/schemas/department.py backend/app/schemas/user.py backend/tests/test_exceptions.py backend/tests/test_schemas_org.py
git commit -m "feat(backend): 添加 ValidationError 与组织架构 Schemas"
```

---

## Task 5: DepartmentService

**Files:**
- Create: `backend/app/services/department_service.py`
- Test: `backend/tests/test_department_service.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_department_service.py`**

```python
import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.services.department_service import DepartmentService
from tests.conftest import make_department, make_user


async def test_create_root_and_child(db):
    svc = DepartmentService(db)
    root = await svc.create_department(DepartmentCreate(name="技术部"))
    child = await svc.create_department(
        DepartmentCreate(name="后端组", parent_id=root.id)
    )
    assert child.parent_id == root.id


async def test_create_rejects_sibling_duplicate_name(db):
    svc = DepartmentService(db)
    await svc.create_department(DepartmentCreate(name="技术部"))
    with pytest.raises(ConflictError, match="同级部门下已存在同名部门"):
        await svc.create_department(DepartmentCreate(name="技术部"))


async def test_create_allows_same_name_under_different_parent(db):
    svc = DepartmentService(db)
    a = await svc.create_department(DepartmentCreate(name="甲部门"))
    b = await svc.create_department(DepartmentCreate(name="乙部门"))
    await svc.create_department(DepartmentCreate(name="同名组", parent_id=a.id))
    await svc.create_department(DepartmentCreate(name="同名组", parent_id=b.id))


async def test_create_rejects_unknown_parent(db):
    import uuid

    svc = DepartmentService(db)
    with pytest.raises(NotFoundError, match="父部门不存在"):
        await svc.create_department(
            DepartmentCreate(name="孤儿", parent_id=uuid.uuid4())
        )


async def test_get_tree_nested_with_member_count(db):
    svc = DepartmentService(db)
    root = await svc.create_department(DepartmentCreate(name="技术部"))
    child = await svc.create_department(
        DepartmentCreate(name="后端组", parent_id=root.id)
    )
    await make_user(db, email="a@x.com", department_id=child.id)

    tree = await svc.get_tree()
    assert len(tree) == 1
    assert tree[0].name == "技术部"
    assert tree[0].member_count == 0
    assert tree[0].children[0].name == "后端组"
    assert tree[0].children[0].member_count == 1


async def test_update_rename_and_move(db):
    svc = DepartmentService(db)
    a = await svc.create_department(DepartmentCreate(name="甲"))
    b = await svc.create_department(DepartmentCreate(name="乙"))
    moved = await svc.update_department(
        b.id, DepartmentUpdate(name="乙改", parent_id=a.id)
    )
    assert moved.name == "乙改"
    assert moved.parent_id == a.id


async def test_update_rejects_move_to_descendant(db):
    svc = DepartmentService(db)
    root = await svc.create_department(DepartmentCreate(name="技术部"))
    child = await svc.create_department(
        DepartmentCreate(name="后端组", parent_id=root.id)
    )
    with pytest.raises(ConflictError, match="不能将部门移动到其自身或子部门下"):
        await svc.update_department(root.id, DepartmentUpdate(parent_id=child.id))
    with pytest.raises(ConflictError, match="不能将部门移动到其自身或子部门下"):
        await svc.update_department(root.id, DepartmentUpdate(parent_id=root.id))


async def test_update_rejects_sibling_name_conflict_on_move(db):
    svc = DepartmentService(db)
    a = await svc.create_department(DepartmentCreate(name="甲"))
    await svc.create_department(DepartmentCreate(name="后端组", parent_id=a.id))
    orphan = await svc.create_department(DepartmentCreate(name="后端组"))
    with pytest.raises(ConflictError, match="同级部门下已存在同名部门"):
        await svc.update_department(orphan.id, DepartmentUpdate(parent_id=a.id))


async def test_delete_empty_department(db):
    svc = DepartmentService(db)
    dept = await svc.create_department(DepartmentCreate(name="技术部"))
    await svc.delete_department(dept.id)
    assert await svc.departments.get_by_id(dept.id) is None


async def test_delete_rejects_department_with_children(db):
    svc = DepartmentService(db)
    root = await svc.create_department(DepartmentCreate(name="技术部"))
    await svc.create_department(DepartmentCreate(name="后端组", parent_id=root.id))
    with pytest.raises(ConflictError, match="请先删除或移动子部门"):
        await svc.delete_department(root.id)


async def test_delete_rejects_department_with_members(db):
    svc = DepartmentService(db)
    dept = await svc.create_department(DepartmentCreate(name="技术部"))
    await make_user(db, email="a@x.com", department_id=dept.id)
    with pytest.raises(ConflictError, match="部门下还有员工,无法删除"):
        await svc.delete_department(dept.id)


async def test_list_members_scope(db):
    svc = DepartmentService(db)
    dept = await svc.create_department(DepartmentCreate(name="技术部"))
    other = await svc.create_department(DepartmentCreate(name="市场部"))
    await make_user(db, email="a@x.com", department_id=dept.id)

    admin = await make_user(db, email="admin@x.com", roles=[])
    from tests.conftest import ALL_PERMISSIONS
    from app.models.permission import Permission
    from app.models.role import Role

    perms = [Permission(code=c, name=n) for c, n in ALL_PERMISSIONS]
    admin.roles = [Role(code="admin", name="管理员", permissions=perms)]
    await db.commit()

    members, total = await svc.list_members(dept.id, 1, 20, admin)
    assert total == 1

    outsider = await make_user(db, email="m@x.com", department_id=other.id)
    with pytest.raises(ForbiddenError, match="无权查看其他部门的人员"):
        await svc.list_members(dept.id, 1, 20, outsider)

    insider = await make_user(db, email="i@x.com", department_id=dept.id)
    members, total = await svc.list_members(dept.id, 1, 20, insider)
    assert total == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_department_service.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.services.department_service'`

- [ ] **Step 3: 创建 `backend/app/services/department_service.py`**

```python
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
```

注意:`list_members` 用 `user:list` 权限点作为「可看任意部门」的管理员标记——admin 角色拥有该权限点,manager 没有。此约定需与 spec §5 数据范围过滤规则一致。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_department_service.py -v`
Expected: PASS(12 个用例)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/department_service.py backend/tests/test_department_service.py
git commit -m "feat(backend): 添加 DepartmentService(树构建/防环/删除校验/数据范围)"
```

---

## Task 6: Departments 路由

**Files:**
- Create: `backend/app/api/v1/departments.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_departments_api.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_departments_api.py`**

```python
import pytest

from tests.conftest import (
    login_token,
    make_department,
    make_permission,
    make_role,
    make_user,
)


async def test_create_department(admin_client):
    resp = await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "技术部"
    assert body["parent_id"] is None


async def test_create_department_requires_auth(client):
    resp = await client.post("/api/v1/departments", json={"name": "技术部"})
    assert resp.status_code == 401


async def test_create_department_requires_permission(employee_client):
    resp = await employee_client.post("/api/v1/departments", json={"name": "技术部"})
    assert resp.status_code == 403


async def test_create_department_duplicate_409(admin_client):
    await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    resp = await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    assert resp.status_code == 409


async def test_get_tree(admin_client):
    root = (
        await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    ).json()
    await admin_client.post(
        "/api/v1/departments", json={"name": "后端组", "parent_id": root["id"]}
    )
    resp = await admin_client.get("/api/v1/departments")
    assert resp.status_code == 200
    tree = resp.json()
    assert len(tree) == 1
    assert tree[0]["name"] == "技术部"
    assert tree[0]["children"][0]["name"] == "后端组"
    assert tree[0]["children"][0]["member_count"] == 0


async def test_update_department_move_rejects_cycle(admin_client):
    root = (
        await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    ).json()
    child = (
        await admin_client.post(
            "/api/v1/departments", json={"name": "后端组", "parent_id": root["id"]}
        )
    ).json()
    resp = await admin_client.patch(
        f"/api/v1/departments/{root['id']}", json={"parent_id": child["id"]}
    )
    assert resp.status_code == 409


async def test_delete_department(admin_client):
    dept = (await admin_client.post("/api/v1/departments", json={"name": "技术部"})).json()
    resp = await admin_client.delete(f"/api/v1/departments/{dept['id']}")
    assert resp.status_code == 204
    resp = await admin_client.get("/api/v1/departments")
    assert resp.json() == []


async def test_delete_department_with_members_409(admin_client, db):
    dept = await make_department(db, name="技术部")
    await make_user(db, email="a@x.com", department_id=dept.id)
    resp = await admin_client.delete(f"/api/v1/departments/{dept.id}")
    assert resp.status_code == 409


@pytest.mark.parametrize(
    "method,url",
    [
        ("POST", "/api/v1/departments"),
        ("GET", "/api/v1/departments"),
    ],
)
async def test_department_endpoints_reject_anonymous(client, method, url):
    resp = await client.request(method, url)
    assert resp.status_code == 401


async def test_members_manager_scope(client, db):
    dept = await make_department(db, name="技术部")
    other = await make_department(db, name="市场部")
    await make_user(db, email="a@x.com", department_id=dept.id)

    p1 = await make_permission(db, code="department:list", name="查看部门树")
    p2 = await make_permission(db, code="department:members", name="查看部门人员")
    role = await make_role(db, code="manager", name="部门主管", permissions=[p1, p2])
    await make_user(
        db, email="mgr@x.com", password="Passw0rd!", roles=[role], department_id=dept.id
    )
    token = await login_token(client, "mgr@x.com", "Passw0rd!")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/departments/{dept.id}/members", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2  # mgr 自己 + a@x.com

    resp = await client.get(f"/api/v1/departments/{other.id}/members", headers=headers)
    assert resp.status_code == 403


async def test_members_admin_can_view_any(admin_client, db):
    dept = await make_department(db, name="技术部")
    await make_user(db, email="a@x.com", department_id=dept.id)
    resp = await admin_client.get(f"/api/v1/departments/{dept.id}/members")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_departments_api.py -v`
Expected: FAIL,404 Not Found(路由未注册)

- [ ] **Step 3: 创建 `backend/app/api/v1/departments.py`**

```python
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.models.user import User
from app.schemas.department import (
    DepartmentCreate,
    DepartmentNode,
    DepartmentResponse,
    DepartmentUpdate,
)
from app.schemas.user import UserListResponse, UserResponse
from app.services.department_service import DepartmentService

router = APIRouter(prefix="/departments", tags=["departments"])


@router.post("", response_model=DepartmentResponse, status_code=201)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("department:create")),
):
    return await DepartmentService(db).create_department(data)


@router.get("", response_model=list[DepartmentNode])
async def get_tree(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("department:list")),
):
    return await DepartmentService(db).get_tree()


@router.patch("/{dept_id}", response_model=DepartmentResponse)
async def update_department(
    dept_id: uuid.UUID,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("department:update")),
):
    return await DepartmentService(db).update_department(dept_id, data)


@router.delete("/{dept_id}", status_code=204)
async def delete_department(
    dept_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("department:delete")),
):
    await DepartmentService(db).delete_department(dept_id)


@router.get("/{dept_id}/members", response_model=UserListResponse)
async def list_members(
    dept_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    requester: User = Depends(require_permission("department:members")),
):
    items, total = await DepartmentService(db).list_members(
        dept_id, page, page_size, requester
    )
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )
```

- [ ] **Step 4: 修改 `backend/app/main.py`**

导入行改为:

```python
from app.api.v1 import auth, departments, roles, users
```

路由注册追加(在 `roles.router` 之后):

```python
api_v1.include_router(departments.router)
```

- [ ] **Step 5: 运行确认通过 + 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/departments.py backend/app/main.py backend/tests/test_departments_api.py
git commit -m "feat(backend): 添加 Departments 路由(CRUD/树/成员列表)"
```

---

## Task 7: 人员归属(PATCH /users/{id}/org)

**Files:**
- Modify: `backend/app/repositories/user_repository.py`
- Modify: `backend/app/services/user_service.py`
- Modify: `backend/app/api/v1/users.py`
- Test: `backend/tests/test_user_org.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_user_org.py`**

```python
from tests.conftest import make_department, make_user


async def test_set_org_assigns_department_and_manager(admin_client, db):
    dept = await make_department(db, name="技术部")
    manager = await make_user(db, email="m@x.com", department_id=dept.id)
    user = await make_user(db, email="u@x.com")

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org",
        json={"department_id": str(dept.id), "manager_id": str(manager.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["department"]["id"] == str(dept.id)
    assert body["manager"]["id"] == str(manager.id)


async def test_set_org_manager_must_be_same_department(admin_client, db):
    dept = await make_department(db, name="技术部")
    other = await make_department(db, name="市场部")
    manager = await make_user(db, email="m@x.com", department_id=other.id)
    user = await make_user(db, email="u@x.com")

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org",
        json={"department_id": str(dept.id), "manager_id": str(manager.id)},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_set_org_manager_without_department_422(admin_client, db):
    manager = await make_user(db, email="m@x.com")
    user = await make_user(db, email="u@x.com")

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org", json={"manager_id": str(manager.id)}
    )
    assert resp.status_code == 422


async def test_set_org_manager_cannot_be_self(admin_client, db):
    dept = await make_department(db, name="技术部")
    user = await make_user(db, email="u@x.com", department_id=dept.id)

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org",
        json={"manager_id": str(user.id)},
    )
    assert resp.status_code == 422


async def test_set_org_clear_manager(admin_client, db):
    dept = await make_department(db, name="技术部")
    manager = await make_user(db, email="m@x.com", department_id=dept.id)
    user = await make_user(
        db, email="u@x.com", department_id=dept.id, manager_id=manager.id
    )

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org", json={"manager_id": None}
    )
    assert resp.status_code == 200
    assert resp.json()["manager"] is None
    assert resp.json()["department"]["id"] == str(dept.id)


async def test_set_org_unknown_department_404(admin_client, db):
    import uuid

    user = await make_user(db, email="u@x.com")
    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org", json={"department_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404


async def test_set_org_requires_permission(employee_client, db):
    user = await make_user(db, email="u2@x.com")
    resp = await employee_client.patch(f"/api/v1/users/{user.id}/org", json={})
    assert resp.status_code == 403
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_user_org.py -v`
Expected: FAIL(404,路由不存在;list_by_department 缺失)

- [ ] **Step 3: 修改 `backend/app/repositories/user_repository.py`,在 `save` 方法后追加**

```python
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
```

- [ ] **Step 4: 修改 `backend/app/services/user_service.py`**

导入区追加:

```python
from app.core.exceptions import ValidationError
from app.repositories.department_repository import DepartmentRepository
from app.schemas.user import UserOrgUpdate
```

`__init__` 追加:

```python
        self.departments = DepartmentRepository(db)
```

类末尾追加方法:

```python
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
```

- [ ] **Step 5: 修改 `backend/app/api/v1/users.py`**

导入区 `app.schemas.user` 导入列表追加 `UserOrgUpdate`,文件末尾追加:

```python
@router.patch("/{user_id}/org", response_model=UserResponse)
async def set_org(
    user_id: uuid.UUID,
    data: UserOrgUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user:update")),
):
    return await UserService(db).set_org(user_id, data)
```

- [ ] **Step 6: 运行确认通过 + 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed

- [ ] **Step 7: Commit**

```bash
git add backend/app/repositories/user_repository.py backend/app/services/user_service.py backend/app/api/v1/users.py backend/tests/test_user_org.py
git commit -m "feat(backend): 添加人员归属接口 PATCH /users/{id}/org"
```

---

## Task 8: /auth/me 与用户响应补充组织信息

**Files:**
- Modify: `backend/app/api/v1/auth.py`
- Test: `backend/tests/test_auth_api.py`(追加)、`backend/tests/test_users_api.py`(追加)

- [ ] **Step 1: 写失败测试**

`backend/tests/test_auth_api.py` 追加:

```python
async def test_me_includes_department_and_manager(client, db):
    from tests.conftest import make_department, make_user, login_token

    dept = await make_department(db, name="技术部")
    manager = await make_user(db, email="m@x.com", department_id=dept.id)
    await make_user(
        db,
        email="u@x.com",
        password="Passw0rd!",
        department_id=dept.id,
        manager_id=manager.id,
    )
    token = await login_token(client, "u@x.com", "Passw0rd!")
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["department"]["name"] == "技术部"
    assert body["manager"]["id"] == str(manager.id)
```

`backend/tests/test_users_api.py` 追加:

```python
async def test_user_response_includes_org_briefs(admin_client, db):
    from tests.conftest import make_department, make_user

    dept = await make_department(db, name="技术部")
    user = await make_user(db, email="u@x.com", department_id=dept.id)
    resp = await admin_client.get("/api/v1/users")
    assert resp.status_code == 200
    target = [u for u in resp.json()["items"] if u["id"] == str(user.id)][0]
    assert target["department"]["name"] == "技术部"
    assert target["manager"] is None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_auth_api.py::test_me_includes_department_and_manager tests/test_users_api.py::test_user_response_includes_org_briefs -v`
Expected: FAIL(KeyError/assertion,响应缺少 department 字段——/users 列表在 Task 4 已加字段应通过,若通过则仅 /auth/me 失败,均符合预期继续)

- [ ] **Step 3: 修改 `backend/app/api/v1/auth.py` 的 `me` 函数**

导入区追加:

```python
from app.schemas.department import DepartmentBrief
from app.schemas.user import UserBrief
```

`me` 返回改为:

```python
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        is_active=current_user.is_active,
        roles=[RoleBrief(code=r.code, name=r.name) for r in current_user.roles],
        permissions=permissions,
        department=(
            DepartmentBrief.model_validate(current_user.department)
            if current_user.department
            else None
        ),
        manager=(
            UserBrief.model_validate(current_user.manager)
            if current_user.manager
            else None
        ),
    )
```

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/auth.py backend/tests/test_auth_api.py backend/tests/test_users_api.py
git commit -m "feat(backend): /auth/me 与用户列表响应补充部门/上级概要"
```

---

## Task 9: Seed 更新(新权限点 + 角色权限映射)

**Files:**
- Modify: `backend/scripts/seed.py`
- Modify: `backend/tests/test_seed.py`

- [ ] **Step 1: 先看现有 `backend/tests/test_seed.py` 的用例结构,追加失败测试**

```python
async def test_seed_assigns_department_permissions(db):
    from scripts.seed import seed
    from app.models.permission import Permission
    from app.models.role import Role
    from sqlalchemy import select

    await seed(db)

    perms = {p.code for p in (await db.execute(select(Permission))).scalars()}
    expected = {
        "department:create",
        "department:update",
        "department:delete",
        "department:list",
        "department:members",
    }
    assert expected <= perms

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    admin_perms = {p.code for p in roles["admin"].permissions}
    manager_perms = {p.code for p in roles["manager"].permissions}
    assert expected <= admin_perms
    assert manager_perms == {"department:list", "department:members"}
    assert roles["employee"].permissions == []


async def test_seed_repairs_manager_permissions_on_rerun(db):
    from scripts.seed import seed
    from app.models.role import Role
    from sqlalchemy import select

    await seed(db)
    role = (
        await db.execute(select(Role).where(Role.code == "manager"))
    ).scalar_one()
    role.permissions = []
    await db.commit()

    await seed(db)
    role = (
        await db.execute(select(Role).where(Role.code == "manager"))
    ).scalar_one()
    assert {p.code for p in role.permissions} == {
        "department:list",
        "department:members",
    }
```

注意:参照 `test_seed.py` 现有 fixture/导入习惯调整(import 位置、db fixture 用法与现有用例保持一致)。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_seed.py -v`
Expected: FAIL(断言不成立,新权限点不存在)

- [ ] **Step 3: 修改 `backend/scripts/seed.py`**

`PERMISSIONS` 列表追加:

```python
    ("department:create", "创建部门"),
    ("department:update", "编辑/移动部门"),
    ("department:delete", "删除部门"),
    ("department:list", "查看部门树"),
    ("department:members", "查看部门人员"),
```

`ROLES` 之后新增角色权限映射(`None` 表示全部权限点):

```python
ROLE_PERMISSIONS: dict[str, list[str] | None] = {
    "admin": None,
    "manager": ["department:list", "department:members"],
    "employee": [],
}
```

角色创建/修复循环替换为(整体替换现有 `for code, name, description in ROLES:` 循环体):

```python
    existing_roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    for code, name, description in ROLES:
        wanted = ROLE_PERMISSIONS[code]
        target_perms = (
            list(perms.values()) if wanted is None else [perms[c] for c in wanted]
        )
        if code not in existing_roles:
            role = Role(code=code, name=name, description=description)
            role.permissions = target_perms
            db.add(role)
            existing_roles[code] = role
        else:
            # 幂等修复:重跑 seed 时校准角色权限集合
            # 旧 permissions 集合在 flush 时于 greenlet 上下文内
            # 通过 selectin 加载以计算 diff,故无 MissingGreenlet
            existing_roles[code].permissions = target_perms
    await db.flush()
```

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed

- [ ] **Step 5: 在开发库重跑 seed 验证幂等**

前置:`docker compose up -d db` 且已完成迁移

Run: `cd backend && python -m scripts.seed && python -m scripts.seed`
Expected: 两次均输出 `Seed 完成,admin 账号: ...`,无异常

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/seed.py backend/tests/test_seed.py
git commit -m "feat(backend): seed 增加部门权限点与角色权限映射"
```

---

## Task 10: 全量验收

- [ ] **Step 1: 全量测试**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed

- [ ] **Step 2: 对照 spec §9 验收标准逐项确认**

- 部门支持树形结构:`test_get_tree_nested_with_member_count`、`test_get_tree`
- 删除校验(有员工/子部门 409):`test_delete_rejects_department_with_children/members`、`test_delete_department_with_members_409`
- Admin 部门管理与人员归属:Task 6/7 全部 admin 用例
- Manager 本部门可见、越权 403:`test_members_manager_scope`、`test_list_members_scope`
- 移动防环:`test_update_rejects_move_to_descendant`、`test_update_department_move_rejects_cycle`

- [ ] **Step 3: 勾选 `docs/superpowers/specs/2026-07-24-org-structure-design.md` §9 的全部 checkbox(`- [ ]` → `- [x]`)**

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-24-org-structure-design.md
git commit -m "test(backend): 组织架构模块全量验收通过,勾选 spec 验收标准"
```
