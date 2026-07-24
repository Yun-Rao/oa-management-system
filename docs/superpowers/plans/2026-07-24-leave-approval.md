# 请假审批模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现请假申请(提交/撤回)、审批(通过/驳回)、三类查询(我的申请/待我审批/全部记录)与状态变更留痕。

**Architecture:** 沿用现有三层结构(api/v1 → services → repositories)。申请单表存当前状态,状态历史表只追加(审计留痕);审批人提交时快照直属上级;重叠校验、状态机、权限与数据归属全部在 service 层强制。

**Tech Stack:** FastAPI、SQLAlchemy 2.0 Async、Alembic、Pydantic v2、pytest + httpx(测试库 SQLite + StaticPool)。

**Spec:** `docs/superpowers/specs/2026-07-24-leave-approval-design.md`(验收标准见 §10)

**执行纪律(继承上一模块):**
- 每步 TDD:先写失败测试 → 确认失败 → 实现 → 确认通过 → 提交
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- 设计决策级变更必须同步 spec;实现细节修复不动 spec
- 所有命令在 `backend/` 目录下执行(pytest、alembic),git 命令在仓库根执行

---

## Task 1: LeaveRequest + LeaveStatusHistory 模型 + conftest 扩展

**Files:**
- Create: `backend/app/models/leave.py`
- Modify: `backend/alembic/env.py`(模型导入行)
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_models.py`

- [ ] **Step 1: 写失败测试(追加到 `backend/tests/test_models.py`)**

```python
async def test_leave_request_create(db):
    from datetime import date

    from app.models.leave import LeaveRequest

    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    leave = LeaveRequest(
        applicant_id=applicant.id,
        approver_id=approver.id,
        type="annual",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
        reason="家庭旅行",
    )
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    assert leave.status == "pending"
    assert leave.applicant.id == applicant.id
    assert leave.approver.id == approver.id


async def test_leave_status_history_append(db):
    from datetime import date

    from app.models.leave import LeaveRequest, LeaveStatusHistory

    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    leave = LeaveRequest(
        applicant_id=applicant.id,
        approver_id=approver.id,
        type="sick",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
        reason="感冒",
    )
    db.add(leave)
    await db.commit()
    entry = LeaveStatusHistory(
        request_id=leave.id,
        from_status=None,
        to_status="pending",
        actor_id=applicant.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    assert entry.from_status is None
    assert entry.to_status == "pending"
    assert entry.comment is None


async def test_leave_history_backref(db):
    from datetime import date

    from app.models.leave import LeaveRequest, LeaveStatusHistory

    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    leave = LeaveRequest(
        applicant_id=applicant.id,
        approver_id=approver.id,
        type="personal",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
        reason="私事",
    )
    db.add(leave)
    await db.commit()
    db.add(
        LeaveStatusHistory(
            request_id=leave.id,
            from_status=None,
            to_status="pending",
            actor_id=applicant.id,
        )
    )
    await db.commit()
    await db.refresh(leave)
    assert len(leave.history) == 1
    assert leave.history[0].to_status == "pending"
```

(`test_models.py` 顶部已有 `from tests.conftest import make_user`,直接沿用。)

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.models.leave'`

- [ ] **Step 3: 创建 `backend/app/models/leave.py`**

```python
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    approver_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )

    applicant: Mapped["User"] = relationship(
        foreign_keys=[applicant_id], lazy="selectin"
    )
    approver: Mapped["User"] = relationship(
        foreign_keys=[approver_id], lazy="selectin"
    )
    history: Mapped[list["LeaveStatusHistory"]] = relationship(
        back_populates="request",
        lazy="selectin",
        order_by="LeaveStatusHistory.created_at",
    )


class LeaveStatusHistory(Base):
    __tablename__ = "leave_status_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("leave_requests.id", ondelete="RESTRICT"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    comment: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    request: Mapped[LeaveRequest] = relationship(back_populates="history")
    actor: Mapped["User"] = relationship(lazy="selectin")
```

注意:
- `LeaveStatusHistory` 不挂 TimestampMixin(追加式表只有 created_at)
- `User` 侧不加反向关系(避免改动 user.py);`applicant`/`approver` 必须显式 `foreign_keys`,两个 FK 同指 users 表,不指定会报 AmbiguousForeignKeysError
- 所有关系 `lazy="selectin"`(序列化在 greenlet 外访问,与 User/Department 一致)

- [ ] **Step 4: 修改 `backend/alembic/env.py`**

把模型导入行:

```python
from app.models import associations, department, permission, role, user  # noqa: F401
```

改为:

```python
from app.models import associations, department, leave, permission, role, user  # noqa: F401
```

- [ ] **Step 5: 修改 `backend/tests/conftest.py`**

`ALL_PERMISSIONS` 列表末尾追加 4 个新权限点:

```python
    ("leave:create", "提交/撤回请假申请"),
    ("leave:list", "查看我的申请"),
    ("leave:approve", "审批请假申请"),
    ("leave:list_all", "查看全部审批记录"),
```

导入区追加:

```python
from datetime import date

from app.models.leave import LeaveRequest
```

`make_department` 后追加 `make_leave`:

```python
async def make_leave(
    db,
    applicant: User,
    approver: User,
    type="personal",
    start_date=date(2026, 8, 1),
    end_date=date(2026, 8, 2),
    reason="私事",
    status="pending",
) -> LeaveRequest:
    leave = LeaveRequest(
        applicant_id=applicant.id,
        approver_id=approver.id,
        type=type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        status=status,
    )
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    return leave
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: PASS(含新旧全部用例)

- [ ] **Step 7: 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过(127 个左右),0 failed

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/leave.py backend/alembic/env.py backend/tests/conftest.py backend/tests/test_models.py
git commit -m "feat(backend): 添加 LeaveRequest 与 LeaveStatusHistory 模型"
```

---

## Task 2: Alembic 迁移

**Files:**
- Create: `backend/alembic/versions/5f3a8c1d9e02_add_leave_approval.py`

- [ ] **Step 1: 创建迁移文件 `backend/alembic/versions/5f3a8c1d9e02_add_leave_approval.py`**

```python
"""add leave approval

Revision ID: 5f3a8c1d9e02
Revises: 9c8e2f4a1b07
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5f3a8c1d9e02"
down_revision: Union[str, None] = "9c8e2f4a1b07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("applicant_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approver_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["applicant_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_leave_requests_applicant_id"),
        "leave_requests",
        ["applicant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_leave_requests_approver_id"),
        "leave_requests",
        ["approver_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_leave_requests_status"), "leave_requests", ["status"], unique=False
    )
    op.create_table(
        "leave_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["leave_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_leave_status_history_request_id"),
        "leave_status_history",
        ["request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_leave_status_history_request_id"), table_name="leave_status_history"
    )
    op.drop_table("leave_status_history")
    op.drop_index(op.f("ix_leave_requests_status"), table_name="leave_requests")
    op.drop_index(op.f("ix_leave_requests_approver_id"), table_name="leave_requests")
    op.drop_index(op.f("ix_leave_requests_applicant_id"), table_name="leave_requests")
    op.drop_table("leave_requests")
```

注意:模型 `status` 列的 `default="pending"` 是 Python 端默认值,迁移中**不**加 server_default,`alembic check` 不会因此报漂移(与既有迁移风格一致)。

- [ ] **Step 2: 起开发库并执行迁移**

前置:`docker compose up -d db`(若本地 PG 已在运行可跳过)

Run: `cd backend && alembic upgrade head`
Expected: 输出 `Running upgrade 9c8e2f4a1b07 -> 5f3a8c1d9e02, add leave approval`

- [ ] **Step 3: 校验模型与迁移无漂移**

Run: `cd backend && alembic check`
Expected: 无 diff 输出,退出码 0

- [ ] **Step 4: 回滚再重放,验证可逆**

Run: `cd backend && alembic downgrade -1 && alembic upgrade head`
Expected: 两条命令均成功

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/5f3a8c1d9e02_add_leave_approval.py
git commit -m "feat(backend): 添加请假审批 Alembic 迁移"
```

---

## Task 3: LeaveRepository

**Files:**
- Create: `backend/app/repositories/leave_repository.py`
- Test: `backend/tests/test_leave_repository.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_leave_repository.py`**

```python
from datetime import date

from app.models.leave import LeaveRequest, LeaveStatusHistory
from app.repositories.leave_repository import LeaveRepository
from tests.conftest import make_department, make_leave, make_user


async def test_find_overlapping_detects(db):
    repo = LeaveRepository(db)
    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    await make_leave(
        db, applicant, approver, start_date=date(2026, 8, 1), end_date=date(2026, 8, 3)
    )
    # 完全包含、部分重叠、含共同边界日均算重叠
    assert await repo.find_overlapping(applicant.id, date(2026, 8, 2), date(2026, 8, 5))
    assert await repo.find_overlapping(applicant.id, date(2026, 7, 30), date(2026, 8, 1))
    assert await repo.find_overlapping(applicant.id, date(2026, 8, 3), date(2026, 8, 5))
    # 首尾相接(次日开始)与其他申请人均不算
    assert await repo.find_overlapping(applicant.id, date(2026, 8, 4), date(2026, 8, 5)) is None
    other = await make_user(db, email="b@x.com")
    assert await repo.find_overlapping(other.id, date(2026, 8, 2), date(2026, 8, 5)) is None


async def test_find_overlapping_ignores_inactive_status(db):
    repo = LeaveRepository(db)
    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    await make_leave(db, applicant, approver, status="rejected")
    await make_leave(db, applicant, approver, status="canceled")
    assert (
        await repo.find_overlapping(applicant.id, date(2026, 8, 1), date(2026, 8, 2))
        is None
    )


async def test_create_persists_request_and_history(db):
    repo = LeaveRepository(db)
    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    leave = LeaveRequest(
        applicant_id=applicant.id,
        approver_id=approver.id,
        type="annual",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
        reason="家庭旅行",
    )
    history = LeaveStatusHistory(
        request=leave, from_status=None, to_status="pending", actor_id=applicant.id
    )
    saved = await repo.create(leave, history)
    assert saved.id is not None
    assert saved.status == "pending"
    assert len(saved.history) == 1
    assert saved.history[0].from_status is None


async def test_transition_updates_status_and_appends_history(db):
    repo = LeaveRepository(db)
    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    leave = await make_leave(db, applicant, approver)
    updated = await repo.transition(
        leave, "pending", "approved", approver.id, None
    )
    assert updated.status == "approved"
    assert len(updated.history) == 1
    entry = updated.history[0]
    assert entry.from_status == "pending"
    assert entry.to_status == "approved"
    assert entry.actor_id == approver.id


async def test_list_mine_filter_and_total(db):
    repo = LeaveRepository(db)
    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    await make_leave(db, applicant, approver, status="pending")
    await make_leave(db, applicant, approver, status="approved")
    await make_leave(db, await make_user(db, email="b@x.com"), approver)

    items, total = await repo.list_mine(applicant.id, None, 0, 20)
    assert total == 2
    items, total = await repo.list_mine(applicant.id, "approved", 0, 20)
    assert total == 1
    assert items[0].status == "approved"


async def test_list_all_department_and_status_filter(db):
    repo = LeaveRepository(db)
    dept = await make_department(db, name="技术部")
    other_dept = await make_department(db, name="市场部")
    approver = await make_user(db, email="m@x.com")
    in_dept = await make_user(db, email="a@x.com", department_id=dept.id)
    out_dept = await make_user(db, email="b@x.com", department_id=other_dept.id)
    await make_leave(db, in_dept, approver, status="pending")
    await make_leave(db, in_dept, approver, status="approved")
    await make_leave(db, out_dept, approver, status="pending")

    items, total = await repo.list_all(dept.id, None, None, None, None, 0, 20)
    assert total == 2
    items, total = await repo.list_all(None, "pending", None, None, None, 0, 20)
    assert total == 2
    items, total = await repo.list_all(dept.id, "pending", None, None, None, 0, 20)
    assert total == 1
    assert items[0].applicant_id == in_dept.id
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_leave_repository.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.repositories.leave_repository'`

- [ ] **Step 3: 创建 `backend/app/repositories/leave_repository.py`**

```python
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave import LeaveRequest, LeaveStatusHistory
from app.models.user import User


class LeaveRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, leave_id: uuid.UUID) -> LeaveRequest | None:
        return await self.db.get(LeaveRequest, leave_id)

    async def find_overlapping(
        self, applicant_id: uuid.UUID, start_date: date, end_date: date
    ) -> LeaveRequest | None:
        result = await self.db.execute(
            select(LeaveRequest).where(
                LeaveRequest.applicant_id == applicant_id,
                LeaveRequest.status.in_(["pending", "approved"]),
                LeaveRequest.end_date >= start_date,
                LeaveRequest.start_date <= end_date,
            )
        )
        return result.scalars().first()

    async def create(
        self, leave: LeaveRequest, history: LeaveStatusHistory
    ) -> LeaveRequest:
        self.db.add(leave)
        self.db.add(history)
        await self.db.commit()
        await self.db.refresh(leave)
        return leave

    async def transition(
        self,
        leave: LeaveRequest,
        from_status: str,
        to_status: str,
        actor_id: uuid.UUID,
        comment: str | None,
    ) -> LeaveRequest:
        leave.status = to_status
        self.db.add(
            LeaveStatusHistory(
                request_id=leave.id,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor_id,
                comment=comment,
            )
        )
        await self.db.commit()
        await self.db.refresh(leave)
        return leave

    async def list_mine(
        self, applicant_id: uuid.UUID, status: str | None, offset: int, limit: int
    ) -> tuple[list[LeaveRequest], int]:
        conditions = [LeaveRequest.applicant_id == applicant_id]
        if status is not None:
            conditions.append(LeaveRequest.status == status)
        total = (
            await self.db.execute(
                select(func.count()).select_from(LeaveRequest).where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(LeaveRequest)
            .where(*conditions)
            .order_by(LeaveRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_todo(
        self, approver_id: uuid.UUID, offset: int, limit: int
    ) -> tuple[list[LeaveRequest], int]:
        conditions = [
            LeaveRequest.approver_id == approver_id,
            LeaveRequest.status == "pending",
        ]
        total = (
            await self.db.execute(
                select(func.count()).select_from(LeaveRequest).where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(LeaveRequest)
            .where(*conditions)
            .order_by(LeaveRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_all(
        self,
        department_id: uuid.UUID | None,
        status: str | None,
        leave_type: str | None,
        start_from: date | None,
        end_to: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[LeaveRequest], int]:
        join_condition = LeaveRequest.applicant_id == User.id
        conditions = []
        if department_id is not None:
            conditions.append(User.department_id == department_id)
        if status is not None:
            conditions.append(LeaveRequest.status == status)
        if leave_type is not None:
            conditions.append(LeaveRequest.type == leave_type)
        if start_from is not None:
            conditions.append(LeaveRequest.end_date >= start_from)
        if end_to is not None:
            conditions.append(LeaveRequest.start_date <= end_to)
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(LeaveRequest)
                .join(User, join_condition)
                .where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(LeaveRequest)
            .join(User, join_condition)
            .where(*conditions)
            .order_by(LeaveRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_leave_repository.py -v`
Expected: PASS(6 个用例)

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/leave_repository.py backend/tests/test_leave_repository.py
git commit -m "feat(backend): 添加 LeaveRepository(重叠检测/状态迁移/列表查询)"
```

---

## Task 4: 请假 Schemas

**Files:**
- Create: `backend/app/schemas/leave.py`
- Test: `backend/tests/test_schemas_leave.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_schemas_leave.py`**

```python
import uuid
from datetime import date, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.leave import LeaveCreate, LeaveDetailResponse, LeaveHistoryItem


def test_leave_create_type_must_be_known():
    with pytest.raises(PydanticValidationError):
        LeaveCreate(
            type="婚假",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
            reason="x",
        )
    ok = LeaveCreate(
        type="annual",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
        reason="家庭旅行",
    )
    assert ok.type == "annual"


def test_leave_create_reason_length():
    with pytest.raises(PydanticValidationError):
        LeaveCreate(
            type="sick",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            reason="",
        )
    with pytest.raises(PydanticValidationError):
        LeaveCreate(
            type="sick",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            reason="x" * 501,
        )


def test_leave_history_item_from_attributes():
    from app.models.leave import LeaveStatusHistory

    entry = LeaveStatusHistory(
        request_id=uuid.uuid4(),
        from_status="pending",
        to_status="rejected",
        actor_id=uuid.uuid4(),
        comment="时间冲突",
    )
    entry.actor = type("U", (), {"id": uuid.uuid4(), "name": "主管"})()
    entry.created_at = datetime(2026, 8, 1, 12, 0, 0)
    item = LeaveHistoryItem.model_validate(entry)
    assert item.from_status == "pending"
    assert item.to_status == "rejected"
    assert item.comment == "时间冲突"
    assert item.actor.name == "主管"


def test_leave_detail_response_extends_base():
    fields = LeaveDetailResponse.model_fields
    for name in ("id", "type", "start_date", "end_date", "reason", "status",
                 "applicant", "approver", "created_at", "history"):
        assert name in fields
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_schemas_leave.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.schemas.leave'`

- [ ] **Step 3: 创建 `backend/app/schemas/leave.py`**

```python
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserBrief


class LeaveCreate(BaseModel):
    type: Literal["personal", "sick", "annual", "compensatory"]
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=500)


class LeaveReject(BaseModel):
    reason: str = Field(max_length=500)


class LeaveHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    actor: UserBrief
    comment: str | None
    created_at: datetime


class LeaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    start_date: date
    end_date: date
    reason: str
    status: str
    applicant: UserBrief
    approver: UserBrief
    created_at: datetime


class LeaveDetailResponse(LeaveResponse):
    history: list[LeaveHistoryItem]


class LeaveListResponse(BaseModel):
    items: list[LeaveResponse]
    total: int
    page: int
    page_size: int
```

注意:`LeaveReject.reason` 不设 min_length——空字符串由 service 层抛 `ValidationError("驳回必须填写原因")`,保证 422 走统一 `{"error":...}` 信封,而非 FastAPI 默认的 `{"detail":...}`。

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/leave.py backend/tests/test_schemas_leave.py
git commit -m "feat(backend): 添加请假审批 Schemas"
```

---

## Task 5: LeaveService

**Files:**
- Create: `backend/app/services/leave_service.py`
- Test: `backend/tests/test_leave_service.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_leave_service.py`**

```python
from datetime import date

import pytest

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.schemas.leave import LeaveCreate
from app.services.leave_service import LeaveService
from tests.conftest import ALL_PERMISSIONS, make_leave, make_user
from app.models.permission import Permission
from app.models.role import Role


def leave_create(start=date(2026, 8, 1), end=date(2026, 8, 2), type="personal"):
    return LeaveCreate(type=type, start_date=start, end_date=end, reason="私事")


async def make_applicant_with_manager(db, applicant_email="a@x.com", manager_email="m@x.com"):
    manager = await make_user(db, email=manager_email)
    applicant = await make_user(db, email=applicant_email, manager_id=manager.id)
    return applicant, manager


async def test_create_leave_snapshots_manager_and_writes_history(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    assert leave.status == "pending"
    assert leave.approver_id == manager.id
    assert len(leave.history) == 1
    assert leave.history[0].from_status is None
    assert leave.history[0].to_status == "pending"


async def test_create_leave_rejects_inverted_dates(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    with pytest.raises(ValidationError, match="开始日期不能晚于结束日期"):
        await svc.create_leave(
            leave_create(start=date(2026, 8, 3), end=date(2026, 8, 1)), applicant
        )


async def test_create_leave_rejects_without_manager(db):
    svc = LeaveService(db)
    applicant = await make_user(db, email="a@x.com")
    with pytest.raises(ValidationError, match="未设置直属上级,无法提交请假申请"):
        await svc.create_leave(leave_create(), applicant)


async def test_create_leave_rejects_overlap(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    await svc.create_leave(leave_create(date(2026, 8, 1), date(2026, 8, 3)), applicant)
    with pytest.raises(ConflictError, match="该时间段与已有请假申请重叠"):
        await svc.create_leave(leave_create(date(2026, 8, 3), date(2026, 8, 5)), applicant)


async def test_create_leave_allows_adjacent_and_inactive_overlap(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    await svc.create_leave(leave_create(date(2026, 8, 1), date(2026, 8, 3)), applicant)
    # 首尾相接不重叠
    await svc.create_leave(leave_create(date(2026, 8, 4), date(2026, 8, 5)), applicant)
    # rejected/canceled 不阻塞
    await make_leave(db, applicant, manager, status="rejected",
                     start_date=date(2026, 9, 1), end_date=date(2026, 9, 2))
    await svc.create_leave(leave_create(date(2026, 9, 1), date(2026, 9, 2)), applicant)


async def test_cancel_leave_success(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    canceled = await svc.cancel_leave(leave.id, applicant)
    assert canceled.status == "canceled"
    assert canceled.history[-1].to_status == "canceled"
    assert canceled.history[-1].actor_id == applicant.id


async def test_cancel_leave_forbidden_for_other_user(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    other = await make_user(db, email="b@x.com")
    with pytest.raises(ForbiddenError, match="只能撤回自己的请假申请"):
        await svc.cancel_leave(leave.id, other)


async def test_cancel_leave_conflict_when_not_pending(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    await svc.approve_leave(leave.id, manager)
    with pytest.raises(ConflictError, match="该申请已处理,无法操作"):
        await svc.cancel_leave(leave.id, applicant)


async def test_approve_leave_success(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    approved = await svc.approve_leave(leave.id, manager)
    assert approved.status == "approved"
    assert approved.history[-1].to_status == "approved"
    assert approved.history[-1].actor_id == manager.id


async def test_approve_leave_forbidden_for_non_approver(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    other_manager = await make_user(db, email="m2@x.com")
    with pytest.raises(ForbiddenError, match="只有审批人本人可以审批"):
        await svc.approve_leave(leave.id, other_manager)


async def test_reject_leave_requires_reason(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    with pytest.raises(ValidationError, match="驳回必须填写原因"):
        await svc.reject_leave(leave.id, manager, "  ")


async def test_reject_leave_success_with_comment(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    rejected = await svc.reject_leave(leave.id, manager, "时间冲突,请调整")
    assert rejected.status == "rejected"
    assert rejected.history[-1].to_status == "rejected"
    assert rejected.history[-1].comment == "时间冲突,请调整"


async def test_approver_snapshot_survives_manager_change(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    # 提交后换上级,在途单仍归原审批人
    applicant.manager_id = (await make_user(db, email="m2@x.com")).id
    await db.commit()
    approved = await svc.approve_leave(leave.id, manager)
    assert approved.status == "approved"


async def test_get_detail_scope(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)

    assert (await svc.get_detail(leave.id, applicant)).id == leave.id
    assert (await svc.get_detail(leave.id, manager)).id == leave.id

    perms = [Permission(code=c, name=n) for c, n in ALL_PERMISSIONS]
    admin = await make_user(
        db, email="admin@x.com",
        roles=[Role(code="admin", name="管理员", permissions=perms)],
    )
    assert (await svc.get_detail(leave.id, admin)).id == leave.id

    outsider = await make_user(db, email="b@x.com")
    with pytest.raises(ForbiddenError, match="无权查看该请假申请"):
        await svc.get_detail(leave.id, outsider)


async def test_get_detail_not_found(db):
    import uuid

    svc = LeaveService(db)
    user = await make_user(db, email="a@x.com")
    with pytest.raises(NotFoundError, match="请假申请不存在"):
        await svc.get_detail(uuid.uuid4(), user)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_leave_service.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.services.leave_service'`

- [ ] **Step 3: 创建 `backend/app/services/leave_service.py`**

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.leave import LeaveRequest, LeaveStatusHistory
from app.models.user import User
from app.repositories.leave_repository import LeaveRepository
from app.schemas.leave import LeaveCreate


class LeaveService:
    def __init__(self, db: AsyncSession):
        self.leaves = LeaveRepository(db)

    async def create_leave(
        self, data: LeaveCreate, applicant: User
    ) -> LeaveRequest:
        if data.start_date > data.end_date:
            raise ValidationError("开始日期不能晚于结束日期")
        if applicant.manager_id is None:
            raise ValidationError("未设置直属上级,无法提交请假申请")
        if await self.leaves.find_overlapping(
            applicant.id, data.start_date, data.end_date
        ):
            raise ConflictError("该时间段与已有请假申请重叠")
        leave = LeaveRequest(
            applicant_id=applicant.id,
            approver_id=applicant.manager_id,
            type=data.type,
            start_date=data.start_date,
            end_date=data.end_date,
            reason=data.reason,
        )
        history = LeaveStatusHistory(
            request=leave,
            from_status=None,
            to_status="pending",
            actor_id=applicant.id,
        )
        return await self.leaves.create(leave, history)

    async def get_detail(self, leave_id: uuid.UUID, user: User) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        perms = {p.code for role in user.roles for p in role.permissions}
        if (
            user.id != leave.applicant_id
            and user.id != leave.approver_id
            and "leave:list_all" not in perms
        ):
            raise ForbiddenError("无权查看该请假申请")
        return leave

    async def cancel_leave(self, leave_id: uuid.UUID, user: User) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        if leave.applicant_id != user.id:
            raise ForbiddenError("只能撤回自己的请假申请")
        self._check_pending(leave)
        return await self.leaves.transition(
            leave, "pending", "canceled", user.id, None
        )

    async def approve_leave(self, leave_id: uuid.UUID, user: User) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        self._check_approver(leave, user)
        self._check_pending(leave)
        return await self.leaves.transition(
            leave, "pending", "approved", user.id, None
        )

    async def reject_leave(
        self, leave_id: uuid.UUID, user: User, reason: str
    ) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        self._check_approver(leave, user)
        self._check_pending(leave)
        if not reason.strip():
            raise ValidationError("驳回必须填写原因")
        return await self.leaves.transition(
            leave, "pending", "rejected", user.id, reason
        )

    async def list_mine(
        self, user: User, status: str | None, page: int, page_size: int
    ) -> tuple[list[LeaveRequest], int]:
        return await self.leaves.list_mine(
            user.id, status, (page - 1) * page_size, page_size
        )

    async def list_todo(
        self, user: User, page: int, page_size: int
    ) -> tuple[list[LeaveRequest], int]:
        return await self.leaves.list_todo(
            user.id, (page - 1) * page_size, page_size
        )

    async def list_all(
        self,
        department_id: uuid.UUID | None,
        status: str | None,
        leave_type: str | None,
        start_from,
        end_to,
        page: int,
        page_size: int,
    ) -> tuple[list[LeaveRequest], int]:
        return await self.leaves.list_all(
            department_id,
            status,
            leave_type,
            start_from,
            end_to,
            (page - 1) * page_size,
            page_size,
        )

    async def _get_or_404(self, leave_id: uuid.UUID) -> LeaveRequest:
        leave = await self.leaves.get_by_id(leave_id)
        if leave is None:
            raise NotFoundError("请假申请不存在")
        return leave

    def _check_pending(self, leave: LeaveRequest) -> None:
        if leave.status != "pending":
            raise ConflictError("该申请已处理,无法操作")

    def _check_approver(self, leave: LeaveRequest, user: User) -> None:
        if leave.approver_id != user.id:
            raise ForbiddenError("只有审批人本人可以审批")
```

注意:
- 错误顺序:404 → 403(归属/审批人) → 409(非 pending) → 422(驳回原因),与测试断言对应
- `history` 关系按 created_at 升序;测试中 `history[-1]` 取最新一行。SQLite 的 CURRENT_TIMESTAMP 为秒级,同一测试内多行可能同秒——排序键相同的情况下 SQLite 通常按插入序返回,本模块测试断言均只依赖"最后一行"或集合内容,不做全序断言

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_leave_service.py -v`
Expected: PASS(15 个用例)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/leave_service.py backend/tests/test_leave_service.py
git commit -m "feat(backend): 添加 LeaveService(状态机/重叠校验/审批人快照/数据归属)"
```

---

## Task 6: Leaves 路由

**Files:**
- Create: `backend/app/api/v1/leaves.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_leaves_api.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_leaves_api.py`**

```python
import pytest
from sqlalchemy import select

from app.models.permission import Permission
from tests.conftest import login_token, make_department, make_permission, make_role, make_user


async def leave_permissions(db):
    """取或建本模块 3 个权限点。同一测试内多次调用、或与 admin_client
    fixture(建 ALL_PERMISSIONS 全部权限)共存时不会触发 code 唯一冲突。"""
    existing = {p.code: p for p in (await db.execute(select(Permission))).scalars()}
    perms = []
    for code, name in [
        ("leave:create", "提交/撤回请假申请"),
        ("leave:list", "查看我的申请"),
        ("leave:approve", "审批请假申请"),
    ]:
        perms.append(existing.get(code) or await make_permission(db, code=code, name=name))
    return perms


async def make_manager_client(db, client, email="mgr@x.com"):
    perms = await leave_permissions(db)
    role = await make_role(db, code=f"manager-{email}", name="部门主管", permissions=perms)
    manager = await make_user(db, email=email, password="Passw0rd!", roles=[role])
    token = await login_token(client, email, "Passw0rd!")
    return manager, {"Authorization": f"Bearer {token}"}


async def make_employee_client(db, client, manager, email="emp@x.com"):
    perms = await leave_permissions(db)
    role = await make_role(db, code=f"employee-{email}", name="员工", permissions=perms[:2])
    user = await make_user(
        db, email=email, password="Passw0rd!", roles=[role], manager_id=manager.id
    )
    token = await login_token(client, email, "Passw0rd!")
    return user, {"Authorization": f"Bearer {token}"}


LEAVE_JSON = {
    "type": "annual",
    "start_date": "2026-08-01",
    "end_date": "2026-08-03",
    "reason": "家庭旅行",
}


async def test_create_leave_201_snapshots_approver(client, db):
    manager, mgr_headers = await make_manager_client(db, client)
    user, headers = await make_employee_client(db, client, manager)
    resp = await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["approver"]["id"] == str(manager.id)
    assert body["applicant"]["id"] == str(user.id)


async def test_create_leave_requires_auth(client):
    resp = await client.post("/api/v1/leaves", json=LEAVE_JSON)
    assert resp.status_code == 401


async def test_create_leave_requires_permission(employee_client):
    resp = await employee_client.post("/api/v1/leaves", json=LEAVE_JSON)
    assert resp.status_code == 403


async def test_create_leave_overlap_409(client, db):
    manager, _ = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    resp = await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    assert resp.status_code == 201
    resp = await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    assert resp.status_code == 409


async def test_create_leave_inverted_dates_422(client, db):
    manager, _ = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    bad = {**LEAVE_JSON, "start_date": "2026-08-03", "end_date": "2026-08-01"}
    resp = await client.post("/api/v1/leaves", json=bad, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_cancel_leave(client, db):
    manager, _ = await make_manager_client(db, client)
    user, headers = await make_employee_client(db, client, manager)
    leave = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    ).json()
    resp = await client.post(f"/api/v1/leaves/{leave['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "canceled"


async def test_cancel_leave_not_owner_403(client, db):
    manager, mgr_headers = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    leave = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    ).json()
    resp = await client.post(
        f"/api/v1/leaves/{leave['id']}/cancel", headers=mgr_headers
    )
    assert resp.status_code == 403


async def test_approve_leave_by_manager(client, db):
    manager, mgr_headers = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    leave = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    ).json()
    resp = await client.post(
        f"/api/v1/leaves/{leave['id']}/approve", headers=mgr_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_approve_leave_not_approver_403(client, db):
    manager, _ = await make_manager_client(db, client)
    _, other_headers = await make_manager_client(db, client, email="mgr2@x.com")
    _, headers = await make_employee_client(db, client, manager)
    leave = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    ).json()
    resp = await client.post(
        f"/api/v1/leaves/{leave['id']}/approve", headers=other_headers
    )
    assert resp.status_code == 403


async def test_reject_leave_requires_reason_422(client, db):
    manager, mgr_headers = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    leave = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    ).json()
    resp = await client.post(
        f"/api/v1/leaves/{leave['id']}/reject",
        json={"reason": ""},
        headers=mgr_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_reject_leave_success_keeps_comment_in_history(client, db):
    manager, mgr_headers = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    leave = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    ).json()
    resp = await client.post(
        f"/api/v1/leaves/{leave['id']}/reject",
        json={"reason": "时间冲突"},
        headers=mgr_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    detail = await client.get(f"/api/v1/leaves/{leave['id']}", headers=headers)
    history = detail.json()["history"]
    assert history[-1]["to_status"] == "rejected"
    assert history[-1]["comment"] == "时间冲突"


async def test_list_mine_with_status_filter(client, db):
    manager, mgr_headers = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    leave2 = (
        await client.post(
            "/api/v1/leaves",
            json={**LEAVE_JSON, "start_date": "2026-09-01", "end_date": "2026-09-02"},
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/leaves/{leave2['id']}/approve", headers=mgr_headers)

    resp = await client.get("/api/v1/leaves/mine", headers=headers)
    assert resp.json()["total"] == 2
    resp = await client.get("/api/v1/leaves/mine?status=approved", headers=headers)
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["status"] == "approved"


async def test_list_todo(client, db):
    manager, mgr_headers = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)

    resp = await client.get("/api/v1/leaves/todo", headers=mgr_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    resp = await client.get("/api/v1/leaves/todo", headers=headers)
    assert resp.status_code == 403


async def test_list_all_admin_and_filters(admin_client, client, db):
    manager, _ = await make_manager_client(db, client)
    dept = await make_department(db, name="技术部")
    user, headers = await make_employee_client(db, client, manager)
    user.department_id = dept.id
    await db.commit()
    await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)

    resp = await admin_client.get("/api/v1/leaves")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    resp = await admin_client.get(f"/api/v1/leaves?department_id={dept.id}")
    assert resp.json()["total"] == 1
    resp = await admin_client.get("/api/v1/leaves?status=approved")
    assert resp.json()["total"] == 0
    resp = await client.get("/api/v1/leaves", headers=headers)
    assert resp.status_code == 403


async def test_get_detail_identities(client, db):
    manager, mgr_headers = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    _, stranger_headers = await make_employee_client(db, client, manager, email="emp2@x.com")
    leave = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    ).json()

    assert (await client.get(f"/api/v1/leaves/{leave['id']}", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/leaves/{leave['id']}", headers=mgr_headers)).status_code == 200
    resp = await client.get(f"/api/v1/leaves/{leave['id']}", headers=stranger_headers)
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "method,url",
    [
        ("POST", "/api/v1/leaves"),
        ("GET", "/api/v1/leaves/mine"),
        ("GET", "/api/v1/leaves/todo"),
        ("GET", "/api/v1/leaves"),
    ],
)
async def test_leave_endpoints_reject_anonymous(client, method, url):
    resp = await client.request(method, url)
    assert resp.status_code == 401
```

注意:`make_role` 的 code 参数带 email 后缀是为了避免同一测试内多次调用产生 code 唯一冲突(如 `test_approve_leave_not_approver_403` 建两个 manager);`make_employee_client` 第二个员工(emp2)没有部门,仅用于详情越权用例。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_leaves_api.py -v`
Expected: FAIL,404 Not Found(路由未注册)

- [ ] **Step 3: 创建 `backend/app/api/v1/leaves.py`**

```python
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.models.user import User
from app.schemas.leave import (
    LeaveCreate,
    LeaveDetailResponse,
    LeaveListResponse,
    LeaveReject,
    LeaveResponse,
)
from app.services.leave_service import LeaveService

router = APIRouter(prefix="/leaves", tags=["leaves"])


def to_response(leave) -> LeaveResponse:
    return LeaveResponse.model_validate(leave)


@router.post("", response_model=LeaveResponse, status_code=201)
async def create_leave(
    data: LeaveCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:create")),
):
    return await LeaveService(db).create_leave(data, current_user)


@router.get("/mine", response_model=LeaveListResponse)
async def list_mine(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:list")),
):
    items, total = await LeaveService(db).list_mine(
        current_user, status, page, page_size
    )
    return LeaveListResponse(
        items=[to_response(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/todo", response_model=LeaveListResponse)
async def list_todo(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:approve")),
):
    items, total = await LeaveService(db).list_todo(current_user, page, page_size)
    return LeaveListResponse(
        items=[to_response(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=LeaveListResponse)
async def list_all(
    department_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    type: str | None = Query(None),
    start_from: date | None = Query(None),
    end_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leave:list_all")),
):
    items, total = await LeaveService(db).list_all(
        department_id, status, type, start_from, end_to, page, page_size
    )
    return LeaveListResponse(
        items=[to_response(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{leave_id}", response_model=LeaveDetailResponse)
async def get_detail(
    leave_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:list")),
):
    return await LeaveService(db).get_detail(leave_id, current_user)


@router.post("/{leave_id}/cancel", response_model=LeaveResponse)
async def cancel_leave(
    leave_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:create")),
):
    return await LeaveService(db).cancel_leave(leave_id, current_user)


@router.post("/{leave_id}/approve", response_model=LeaveResponse)
async def approve_leave(
    leave_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:approve")),
):
    return await LeaveService(db).approve_leave(leave_id, current_user)


@router.post("/{leave_id}/reject", response_model=LeaveResponse)
async def reject_leave(
    leave_id: uuid.UUID,
    data: LeaveReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("leave:approve")),
):
    return await LeaveService(db).reject_leave(leave_id, current_user, data.reason)
```

注意:`/mine`、`/todo`、``(list_all) 必须声明在 `/{leave_id}` **之前**——FastAPI 按声明顺序匹配,否则 "mine"/"todo" 会被 `/{leave_id}` 捕获并按 UUID 解析报 422。

- [ ] **Step 4: 修改 `backend/app/main.py`**

导入行改为:

```python
from app.api.v1 import auth, departments, leaves, roles, users
```

路由注册追加(在 `departments.router` 之后):

```python
api_v1.include_router(leaves.router)
```

- [ ] **Step 5: 运行确认通过 + 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/leaves.py backend/app/main.py backend/tests/test_leaves_api.py
git commit -m "feat(backend): 添加 Leaves 路由(申请/撤回/审批/三类查询)"
```

---

## Task 7: Seed 更新(新权限点 + 角色权限映射)

**Files:**
- Modify: `backend/scripts/seed.py`
- Modify: `backend/tests/test_seed.py`

- [ ] **Step 1: 先看现有 `backend/tests/test_seed.py` 的用例结构,追加失败测试**

```python
async def test_seed_assigns_leave_permissions(db):
    await seed(db)

    perms = {p.code for p in (await db.execute(select(Permission))).scalars()}
    expected = {"leave:create", "leave:list", "leave:approve", "leave:list_all"}
    assert expected <= perms

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    admin_perms = {p.code for p in roles["admin"].permissions}
    manager_perms = {p.code for p in roles["manager"].permissions}
    employee_perms = {p.code for p in roles["employee"].permissions}
    assert expected <= admin_perms
    assert {"leave:create", "leave:list", "leave:approve"} <= manager_perms
    assert "leave:list_all" not in manager_perms
    assert employee_perms == {"leave:create", "leave:list"}
```

(`test_seed.py` 顶部已导入 `select`、`Permission`、`Role`、`seed`,直接沿用,无需新增导入。)

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_seed.py -v`
Expected: FAIL(断言不成立,新权限点不存在)

- [ ] **Step 3: 修改 `backend/scripts/seed.py`**

`PERMISSIONS` 列表追加:

```python
    ("leave:create", "提交/撤回请假申请"),
    ("leave:list", "查看我的申请"),
    ("leave:approve", "审批请假申请"),
    ("leave:list_all", "查看全部审批记录"),
```

`ROLE_PERMISSIONS` 更新为:

```python
ROLE_PERMISSIONS: dict[str, list[str] | None] = {
    "admin": None,
    "manager": [
        "department:list",
        "department:members",
        "leave:create",
        "leave:list",
        "leave:approve",
    ],
    "employee": ["leave:create", "leave:list"],
}
```

- [ ] **Step 4: 同步修正既有 seed 测试断言**

以下既有断言会因角色权限集合扩大而失败,按新映射更新(这是设计决策内的预期变更,不是绕过测试):

1. `ALL_PERMISSION_CODES` 常量(文件顶部)追加 4 项:

```python
ALL_PERMISSION_CODES = {
    "user:create", "user:list", "user:update",
    "user:disable", "role:list", "role:assign",
    "department:create", "department:update", "department:delete",
    "department:list", "department:members",
    "leave:create", "leave:list", "leave:approve", "leave:list_all",
}
```

2. `test_seed_creates_permissions_roles_and_admin` 中 manager 断言改为:

```python
    assert {p.code for p in roles["manager"].permissions} == {
        "department:list",
        "department:members",
        "leave:create",
        "leave:list",
        "leave:approve",
    }
```

3. `test_seed_assigns_department_permissions` 中两处断言改为:

```python
    assert DEPARTMENT_PERMISSION_CODES <= manager_perms
    assert {p.code for p in roles["employee"].permissions} == {
        "leave:create",
        "leave:list",
    }
```

(原来分别是 `manager_perms == {"department:list", "department:members"}` 和 `roles["employee"].permissions == []`。)

4. `test_seed_repairs_manager_permissions_on_rerun` 中 manager 断言改为:

```python
    assert {p.code for p in role.permissions} == {
        "department:list",
        "department:members",
        "leave:create",
        "leave:list",
        "leave:approve",
    }
```

- [ ] **Step 5: 运行确认通过 + 全量回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed

- [ ] **Step 6: 在开发库重跑 seed 验证幂等**

前置:`docker compose up -d db` 且已完成迁移

Run: `cd backend && python -m scripts.seed && python -m scripts.seed`
Expected: 两次均输出 `Seed 完成,admin 账号: ...`,无异常

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/seed.py backend/tests/test_seed.py
git commit -m "feat(backend): seed 增加请假权限点与角色权限映射"
```

---

## Task 8: 全量验收

- [ ] **Step 1: 全量测试**

Run: `cd backend && python -m pytest -v`
Expected: 全部通过,0 failed

- [ ] **Step 2: 对照 spec §10 验收标准逐项确认**

- 员工可提交申请、审批人自动为直属上级:`test_create_leave_snapshots_manager_and_writes_history`、`test_create_leave_201_snapshots_approver`
- 开始时间不能晚于结束时间(422):`test_create_leave_rejects_inverted_dates`、`test_create_leave_inverted_dates_422`
- 区间不重叠(409):`test_find_overlapping_detects`、`test_create_leave_rejects_overlap`、`test_create_leave_overlap_409`
- 通过/驳回留痕、驳回必填原因:`test_approve_leave_success`、`test_reject_leave_success_with_comment`、`test_reject_leave_requires_reason_422`
- 待审批可撤回:`test_cancel_leave_success`、`test_cancel_leave`
- 三类查询:`test_list_mine_with_status_filter`、`test_list_todo`、`test_list_all_admin_and_filters`

- [ ] **Step 3: 勾选 `docs/superpowers/specs/2026-07-24-leave-approval-design.md` §10 的全部 checkbox(`- [ ]` → `- [x]`)**

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-24-leave-approval-design.md
git commit -m "test(backend): 请假审批模块全量验收通过,勾选 spec 验收标准"
```
