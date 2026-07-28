# 报销审批模块(后端,含二级审批)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现报销申请提交(金额/类型/说明/附件凭证)、一级(主管)审批、超阈值二级(HR/Admin 权限池)审批、驳回/撤回、查询与附件鉴权下载,并在四个触发点同步生成站内通知。

**Architecture:** 对称复制请假模式:expense_requests + expense_status_history(只追加)+ expense_attachments 三表;api/v1 → services → repositories → models 分层;通知行由 ExpenseService 在动作点调用 NotificationService 生成,只 `db.add()` 不 commit,随动作同事务提交。状态机:`pending_l1 → pending_l2 → approved`,任一级驳回 → `rejected`,撤回 → `cancelled`;`pending_l2` 时 `approver_id=NULL` 表达权限池。

**Tech Stack:** FastAPI + SQLAlchemy Async + Alembic + pydantic v2;pytest + httpx AsyncClient + 内存 SQLite。

## Global Constraints

- 工作分支:`feature/backend-expense`(已在此分支,不切分支)
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- Commit message:中文 Conventional Commits(参照 git log 现有风格,如 `feat(backend): ...`)
- 设计依据:`docs/superpowers/specs/2026-07-28-expense-approval-design.md`,实现必须与 spec 一致;触发场景严格四个(submit→主管;L1 通过且超阈值→扇出 l2 权限池;终审通过→申请人;任一级驳回→申请人;撤回不通知)
- 不改 frontend/、不引入新 Python 依赖;seed 只追加 5 个 expense 权限点及角色映射(Task 6)
- 通知生成只做 `db.add()`,commit 一律由 ExpenseRepository 既有方法完成(同事务原子性的实现关键);reject 模板必须过 `_clamp_content`
- 阈值一律读 `settings.EXPENSE_L2_THRESHOLD`,判定只发生在 L1 approve 动作点(`amount > 阈值` → 转 pending_l2),**禁止**写死 2000
- 测试库为内存 SQLite,迁移 DDL 须 SQLite 兼容(server_default 用 `sa.text("(CURRENT_TIMESTAMP)")`,参照 b4c7e1a9d253 迁移)
- 运行 pytest 的工作目录是 `backend/`(`pytest.ini` 在其中,asyncio_mode=auto)
- 状态值精确为:`pending_l1` / `pending_l2` / `approved` / `rejected` / `cancelled`(注意撤回是两个 l,与请假的 `canceled` 不同,以 spec 为准)

---

### Task 1: Expense 三表模型 + Alembic 迁移

**Files:**
- Create: `backend/app/models/expense.py`
- Create: `backend/alembic/versions/c8d3f2a1b947_add_expense_approval.py`
- Modify: `backend/alembic/env.py:11`(import 行加 expense)
- Modify: `backend/tests/conftest.py`(import 区加 expense 模型)
- Test: `backend/tests/test_expense_model.py`

**Interfaces:**
- Consumes: `app.models.base.Base` / `TimestampMixin`(ExpenseRequest 挂,另两表不挂)
- Produces: `ExpenseRequest`(id/applicant_id/type/amount/reason/status/approver_id可空 + applicant/approver/history/attachments 关系)、`ExpenseStatusHistory`、`ExpenseAttachment`;后续所有任务依赖

- [ ] **Step 1: Write the failing test**

创建 `backend/tests/test_expense_model.py`:

```python
from decimal import Decimal

from app.core.security import hash_password
from app.models.user import User


async def test_expense_persist(db):
    from app.models.expense import ExpenseAttachment, ExpenseRequest

    user = User(
        email="e@x.com", name="E", hashed_password=hash_password("Passw0rd!")
    )
    mgr = User(
        email="m@x.com", name="M", hashed_password=hash_password("Passw0rd!")
    )
    db.add_all([user, mgr])
    await db.commit()
    await db.refresh(user)
    await db.refresh(mgr)

    e = ExpenseRequest(
        applicant_id=user.id,
        approver_id=mgr.id,
        type="travel",
        amount=Decimal("1999.50"),
        reason="出差打车",
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)

    assert e.id is not None
    assert e.status == "pending_l1"
    assert e.amount == Decimal("1999.50")
    assert e.created_at is not None

    att = ExpenseAttachment(
        expense_id=e.id,
        filename="a.png",
        stored_path=f"expenses/{e.id}/x.png",
        content_type="image/png",
        size_bytes=8,
    )
    db.add(att)
    await db.commit()
    await db.refresh(e)
    assert len(e.attachments) == 1
    assert e.attachments[0].filename == "a.png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_expense_model.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.models.expense'`

- [ ] **Step 3: Write the models**

创建 `backend/app/models/expense.py`:

```python
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ExpenseRequest(Base, TimestampMixin):
    __tablename__ = "expense_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(20), default="pending_l1", index=True
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )

    applicant: Mapped["User"] = relationship(
        foreign_keys=[applicant_id], lazy="selectin"
    )
    approver: Mapped["User | None"] = relationship(
        foreign_keys=[approver_id], lazy="selectin"
    )
    history: Mapped[list["ExpenseStatusHistory"]] = relationship(
        back_populates="request",
        lazy="selectin",
        order_by="ExpenseStatusHistory.created_at",
    )
    attachments: Mapped[list["ExpenseAttachment"]] = relationship(
        back_populates="expense", lazy="selectin"
    )


class ExpenseStatusHistory(Base):
    __tablename__ = "expense_status_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("expense_requests.id", ondelete="RESTRICT"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    comment: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    request: Mapped[ExpenseRequest] = relationship(back_populates="history")
    actor: Mapped["User"] = relationship(lazy="selectin")


class ExpenseAttachment(Base):
    __tablename__ = "expense_attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    expense_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("expense_requests.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    expense: Mapped[ExpenseRequest] = relationship(back_populates="attachments")
```

修改 `backend/alembic/env.py:11`,import 行加入 expense:

```python
from app.models import associations, department, expense, leave, notification, permission, role, user  # noqa: F401
```

修改 `backend/tests/conftest.py`,在 `from app.models.leave import LeaveRequest` 一行后加:

```python
from app.models.expense import ExpenseAttachment, ExpenseRequest  # noqa: F401  # 注册进 metadata,create_all 用
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_expense_model.py -v`
Expected: PASS

- [ ] **Step 5: Write the migration**

创建 `backend/alembic/versions/c8d3f2a1b947_add_expense_approval.py`(down_revision 为当前 head `b4c7e1a9d253`):

```python
"""add expense approval

Revision ID: c8d3f2a1b947
Revises: b4c7e1a9d253
Create Date: 2026-07-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d3f2a1b947"
down_revision: Union[str, None] = "b4c7e1a9d253"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expense_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("applicant_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approver_id", sa.Uuid(), nullable=True),
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
        op.f("ix_expense_requests_applicant_id"),
        "expense_requests",
        ["applicant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expense_requests_approver_id"),
        "expense_requests",
        ["approver_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expense_requests_status"), "expense_requests", ["status"], unique=False
    )
    op.create_table(
        "expense_status_history",
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
            ["request_id"], ["expense_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expense_status_history_request_id"),
        "expense_status_history",
        ["request_id"],
        unique=False,
    )
    op.create_table(
        "expense_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("expense_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["expense_id"], ["expense_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expense_attachments_expense_id"),
        "expense_attachments",
        ["expense_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_expense_attachments_expense_id"), table_name="expense_attachments"
    )
    op.drop_table("expense_attachments")
    op.drop_index(
        op.f("ix_expense_status_history_request_id"),
        table_name="expense_status_history",
    )
    op.drop_table("expense_status_history")
    op.drop_index(op.f("ix_expense_requests_status"), table_name="expense_requests")
    op.drop_index(
        op.f("ix_expense_requests_approver_id"), table_name="expense_requests"
    )
    op.drop_index(
        op.f("ix_expense_requests_applicant_id"), table_name="expense_requests"
    )
    op.drop_table("expense_requests")
```

- [ ] **Step 6: Verify migration on dev DB**

前置:确认开发库在跑(`docker compose up -d db`,若已在跑跳过)。

Run: `cd backend && alembic upgrade head && alembic check`
Expected: upgrade 应用 `c8d3f2a1b947`;`alembic check` 输出无漂移(No new upgrade operations detected)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/expense.py backend/alembic/versions/c8d3f2a1b947_add_expense_approval.py backend/alembic/env.py backend/tests/conftest.py backend/tests/test_expense_model.py
git commit -m "feat(backend): 新增 Expense 三表模型与迁移"
```

---

### Task 2: 配置项 + schemas + conftest 工厂 + ExpenseRepository

**Files:**
- Modify: `backend/app/core/config.py`(加两个配置项)
- Create: `backend/app/schemas/expense.py`
- Modify: `backend/tests/conftest.py`(加 `from decimal import Decimal` + make_expense 工厂)
- Create: `backend/app/repositories/expense_repository.py`
- Test: `backend/tests/test_expense_repository.py`

**Interfaces:**
- Consumes: Task 1 三表模型
- Produces:
  - `settings.EXPENSE_L2_THRESHOLD: Decimal = 2000`、`settings.UPLOAD_DIR: str = "uploads"`
  - `ExpenseRepository(db)`:`get_by_id`、`create(expense, history, attachments)`、`transition(expense, from_status, to_status, actor_id, comment, clear_approver=False)`、`list_mine(applicant_id, status, expense_type, offset, limit)`、`list_todo(user_id, can_l1, can_l2, offset, limit)`、`list_all(department_id, status, expense_type, start_from, end_to, offset, limit)`、`get_attachment(attachment_id)`
  - schemas:`ExpenseReject/ExpenseHistoryItem/ExpenseAttachmentItem/ExpenseResponse/ExpenseDetailResponse/ExpenseListResponse`
  - conftest 工厂 `make_expense(db, applicant, approver, type=, amount=, reason=, status=)`

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_expense_repository.py`:

```python
from datetime import datetime
from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError
from app.models.expense import ExpenseStatusHistory
from tests.conftest import make_expense, make_user


async def test_list_mine_filter_and_pagination(db):
    from app.repositories.expense_repository import ExpenseRepository

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_expense(db, u1, None, type="travel")
    await make_expense(db, u1, None, type="office", status="approved")
    await make_expense(db, u2, None, type="travel")

    repo = ExpenseRepository(db)
    _, total_all = await repo.list_mine(u1.id, None, None, 0, 20)
    _, total_travel = await repo.list_mine(u1.id, None, "travel", 0, 20)
    _, total_approved = await repo.list_mine(u1.id, "approved", None, 0, 20)
    assert (total_all, total_travel, total_approved) == (2, 1, 1)

    items, total = await repo.list_mine(u1.id, None, None, 1, 1)
    assert total == 2
    assert len(items) == 1


async def test_list_todo_l1_only(db):
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    await make_expense(db, emp, mgr, status="pending_l1")
    await make_expense(db, emp, None, status="pending_l2")

    items, total = await ExpenseRepository(db).list_todo(
        mgr.id, True, False, 0, 20
    )
    assert total == 1
    assert items[0].status == "pending_l1"


async def test_list_todo_l2_pool_and_merged(db):
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    other_mgr = await make_user(db, email="om@x.com")
    await make_expense(db, emp, mgr, status="pending_l1")
    await make_expense(db, emp, None, status="pending_l2")

    repo = ExpenseRepository(db)
    # L2 视角:看到所有 pending_l2,不看别人的 pending_l1
    items, total = await repo.list_todo(other_mgr.id, False, True, 0, 20)
    assert total == 1
    assert items[0].status == "pending_l2"
    # 合并视角:mgr 两种都有权限 → 自己的 pending_l1 + 全部 pending_l2
    _, total = await repo.list_todo(mgr.id, True, True, 0, 20)
    assert total == 2


async def test_list_all_filters(db):
    from app.repositories.expense_repository import ExpenseRepository

    dept = await make_user(db, email="d@x.com")  # 占位,部门过滤另测
    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    await make_expense(db, emp, mgr, type="travel", status="pending_l1")
    await make_expense(db, emp, mgr, type="office", status="rejected")

    repo = ExpenseRepository(db)
    _, total_all = await repo.list_all(None, None, None, None, None, 0, 20)
    _, total_rejected = await repo.list_all(None, "rejected", None, None, None, 0, 20)
    _, total_office = await repo.list_all(None, None, "office", None, None, 0, 20)
    _, total_none = await repo.list_all(None, "approved", None, None, None, 0, 20)
    assert (total_all, total_rejected, total_office, total_none) == (2, 1, 1, 0)


async def test_transition_optimistic_lock(db):
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await make_expense(db, emp, mgr, status="pending_l1")

    repo = ExpenseRepository(db)
    with pytest.raises(ConflictError):
        await repo.transition(e, "approved", "rejected", mgr.id, None)


async def test_transition_clear_approver(db):
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await make_expense(db, emp, mgr, status="pending_l1")

    repo = ExpenseRepository(db)
    e = await repo.transition(
        e, "pending_l1", "pending_l2", mgr.id, None, clear_approver=True
    )
    assert e.status == "pending_l2"
    assert e.approver_id is None
    assert len(e.history) == 1
    assert e.history[0].from_status == "pending_l1"
    assert e.history[0].to_status == "pending_l2"
    assert e.history[0].actor_id == mgr.id


async def test_create_persists_attachments_and_history(db):
    from app.models.expense import ExpenseAttachment, ExpenseRequest
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = ExpenseRequest(
        applicant_id=emp.id,
        approver_id=mgr.id,
        type="travel",
        amount=Decimal("100.00"),
        reason="x",
    )
    history = ExpenseStatusHistory(
        request=e, from_status=None, to_status="pending_l1", actor_id=emp.id
    )
    att = ExpenseAttachment(
        expense=e,
        filename="a.png",
        stored_path="expenses/x/y.png",
        content_type="image/png",
        size_bytes=3,
    )
    repo = ExpenseRepository(db)
    e = await repo.create(e, history, [att])
    assert e.id is not None
    assert len(e.history) == 1
    assert len(e.attachments) == 1
    got = await repo.get_attachment(e.attachments[0].id)
    assert got is not None and got.filename == "a.png"
```

(注意:`ExpenseAttachment(expense=e, ...)` 用关系赋值,commit 后外键自动落库。)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_expense_repository.py -v`
Expected: FAIL,conftest 无 `make_expense`(ImportError)

- [ ] **Step 3: Add config + schemas + factory + repository**

修改 `backend/app/core/config.py`:文件顶部加 `from decimal import Decimal`,Settings 类中追加:

```python
    EXPENSE_L2_THRESHOLD: Decimal = 2000
    UPLOAD_DIR: str = "uploads"
```

创建 `backend/app/schemas/expense.py`:

```python
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserBrief


class ExpenseReject(BaseModel):
    reason: str = Field(max_length=500)


class ExpenseHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    actor: UserBrief
    comment: str | None
    created_at: datetime


class ExpenseAttachmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    amount: Decimal
    reason: str
    status: str
    applicant_id: uuid.UUID
    approver_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ExpenseDetailResponse(ExpenseResponse):
    history: list[ExpenseHistoryItem]
    attachments: list[ExpenseAttachmentItem]


class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse]
    total: int
    page: int
    page_size: int
```

修改 `backend/tests/conftest.py`:文件顶部 import 区加 `from decimal import Decimal`,并在 `make_leave` 函数后追加:

```python
async def make_expense(
    db,
    applicant: User,
    approver: User | None,
    type="travel",
    amount=Decimal("1999.00"),
    reason="出差交通",
    status="pending_l1",
) -> ExpenseRequest:
    e = ExpenseRequest(
        applicant_id=applicant.id,
        approver_id=approver.id if approver else None,
        type=type,
        amount=amount,
        reason=reason,
        status=status,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e
```

创建 `backend/app/repositories/expense_repository.py`:

```python
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.expense import (
    ExpenseAttachment,
    ExpenseRequest,
    ExpenseStatusHistory,
)
from app.models.user import User


class ExpenseRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, expense_id: uuid.UUID) -> ExpenseRequest | None:
        return await self.db.get(ExpenseRequest, expense_id)

    async def get_attachment(
        self, attachment_id: uuid.UUID
    ) -> ExpenseAttachment | None:
        return await self.db.get(ExpenseAttachment, attachment_id)

    async def create(
        self,
        expense: ExpenseRequest,
        history: ExpenseStatusHistory,
        attachments: list[ExpenseAttachment],
    ) -> ExpenseRequest:
        self.db.add(expense)
        self.db.add(history)
        for att in attachments:
            self.db.add(att)
        await self.db.commit()
        await self.db.refresh(expense)
        return expense

    async def transition(
        self,
        expense: ExpenseRequest,
        from_status: str,
        to_status: str,
        actor_id: uuid.UUID,
        comment: str | None,
        clear_approver: bool = False,
    ) -> ExpenseRequest:
        values: dict = {"status": to_status}
        if clear_approver:
            values["approver_id"] = None
        result = await self.db.execute(
            update(ExpenseRequest)
            .where(
                ExpenseRequest.id == expense.id,
                ExpenseRequest.status == from_status,
            )
            .values(**values)
        )
        if result.rowcount == 0:
            await self.db.rollback()
            raise ConflictError("该申请已处理,无法操作")
        expense.status = to_status
        if clear_approver:
            expense.approver_id = None
        self.db.add(
            ExpenseStatusHistory(
                request_id=expense.id,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor_id,
                comment=comment,
            )
        )
        await self.db.commit()
        await self.db.refresh(expense)
        return expense

    async def list_mine(
        self,
        applicant_id: uuid.UUID,
        status: str | None,
        expense_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ExpenseRequest], int]:
        conditions = [ExpenseRequest.applicant_id == applicant_id]
        if status is not None:
            conditions.append(ExpenseRequest.status == status)
        if expense_type is not None:
            conditions.append(ExpenseRequest.type == expense_type)
        total = (
            await self.db.execute(
                select(func.count()).select_from(ExpenseRequest).where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(ExpenseRequest)
            .where(*conditions)
            .order_by(ExpenseRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_todo(
        self,
        user_id: uuid.UUID,
        can_l1: bool,
        can_l2: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[ExpenseRequest], int]:
        clauses = []
        if can_l1:
            clauses.append(
                and_(
                    ExpenseRequest.status == "pending_l1",
                    ExpenseRequest.approver_id == user_id,
                )
            )
        if can_l2:
            clauses.append(ExpenseRequest.status == "pending_l2")
        condition = or_(*clauses)
        total = (
            await self.db.execute(
                select(func.count()).select_from(ExpenseRequest).where(condition)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(ExpenseRequest)
            .where(condition)
            .order_by(ExpenseRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_all(
        self,
        department_id: uuid.UUID | None,
        status: str | None,
        expense_type: str | None,
        start_from: date | None,
        end_to: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ExpenseRequest], int]:
        join_condition = ExpenseRequest.applicant_id == User.id
        conditions = []
        if department_id is not None:
            conditions.append(User.department_id == department_id)
        if status is not None:
            conditions.append(ExpenseRequest.status == status)
        if expense_type is not None:
            conditions.append(ExpenseRequest.type == expense_type)
        if start_from is not None:
            conditions.append(
                ExpenseRequest.created_at >= datetime.combine(start_from, time.min)
            )
        if end_to is not None:
            conditions.append(
                ExpenseRequest.created_at
                < datetime.combine(end_to + timedelta(days=1), time.min)
            )
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(ExpenseRequest)
                .join(User, join_condition)
                .where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(ExpenseRequest)
            .join(User, join_condition)
            .where(*conditions)
            .order_by(ExpenseRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_expense_repository.py -v`
Expected: 7 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/schemas/expense.py backend/tests/conftest.py backend/app/repositories/expense_repository.py backend/tests/test_expense_repository.py
git commit -m "feat(backend): 报销 schemas、配置项与 ExpenseRepository"
```

---

### Task 3: NotificationService 报销生成器 + UserRepository.list_by_permission

**Files:**
- Modify: `backend/app/services/notification_service.py`(EXPENSE_TYPE_LABELS + _fmt_amount + 4 个生成器)
- Modify: `backend/app/repositories/user_repository.py`(加 list_by_permission)
- Test: `backend/tests/test_notification_expense.py`

**Interfaces:**
- Consumes: Task 1/2 的 `ExpenseRequest`、既有 NotificationService/`_clamp_content`
- Produces:
  - `EXPENSE_TYPE_LABELS: dict[str, str]`(travel/office/entertainment/transport/other → 差旅/办公/招待/交通/其他)
  - `NotificationService.notify_expense_submitted(expense, applicant_name) -> None`(只 db.add)
  - `NotificationService.notify_expense_pending_l2(expense, applicant_name) -> None`(async,扇出,只 db.add)
  - `NotificationService.notify_expense_approved(expense) -> None`、`notify_expense_rejected(expense, reason) -> None`
  - `UserRepository.list_by_permission(code) -> list[User]`(Task 4 审批流用)

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_notification_expense.py`:

```python
from decimal import Decimal

from tests.conftest import (
    make_expense,
    make_permission,
    make_role,
    make_user,
)


async def _notifications_of(db, user_id):
    from app.repositories.notification_repository import NotificationRepository

    items, _ = await NotificationRepository(db).list_mine(user_id, None, 0, 50)
    return items


async def test_notify_expense_submitted_content(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(
        db, email="e@x.com", name="张三", manager_id=mgr.id
    )
    e = await make_expense(db, emp, mgr, type="travel", amount=Decimal("1999.50"))

    NotificationService(db).notify_expense_submitted(e, emp.name)
    await db.commit()

    items = await _notifications_of(db, mgr.id)
    assert len(items) == 1
    n = items[0]
    assert n.type == "expense_submitted"
    assert n.title == "新的待审批任务"
    assert n.content == "张三 提交了 1999.5 元的差旅报销,待您审批"
    assert n.ref_type == "expense"
    assert n.ref_id == e.id


async def test_notify_expense_pending_l2_fans_out(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", name="张三", manager_id=mgr.id)
    perm = await make_permission(db, code="expense:approve_l2", name="二级审批")
    role = await make_role(db, code="hr", name="HR", permissions=[perm])
    admin1 = await make_user(db, email="a1@x.com", roles=[role])
    admin2 = await make_user(db, email="a2@x.com", roles=[role])
    outsider = await make_user(db, email="o@x.com")
    e = await make_expense(db, emp, None, amount=Decimal("2000.00"), status="pending_l2")

    await NotificationService(db).notify_expense_pending_l2(e, emp.name)
    await db.commit()

    for u in (admin1, admin2):
        items = await _notifications_of(db, u.id)
        assert len(items) == 1
        assert items[0].type == "expense_pending_l2"
        assert items[0].content == "张三 的 2000 元差旅报销已通过主管审批,待您二级审批"
    assert await _notifications_of(db, outsider.id) == []


async def test_notify_expense_pending_l2_skips_inactive(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    perm = await make_permission(db, code="expense:approve_l2", name="二级审批")
    role = await make_role(db, code="hr", name="HR", permissions=[perm])
    active = await make_user(db, email="a@x.com", roles=[role])
    await make_user(db, email="i@x.com", roles=[role], is_active=False)
    e = await make_expense(db, emp, None, status="pending_l2")

    await NotificationService(db).notify_expense_pending_l2(e, emp.name)
    await db.commit()

    assert len(await _notifications_of(db, active.id)) == 1


async def test_notify_expense_approved_content(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await make_expense(db, emp, mgr, type="office", amount=Decimal("88.00"))

    NotificationService(db).notify_expense_approved(e)
    await db.commit()

    items = await _notifications_of(db, emp.id)
    assert len(items) == 1
    n = items[0]
    assert n.type == "expense_approved"
    assert n.title == "报销申请已通过"
    assert n.content == "您 88 元的办公报销已通过"


async def test_notify_expense_rejected_content_and_clamp(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await make_expense(db, emp, mgr, type="transport", amount=Decimal("66.00"))

    NotificationService(db).notify_expense_rejected(e, "票据不全")
    long_reason = "x" * 500
    NotificationService(db).notify_expense_rejected(e, long_reason)
    await db.commit()

    items = await _notifications_of(db, emp.id)
    assert len(items) == 2
    short = [n for n in items if "票据不全" in n.content][0]
    assert short.type == "expense_rejected"
    assert short.title == "报销申请已驳回"
    assert short.content == "您 66 元的交通报销已被驳回:票据不全"
    long_n = [n for n in items if "票据不全" not in n.content][0]
    assert len(long_n.content) == 500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_notification_expense.py -v`
Expected: FAIL,`AttributeError: type object 'NotificationService' has no attribute 'notify_expense_submitted'`(或 list_by_permission 缺失)

- [ ] **Step 3: Add generators + list_by_permission**

修改 `backend/app/repositories/user_repository.py`:import 区追加:

```python
from app.models.permission import Permission
from app.models.role import Role
```

类中追加方法:

```python
    async def list_by_permission(self, code: str) -> list[User]:
        result = await self.db.execute(
            select(User)
            .join(User.roles)
            .join(Role.permissions)
            .where(Permission.code == code, User.is_active.is_(True))
            .distinct()
        )
        return list(result.scalars().all())
```

修改 `backend/app/services/notification_service.py`:

1) import 区追加:

```python
from decimal import Decimal

from app.models.expense import ExpenseRequest
from app.repositories.user_repository import UserRepository
```

2) `LEAVE_TYPE_LABELS` 后追加:

```python
EXPENSE_TYPE_LABELS = {
    "travel": "差旅",
    "office": "办公",
    "entertainment": "招待",
    "transport": "交通",
    "other": "其他",
}


def _fmt_amount(amount: Decimal) -> str:
    return format(amount.normalize(), "f")
```

3) `NotificationService` 类中(`notify_leave_rejected` 之后)追加:

```python
    def notify_expense_submitted(
        self, expense: ExpenseRequest, applicant_name: str
    ) -> None:
        label = EXPENSE_TYPE_LABELS.get(expense.type, expense.type)
        self.db.add(
            Notification(
                user_id=expense.approver_id,
                type="expense_submitted",
                title="新的待审批任务",
                content=_clamp_content(
                    f"{applicant_name} 提交了 {_fmt_amount(expense.amount)} 元的{label}报销,待您审批"
                ),
                ref_type="expense",
                ref_id=expense.id,
            )
        )

    async def notify_expense_pending_l2(
        self, expense: ExpenseRequest, applicant_name: str
    ) -> None:
        label = EXPENSE_TYPE_LABELS.get(expense.type, expense.type)
        approvers = await UserRepository(self.db).list_by_permission(
            "expense:approve_l2"
        )
        for u in approvers:
            self.db.add(
                Notification(
                    user_id=u.id,
                    type="expense_pending_l2",
                    title="新的待审批任务",
                    content=_clamp_content(
                        f"{applicant_name} 的 {_fmt_amount(expense.amount)} 元{label}报销已通过主管审批,待您二级审批"
                    ),
                    ref_type="expense",
                    ref_id=expense.id,
                )
            )

    def notify_expense_approved(self, expense: ExpenseRequest) -> None:
        label = EXPENSE_TYPE_LABELS.get(expense.type, expense.type)
        self.db.add(
            Notification(
                user_id=expense.applicant_id,
                type="expense_approved",
                title="报销申请已通过",
                content=_clamp_content(
                    f"您 {_fmt_amount(expense.amount)} 元的{label}报销已通过"
                ),
                ref_type="expense",
                ref_id=expense.id,
            )
        )

    def notify_expense_rejected(
        self, expense: ExpenseRequest, reason: str
    ) -> None:
        label = EXPENSE_TYPE_LABELS.get(expense.type, expense.type)
        self.db.add(
            Notification(
                user_id=expense.applicant_id,
                type="expense_rejected",
                title="报销申请已驳回",
                content=_clamp_content(
                    f"您 {_fmt_amount(expense.amount)} 元的{label}报销已被驳回:{reason}"
                ),
                ref_type="expense",
                ref_id=expense.id,
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_notification_expense.py -v`
Expected: 5 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notification_service.py backend/app/repositories/user_repository.py backend/tests/test_notification_expense.py
git commit -m "feat(backend): 报销通知生成器(含二级扇出)与 list_by_permission"
```

---

### Task 4: ExpenseService(审批流 + 查询 + 可见性 + 附件落盘)

**Files:**
- Create: `backend/app/services/expense_service.py`
- Test: `backend/tests/test_expense_service.py`

**Interfaces:**
- Consumes: Task 2 的 `ExpenseRepository`/schemas/config;Task 3 的 `notify_expense_*`
- Produces:
  - `ExpenseService(db)`:
    - `create_expense(type: str, amount: Decimal, reason: str, files: list[tuple[str, str, bytes]], applicant: User) -> ExpenseRequest`(files = (filename, content_type, content);落盘失败/DB 失败清理)
    - `get_detail(expense_id, user) -> ExpenseRequest`、`get_attachment(expense_id, attachment_id, user) -> ExpenseAttachment`
    - `cancel_expense(expense_id, user)`、`approve_expense(expense_id, user)`、`reject_expense(expense_id, user, reason)`
    - `list_mine(user, status, expense_type, page, page_size)`、`list_todo(user, page, page_size)`、`list_all(department_id, status, expense_type, start_from, end_to, page, page_size)`
  - 附件落盘约定:`{settings.UPLOAD_DIR}/expenses/{expense_id}/{uuid4}.{ext}`,DB 存相对 UPLOAD_DIR 的 posix 路径

**关键实现约束(必须遵守,否则原子性失效):**
- `notify_expense_*` 只做 `db.add()`(pending_l2 扇出亦然),**不得** commit;commit 由 `ExpenseRepository.create/transition` 完成
- `create_expense` 中 `ExpenseRequest` 必须显式传 `id=uuid.uuid4()`(附件目录名与通知 ref_id 都需要)
- approve/reject 中 notify 调用放在校验之后、transition 之前;transition 因并发 rowcount=0 回滚时,挂起的通知 add 随 rollback 丢弃
- L1→L2 的扇出通知在 transition 之前 add,与 transition 同事务提交

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_expense_service.py`:

```python
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from tests.conftest import (
    make_expense,
    make_permission,
    make_role,
    make_user,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest_asyncio.fixture
async def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


async def perms_role(db, codes, role_code):
    perms = [await make_permission(db, code=c, name=c) for c in codes]
    return await make_role(db, code=role_code, name=role_code, permissions=perms)


async def test_create_requires_manager(db, upload_dir):
    from app.services.expense_service import ExpenseService

    emp = await make_user(db, email="e@x.com")
    with pytest.raises(ValidationError):
        await ExpenseService(db).create_expense(
            "travel", Decimal("100"), "x", [("a.png", "image/png", PNG)], emp
        )


async def test_create_stores_files_and_rows(db, upload_dir):
    from app.services.expense_service import ExpenseService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await ExpenseService(db).create_expense(
        "travel",
        Decimal("1999.50"),
        "出差打车",
        [("a.png", "image/png", PNG), ("b.pdf", "application/pdf", b"%PDF-1.4 fake")],
        emp,
    )
    assert e.status == "pending_l1"
    assert e.approver_id == mgr.id
    assert len(e.attachments) == 2
    for att in e.attachments:
        assert (upload_dir / att.stored_path).exists()
        assert att.size_bytes > 0
    assert len(e.history) == 1
    assert e.history[0].to_status == "pending_l1"


async def _mk_chain(db):
    mgr_role = await perms_role(db, ["expense:approve"], "mgr-r")
    l2_role = await perms_role(db, ["expense:approve_l2"], "hr-r")
    mgr = await make_user(db, email="m@x.com", roles=[mgr_role])
    admin = await make_user(db, email="a@x.com", roles=[l2_role])
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    return mgr, admin, emp


async def test_approve_l1_small_amount_directly_approved(db):
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr, amount=Decimal("2000.00"))
    e = await ExpenseService(db).approve_expense(e.id, mgr)
    assert e.status == "approved"
    assert e.approver_id == mgr.id


async def test_approve_l1_large_amount_goes_pending_l2(db):
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr, amount=Decimal("2000.01"))
    e = await ExpenseService(db).approve_expense(e.id, mgr)
    assert e.status == "pending_l2"
    assert e.approver_id is None
    assert [h.to_status for h in e.history] == ["pending_l2"]


async def test_approve_l2_success(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    e = await make_expense(db, emp, None, amount=Decimal("3000"), status="pending_l2")
    e = await ExpenseService(db).approve_expense(e.id, admin)
    assert e.status == "approved"


async def test_approve_l2_rejects_applicant_self(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    role = await perms_role(db, ["expense:approve_l2"], "hr-r2")
    emp.roles.append(role)
    await db.commit()
    e = await make_expense(db, emp, None, amount=Decimal("3000"), status="pending_l2")
    with pytest.raises(ForbiddenError):
        await ExpenseService(db).approve_expense(e.id, emp)


async def test_approve_l1_wrong_approver_forbidden(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr)
    with pytest.raises(ForbiddenError):
        await ExpenseService(db).approve_expense(e.id, admin)


async def test_approve_on_terminal_status_conflict(db):
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr, status="approved")
    with pytest.raises(ConflictError):
        await ExpenseService(db).approve_expense(e.id, mgr)


async def test_reject_requires_reason(db):
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e = await make_expense(db, emp, mgr)
    with pytest.raises(ValidationError):
        await ExpenseService(db).reject_expense(e.id, mgr, "  ")


async def test_reject_l2_terminates(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    e = await make_expense(db, emp, None, status="pending_l2")
    e = await ExpenseService(db).reject_expense(e.id, admin, "超标")
    assert e.status == "rejected"
    assert e.history[-1].comment == "超标"


async def test_cancel_rules(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    other = await make_user(db, email="o@x.com")
    svc = ExpenseService(db)

    e1 = await make_expense(db, emp, mgr)
    with pytest.raises(ForbiddenError):
        await svc.cancel_expense(e1.id, other)

    e2 = await make_expense(db, emp, mgr, status="approved")
    with pytest.raises(ConflictError):
        await svc.cancel_expense(e2.id, emp)

    e3 = await make_expense(db, emp, None, status="pending_l2")
    e3 = await svc.cancel_expense(e3.id, emp)
    assert e3.status == "cancelled"


async def test_detail_visibility(db):
    from app.services.expense_service import ExpenseService

    mgr, admin, emp = await _mk_chain(db)
    all_role = await perms_role(db, ["expense:list_all"], "all-r")
    viewer = await make_user(db, email="v@x.com", roles=[all_role])
    stranger = await make_user(db, email="s@x.com")
    svc = ExpenseService(db)

    e = await make_expense(db, emp, mgr, status="pending_l1")
    for u in (emp, mgr, viewer):
        assert (await svc.get_detail(e.id, u)).id == e.id
    with pytest.raises(ForbiddenError):
        await svc.get_detail(e.id, stranger)
    # pending_l1 时 l2 权限者不可见
    with pytest.raises(ForbiddenError):
        await svc.get_detail(e.id, admin)

    e2 = await make_expense(db, emp, None, status="pending_l2")
    assert (await svc.get_detail(e2.id, admin)).id == e2.id
    # 一级审批人在单进入二级后不再可见
    with pytest.raises(ForbiddenError):
        await svc.get_detail(e2.id, mgr)


async def test_get_attachment_belongs_to_expense(db):
    from app.models.expense import ExpenseAttachment
    from app.services.expense_service import ExpenseService

    mgr, _, emp = await _mk_chain(db)
    e1 = await make_expense(db, emp, mgr)
    e2 = await make_expense(db, emp, mgr)
    att = ExpenseAttachment(
        expense_id=e2.id,
        filename="a.png",
        stored_path="expenses/x/y.png",
        content_type="image/png",
        size_bytes=3,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)

    svc = ExpenseService(db)
    got = await svc.get_attachment(e2.id, att.id, emp)
    assert got.id == att.id
    from app.core.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        await svc.get_attachment(e1.id, att.id, emp)
    with pytest.raises(NotFoundError):
        await svc.get_attachment(e2.id, uuid.uuid4(), emp)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_expense_service.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.services.expense_service'`

- [ ] **Step 3: Write the service**

创建 `backend/app/services/expense_service.py`:

```python
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.expense import (
    ExpenseAttachment,
    ExpenseRequest,
    ExpenseStatusHistory,
)
from app.models.user import User
from app.repositories.expense_repository import ExpenseRepository
from app.services.notification_service import NotificationService


class ExpenseService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.expenses = ExpenseRepository(db)
        self.notifications = NotificationService(db)

    async def create_expense(
        self,
        type: str,
        amount: Decimal,
        reason: str,
        files: list[tuple[str, str, bytes]],
        applicant: User,
    ) -> ExpenseRequest:
        if applicant.manager_id is None:
            raise ValidationError("未设置直属上级,无法提交报销申请")
        expense = ExpenseRequest(
            id=uuid.uuid4(),
            applicant_id=applicant.id,
            approver_id=applicant.manager_id,
            type=type,
            amount=amount,
            reason=reason,
        )
        stored = self._store_files(expense.id, files)
        attachments = [
            ExpenseAttachment(
                expense_id=expense.id,
                filename=filename,
                stored_path=stored_path,
                content_type=content_type,
                size_bytes=size,
            )
            for filename, content_type, size, stored_path in stored
        ]
        history = ExpenseStatusHistory(
            request=expense,
            from_status=None,
            to_status="pending_l1",
            actor_id=applicant.id,
        )
        self.notifications.notify_expense_submitted(expense, applicant.name)
        try:
            return await self.expenses.create(expense, history, attachments)
        except Exception:
            self._remove_files([s[3] for s in stored])
            raise

    async def get_detail(
        self, expense_id: uuid.UUID, user: User
    ) -> ExpenseRequest:
        expense = await self._get_or_404(expense_id)
        self._check_visible(expense, user)
        return expense

    async def get_attachment(
        self, expense_id: uuid.UUID, attachment_id: uuid.UUID, user: User
    ) -> ExpenseAttachment:
        expense = await self._get_or_404(expense_id)
        self._check_visible(expense, user)
        att = await self.expenses.get_attachment(attachment_id)
        if att is None or att.expense_id != expense.id:
            raise NotFoundError("附件不存在")
        return att

    async def cancel_expense(
        self, expense_id: uuid.UUID, user: User
    ) -> ExpenseRequest:
        expense = await self._get_or_404(expense_id)
        if expense.applicant_id != user.id:
            raise ForbiddenError("只能撤回自己的报销申请")
        if expense.status not in ("pending_l1", "pending_l2"):
            raise ConflictError("该申请已处理,无法操作")
        return await self.expenses.transition(
            expense, expense.status, "cancelled", user.id, None
        )

    async def approve_expense(
        self, expense_id: uuid.UUID, user: User
    ) -> ExpenseRequest:
        expense = await self._get_or_404(expense_id)
        if expense.status == "pending_l1":
            self._check_l1_approver(expense, user)
            if expense.amount > settings.EXPENSE_L2_THRESHOLD:
                await self.notifications.notify_expense_pending_l2(
                    expense, expense.applicant.name
                )
                return await self.expenses.transition(
                    expense,
                    "pending_l1",
                    "pending_l2",
                    user.id,
                    None,
                    clear_approver=True,
                )
            self.notifications.notify_expense_approved(expense)
            return await self.expenses.transition(
                expense, "pending_l1", "approved", user.id, None
            )
        if expense.status == "pending_l2":
            self._check_l2_approver(expense, user)
            self.notifications.notify_expense_approved(expense)
            return await self.expenses.transition(
                expense, "pending_l2", "approved", user.id, None
            )
        raise ConflictError("该申请已处理,无法操作")

    async def reject_expense(
        self, expense_id: uuid.UUID, user: User, reason: str
    ) -> ExpenseRequest:
        expense = await self._get_or_404(expense_id)
        if expense.status == "pending_l1":
            self._check_l1_approver(expense, user)
        elif expense.status == "pending_l2":
            self._check_l2_approver(expense, user)
        else:
            raise ConflictError("该申请已处理,无法操作")
        if not reason.strip():
            raise ValidationError("驳回必须填写原因")
        self.notifications.notify_expense_rejected(expense, reason)
        return await self.expenses.transition(
            expense, expense.status, "rejected", user.id, reason
        )

    async def list_mine(
        self,
        user: User,
        status: str | None,
        expense_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ExpenseRequest], int]:
        return await self.expenses.list_mine(
            user.id, status, expense_type, (page - 1) * page_size, page_size
        )

    async def list_todo(
        self, user: User, page: int, page_size: int
    ) -> tuple[list[ExpenseRequest], int]:
        perms = self._perms(user)
        can_l1 = "expense:approve" in perms
        can_l2 = "expense:approve_l2" in perms
        if not (can_l1 or can_l2):
            raise ForbiddenError("无权限执行此操作")
        return await self.expenses.list_todo(
            user.id, can_l1, can_l2, (page - 1) * page_size, page_size
        )

    async def list_all(
        self,
        department_id: uuid.UUID | None,
        status: str | None,
        expense_type: str | None,
        start_from: date | None,
        end_to: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ExpenseRequest], int]:
        return await self.expenses.list_all(
            department_id,
            status,
            expense_type,
            start_from,
            end_to,
            (page - 1) * page_size,
            page_size,
        )

    async def _get_or_404(self, expense_id: uuid.UUID) -> ExpenseRequest:
        expense = await self.expenses.get_by_id(expense_id)
        if expense is None:
            raise NotFoundError("报销申请不存在")
        return expense

    def _perms(self, user: User) -> set[str]:
        return {p.code for role in user.roles for p in role.permissions}

    def _check_l1_approver(self, expense: ExpenseRequest, user: User) -> None:
        if (
            "expense:approve" not in self._perms(user)
            or expense.approver_id != user.id
        ):
            raise ForbiddenError("只有当前审批人可以审批")

    def _check_l2_approver(self, expense: ExpenseRequest, user: User) -> None:
        if "expense:approve_l2" not in self._perms(user):
            raise ForbiddenError("只有当前审批人可以审批")
        if expense.applicant_id == user.id:
            raise ForbiddenError("不能审批自己的报销申请")

    def _check_visible(self, expense: ExpenseRequest, user: User) -> None:
        perms = self._perms(user)
        if user.id == expense.applicant_id:
            return
        if expense.status == "pending_l1" and expense.approver_id == user.id:
            return
        if expense.status == "pending_l2" and "expense:approve_l2" in perms:
            return
        if "expense:list_all" in perms:
            return
        raise ForbiddenError("无权查看该报销申请")

    def _store_files(
        self, expense_id: uuid.UUID, files: list[tuple[str, str, bytes]]
    ) -> list[tuple[str, str, int, str]]:
        base = Path(settings.UPLOAD_DIR) / "expenses" / str(expense_id)
        base.mkdir(parents=True, exist_ok=True)
        stored = []
        for filename, content_type, content in files:
            ext = filename.rsplit(".", 1)[-1].lower()
            path = base / f"{uuid.uuid4()}.{ext}"
            path.write_bytes(content)
            stored.append(
                (
                    filename,
                    content_type,
                    len(content),
                    path.relative_to(settings.UPLOAD_DIR).as_posix(),
                )
            )
        return stored

    def _remove_files(self, stored_paths: list[str]) -> None:
        for p in stored_paths:
            target = Path(settings.UPLOAD_DIR) / p
            target.unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_expense_service.py -v`
Expected: 13 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/expense_service.py backend/tests/test_expense_service.py
git commit -m "feat(backend): ExpenseService 二级审批流与附件落盘"
```

---

### Task 5: /expenses API(multipart 提交 + 附件下载)

**Files:**
- Create: `backend/app/api/v1/expenses.py`
- Modify: `backend/app/main.py:3,16`(import + include_router)
- Test: `backend/tests/test_expenses_api.py`

**Interfaces:**
- Consumes: Task 4 的 `ExpenseService`;Task 2 的 schemas;`get_current_user`/`require_permission`
- Produces: `POST /api/v1/expenses`(multipart)、`GET /expenses/mine`、`GET /expenses/todo`、`GET /expenses`、`GET /expenses/{id}`、`GET /expenses/{id}/attachments/{att_id}`、`POST /expenses/{id}/cancel|approve|reject`(Task 7 集成测直接调这些接口)

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_expenses_api.py`:

```python
import uuid

import pytest_asyncio

from app.core.config import settings
from tests.conftest import (
    login_token,
    make_expense,
    make_permission,
    make_role,
    make_user,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.4 fake-pdf-bytes"


@pytest_asyncio.fixture
async def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


async def expense_perms(db):
    from sqlalchemy import select

    from app.models.permission import Permission

    existing = {p.code: p for p in (await db.execute(select(Permission))).scalars()}
    perms = {}
    for code in [
        "expense:create",
        "expense:list",
        "expense:approve",
        "expense:approve_l2",
        "expense:list_all",
    ]:
        perms[code] = existing.get(code) or await make_permission(
            db, code=code, name=code
        )
    return perms


async def make_employee_client(db, client, mgr, email="emp@x.com", name="张三"):
    perms = await expense_perms(db)
    role = await make_role(
        db,
        code=f"emp-{email}",
        name="员工",
        permissions=[perms["expense:create"], perms["expense:list"]],
    )
    emp = await make_user(
        db, email=email, password="Passw0rd!", name=name,
        roles=[role], manager_id=mgr.id,
    )
    token = await login_token(client, email, "Passw0rd!")
    return emp, {"Authorization": f"Bearer {token}"}


async def make_manager_client(db, client, email="mgr@x.com"):
    perms = await expense_perms(db)
    role = await make_role(
        db,
        code=f"mgr-{email}",
        name="主管",
        permissions=[
            perms["expense:create"],
            perms["expense:list"],
            perms["expense:approve"],
        ],
    )
    mgr = await make_user(db, email=email, password="Passw0rd!", roles=[role])
    token = await login_token(client, email, "Passw0rd!")
    return mgr, {"Authorization": f"Bearer {token}"}


async def make_admin_client(db, client, email="admin@x.com"):
    perms = await expense_perms(db)
    role = await make_role(
        db, code=f"adm-{email}", name="Admin", permissions=list(perms.values())
    )
    admin = await make_user(db, email=email, password="Passw0rd!", roles=[role])
    token = await login_token(client, email, "Passw0rd!")
    return admin, {"Authorization": f"Bearer {token}"}


def form(**over):
    data = {"type": "travel", "amount": "1999.50", "reason": "出差打车"}
    data.update(over)
    files = [("files", ("a.png", PNG, "image/png"))]
    return data, files


async def submit(client, headers, **over):
    data, files = form(**over)
    return await client.post(
        "/api/v1/expenses", data=data, files=files, headers=headers
    )


async def test_create_201_and_file_on_disk(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    resp = await submit(client, emp_h)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending_l1"
    assert body["approver_id"] == str(mgr.id)
    assert float(body["amount"]) == 1999.5

    detail = await client.get(f"/api/v1/expenses/{body['id']}", headers=emp_h)
    assert detail.status_code == 200
    atts = detail.json()["attachments"]
    assert len(atts) == 1
    assert atts[0]["filename"] == "a.png"
    assert "stored_path" not in atts[0]
    assert detail.json()["history"][0]["to_status"] == "pending_l1"


async def test_create_validation_errors(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    # 类型非法
    resp = await submit(client, emp_h, type="luxury")
    assert resp.status_code == 422
    # 金额 ≤ 0
    resp = await submit(client, emp_h, amount="0")
    assert resp.status_code == 422
    # 扩展名非法
    data, _ = form()
    resp = await client.post(
        "/api/v1/expenses",
        data=data,
        files=[("files", ("a.gif", b"GIF89a fake", "image/gif"))],
        headers=emp_h,
    )
    assert resp.status_code == 422
    # 魔数不符( .png 文件装 JPEG 字节)
    resp = await client.post(
        "/api/v1/expenses",
        data=data,
        files=[("files", ("a.png", b"\xff\xd8\xff\xe0 jpeg", "image/png"))],
        headers=emp_h,
    )
    assert resp.status_code == 422
    # 附件超 5 个
    resp = await client.post(
        "/api/v1/expenses",
        data=data,
        files=[("files", (f"{i}.png", PNG, "image/png")) for i in range(6)],
        headers=emp_h,
    )
    assert resp.status_code == 422


async def test_unauthenticated_401(client):
    assert (await client.post("/api/v1/expenses")).status_code == 401
    assert (await client.get("/api/v1/expenses/mine")).status_code == 401
    assert (await client.get("/api/v1/expenses/todo")).status_code == 401
    assert (await client.get(f"/api/v1/expenses/{uuid.uuid4()}")).status_code == 401


async def test_employee_without_create_perm_403(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    perms = await expense_perms(db)
    role = await make_role(
        db, code="noperm", name="无权限", permissions=[perms["expense:list"]]
    )
    await make_user(
        db, email="np@x.com", password="Passw0rd!", roles=[role],
        manager_id=mgr.id,
    )
    token = await login_token(client, "np@x.com", "Passw0rd!")
    resp = await submit(client, {"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


async def test_todo_merged_view(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    emp, _ = await make_employee_client(db, client, mgr)
    admin, admin_h = await make_admin_client(db, client)
    # 一笔小额(停在 L1)、一笔大额(进入 L2)
    small = await submit(client, {"Authorization": (await login_token(client, emp.email, "Passw0rd!")) and ""}, amount="100")
```

等等——上面这个测试的 token 写法有问题。改为直接用 make_employee_client 返回的 headers:

```python
async def test_todo_merged_view(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    admin, admin_h = await make_admin_client(db, client)

    small = await submit(client, emp_h, amount="100")
    assert small.status_code == 201
    big = await submit(client, emp_h, amount="3000")
    assert big.status_code == 201
    # 大额 L1 通过 → pending_l2
    resp = await client.post(
        f"/api/v1/expenses/{big.json()['id']}/approve", headers=mgr_h
    )
    assert resp.status_code == 200

    # 主管 todo:自己的 pending_l1(1 笔)+ 权限池 pending_l2(0,无 l2 权限)
    resp = await client.get("/api/v1/expenses/todo", headers=mgr_h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "pending_l1"

    # Admin todo:pending_l2 1 笔(admin 无 expense:approve,看不到 pending_l1)
    resp = await client.get("/api/v1/expenses/todo", headers=admin_h)
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "pending_l2"


async def test_mine_and_list_all(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    admin, admin_h = await make_admin_client(db, client)
    await submit(client, emp_h, amount="10")
    await submit(client, emp_h, amount="20", type="office")

    resp = await client.get("/api/v1/expenses/mine?type=office", headers=emp_h)
    assert resp.json()["total"] == 1
    resp = await client.get("/api/v1/expenses/mine", headers=emp_h)
    assert resp.json()["total"] == 2

    resp = await client.get("/api/v1/expenses", headers=admin_h)
    assert resp.json()["total"] == 2
    # 主管无 list_all
    mgr_h2 = (await make_manager_client(db, client, "m2@x.com"))[1]
    resp = await client.get("/api/v1/expenses", headers=mgr_h2)
    assert resp.status_code == 403


async def test_download_attachment_auth(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    created = await submit(client, emp_h)
    eid = created.json()["id"]
    detail = await client.get(f"/api/v1/expenses/{eid}", headers=emp_h)
    att_id = detail.json()["attachments"][0]["id"]

    resp = await client.get(
        f"/api/v1/expenses/{eid}/attachments/{att_id}", headers=emp_h
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"\x89PNG")

    # 陌生人 403(先建一个只有 create+list 的另一员工)
    _, stranger_h = await make_employee_client(db, client, mgr, "s@x.com", "李四")
    resp = await client.get(
        f"/api/v1/expenses/{eid}/attachments/{att_id}", headers=stranger_h
    )
    assert resp.status_code == 403

    # 附件不属于该单 → 404
    created2 = await submit(client, emp_h)
    resp = await client.get(
        f"/api/v1/expenses/{created2.json()['id']}/attachments/{att_id}",
        headers=emp_h,
    )
    assert resp.status_code == 404


async def test_approve_reject_cancel_via_api(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    # approve 直达(≤2000)
    small = await submit(client, emp_h, amount="1500")
    resp = await client.post(
        f"/api/v1/expenses/{small.json()['id']}/approve", headers=mgr_h
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    # 驳回缺原因 422
    big = await submit(client, emp_h, amount="5000")
    resp = await client.post(
        f"/api/v1/expenses/{big.json()['id']}/reject",
        json={"reason": " "},
        headers=mgr_h,
    )
    assert resp.status_code == 422
    resp = await client.post(
        f"/api/v1/expenses/{big.json()['id']}/reject",
        json={"reason": "超标"},
        headers=mgr_h,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    # 已终态再操作 409
    resp = await client.post(
        f"/api/v1/expenses/{big.json()['id']}/approve", headers=mgr_h
    )
    assert resp.status_code == 409

    # 撤回
    e3 = await submit(client, emp_h, amount="50")
    resp = await client.post(
        f"/api/v1/expenses/{e3.json()['id']}/cancel", headers=emp_h
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_expenses_api.py -v`
Expected: FAIL,404/405(路由不存在)

- [ ] **Step 3: Write the router + register**

创建 `backend/app/api/v1/expenses.py`:

```python
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_permission
from app.core.exceptions import ValidationError
from app.models.user import User
from app.schemas.expense import (
    ExpenseDetailResponse,
    ExpenseListResponse,
    ExpenseReject,
    ExpenseResponse,
)
from app.services.expense_service import ExpenseService

router = APIRouter(prefix="/expenses", tags=["expenses"])

ALLOWED_TYPES = {"travel", "office", "entertainment", "transport", "other"}
MAX_FILE_SIZE = 5 * 1024 * 1024
MAGIC = {
    "jpg": ("image/jpeg", b"\xff\xd8\xff"),
    "jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    "png": ("image/png", b"\x89PNG"),
    "pdf": ("application/pdf", b"%PDF"),
}


async def _read_files(
    files: list[UploadFile],
) -> list[tuple[str, str, bytes]]:
    if not 1 <= len(files) <= 5:
        raise ValidationError("附件数量须为 1~5 个")
    payloads = []
    for f in files:
        ext = (f.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in MAGIC:
            raise ValidationError("附件仅支持 jpg/png/pdf")
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            raise ValidationError("单个附件不能超过 5MB")
        content_type, magic = MAGIC[ext]
        if not content.startswith(magic):
            raise ValidationError("附件内容与扩展名不符")
        payloads.append((f.filename or f"file.{ext}", content_type, content))
    return payloads


@router.post("", response_model=ExpenseResponse, status_code=201)
async def create_expense(
    type: str = Form(...),
    amount: Decimal = Form(...),
    reason: str = Form(...),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:create")),
):
    if type not in ALLOWED_TYPES:
        raise ValidationError("报销类型非法")
    if amount <= 0:
        raise ValidationError("金额必须大于 0")
    if not (1 <= len(reason) <= 500):
        raise ValidationError("说明长度须为 1~500 字符")
    payloads = await _read_files(files)
    return await ExpenseService(db).create_expense(
        type, amount, reason, payloads, current_user
    )


@router.get("/mine", response_model=ExpenseListResponse)
async def list_mine(
    status: str | None = Query(None),
    type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:list")),
):
    items, total = await ExpenseService(db).list_mine(
        current_user, status, type, page, page_size
    )
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/todo", response_model=ExpenseListResponse)
async def list_todo(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await ExpenseService(db).list_todo(current_user, page, page_size)
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=ExpenseListResponse)
async def list_all(
    department_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    type: str | None = Query(None),
    start_from: date | None = Query(None),
    end_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("expense:list_all")),
):
    items, total = await ExpenseService(db).list_all(
        department_id, status, type, start_from, end_to, page, page_size
    )
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{expense_id}", response_model=ExpenseDetailResponse)
async def get_detail(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:list")),
):
    return await ExpenseService(db).get_detail(expense_id, current_user)


@router.get("/{expense_id}/attachments/{attachment_id}")
async def download_attachment(
    expense_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:list")),
):
    att = await ExpenseService(db).get_attachment(
        expense_id, attachment_id, current_user
    )
    return FileResponse(
        Path(settings.UPLOAD_DIR) / att.stored_path,
        media_type=att.content_type,
        filename=att.filename,
    )


@router.post("/{expense_id}/cancel", response_model=ExpenseResponse)
async def cancel_expense(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("expense:create")),
):
    return await ExpenseService(db).cancel_expense(expense_id, current_user)


@router.post("/{expense_id}/approve", response_model=ExpenseResponse)
async def approve_expense(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ExpenseService(db).approve_expense(expense_id, current_user)


@router.post("/{expense_id}/reject", response_model=ExpenseResponse)
async def reject_expense(
    expense_id: uuid.UUID,
    data: ExpenseReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ExpenseService(db).reject_expense(
        expense_id, current_user, data.reason
    )
```

修改 `backend/app/main.py`:

- 第 3 行 import 改为:`from app.api.v1 import auth, departments, expenses, leaves, notifications, roles, users`
- 在 `api_v1.include_router(leaves.router)` 后加:`api_v1.include_router(expenses.router)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_expenses_api.py -v`
Expected: 8 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/expenses.py backend/app/main.py backend/tests/test_expenses_api.py
git commit -m "feat(backend): /expenses 提交/审批/查询/附件下载接口"
```

---

### Task 6: seed 追加报销权限点

**Files:**
- Modify: `backend/scripts/seed.py`(PERMISSIONS + ROLE_PERMISSIONS)
- Modify: `backend/tests/conftest.py`(ALL_PERMISSIONS 追加 5 条)
- Modify: `backend/tests/test_seed.py`(期望集合更新)
- Test: `backend/tests/test_seed.py`(既有,改期望)

**Interfaces:**
- Consumes: Task 5 的权限点命名
- Produces: 新环境 `python -m scripts.seed` 后 admin 全量、manager 含 expense:create/list/approve、employee 含 expense:create/list

- [ ] **Step 1: Update the failing tests first**

修改 `backend/tests/test_seed.py`:

1) `ALL_PERMISSION_CODES` 改为:

```python
ALL_PERMISSION_CODES = {
    "user:create", "user:list", "user:update",
    "user:disable", "role:list", "role:assign",
    "department:create", "department:update", "department:delete",
    "department:list", "department:members",
    "leave:create", "leave:list", "leave:approve", "leave:list_all",
    "expense:create", "expense:list", "expense:approve",
    "expense:approve_l2", "expense:list_all",
}
```

2) `test_seed_creates_permissions_roles_and_admin` 与 `test_seed_repairs_manager_permissions_on_rerun` 中 manager 期望集合改为:

```python
    assert {p.code for p in roles["manager"].permissions} == {
        "department:list",
        "department:members",
        "leave:create",
        "leave:list",
        "leave:approve",
        "expense:create",
        "expense:list",
        "expense:approve",
    }
```

(`test_seed_repairs_manager_permissions_on_rerun` 里是 `role` 变量,断言相应改为 `{p.code for p in role.permissions}`。)

3) `test_seed_assigns_department_permissions` 中 employee 期望改为:

```python
    assert {p.code for p in roles["employee"].permissions} == {
        "leave:create",
        "leave:list",
        "expense:create",
        "expense:list",
    }
```

4) `test_seed_assigns_leave_permissions` 中 employee 断言改为:

```python
    assert employee_perms == {
        "leave:create",
        "leave:list",
        "expense:create",
        "expense:list",
    }
```

5) 文件末尾追加报销专项测试:

```python
async def test_seed_assigns_expense_permissions(db):
    await seed(db)

    perms = {p.code for p in (await db.execute(select(Permission))).scalars()}
    expected = {
        "expense:create",
        "expense:list",
        "expense:approve",
        "expense:approve_l2",
        "expense:list_all",
    }
    assert expected <= perms

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    admin_perms = {p.code for p in roles["admin"].permissions}
    manager_perms = {p.code for p in roles["manager"].permissions}
    employee_perms = {p.code for p in roles["employee"].permissions}
    assert expected <= admin_perms
    assert {"expense:create", "expense:list", "expense:approve"} <= manager_perms
    assert "expense:approve_l2" not in manager_perms
    assert "expense:list_all" not in manager_perms
    assert employee_perms == {
        "leave:create",
        "leave:list",
        "expense:create",
        "expense:list",
    }
```

修改 `backend/tests/conftest.py` 的 `ALL_PERMISSIONS`,在 `("leave:list_all", "查看全部审批记录"),` 后追加:

```python
    ("expense:create", "提交/撤回报销申请"),
    ("expense:list", "查看我的报销"),
    ("expense:approve", "审批报销申请(一级)"),
    ("expense:approve_l2", "审批报销申请(二级)"),
    ("expense:list_all", "查看全部报销记录"),
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_seed.py -v`
Expected: FAIL(manager/employee/admin 权限集合不符)

- [ ] **Step 3: Update seed.py**

修改 `backend/scripts/seed.py` 的 `PERMISSIONS`,在 `("leave:list_all", "查看全部审批记录"),` 后追加:

```python
    ("expense:create", "提交/撤回报销申请"),
    ("expense:list", "查看我的报销"),
    ("expense:approve", "审批报销申请(一级)"),
    ("expense:approve_l2", "审批报销申请(二级)"),
    ("expense:list_all", "查看全部报销记录"),
```

`ROLE_PERMISSIONS` 的 manager 列表改为:

```python
    "manager": [
        "department:list",
        "department:members",
        "leave:create",
        "leave:list",
        "leave:approve",
        "expense:create",
        "expense:list",
        "expense:approve",
    ],
```

employee 列表改为:

```python
    "employee": ["leave:create", "leave:list", "expense:create", "expense:list"],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_seed.py -v`
Expected: 全部 PASS(含幂等/修复既有测试)

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/seed.py backend/tests/conftest.py backend/tests/test_seed.py
git commit -m "feat(backend): seed 追加报销五个权限点与角色映射"
```

---

### Task 7: 全链路通知集成测试 + 全量验收 + spec 勾选

**Files:**
- Create: `backend/tests/test_expense_notifications.py`
- Modify: `docs/superpowers/specs/2026-07-28-expense-approval-design.md`(§10 六个 `- [ ]` → `- [x]`)

**Interfaces:**
- Consumes: Task 1-6 全部产出;Task 4 的 `/notifications` 既有接口(验证用)
- Produces: 可 PR 的完整分支

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_expense_notifications.py`:

```python
import pytest_asyncio

from app.core.config import settings
from tests.conftest import (
    login_token,
    make_permission,
    make_role,
    make_user,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest_asyncio.fixture
async def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


async def expense_perms(db):
    from sqlalchemy import select

    from app.models.permission import Permission

    existing = {p.code: p for p in (await db.execute(select(Permission))).scalars()}
    perms = {}
    for code in [
        "expense:create",
        "expense:list",
        "expense:approve",
        "expense:approve_l2",
        "expense:list_all",
    ]:
        perms[code] = existing.get(code) or await make_permission(
            db, code=code, name=code
        )
    return perms


async def make_manager_client(db, client, email="mgr@x.com"):
    perms = await expense_perms(db)
    role = await make_role(
        db,
        code=f"mgr-{email}",
        name="主管",
        permissions=[
            perms["expense:create"],
            perms["expense:list"],
            perms["expense:approve"],
        ],
    )
    mgr = await make_user(db, email=email, password="Passw0rd!", roles=[role])
    token = await login_token(client, email, "Passw0rd!")
    return mgr, {"Authorization": f"Bearer {token}"}


async def make_employee_client(db, client, mgr, email="emp@x.com", name="张三"):
    perms = await expense_perms(db)
    role = await make_role(
        db,
        code=f"emp-{email}",
        name="员工",
        permissions=[perms["expense:create"], perms["expense:list"]],
    )
    emp = await make_user(
        db, email=email, password="Passw0rd!", name=name,
        roles=[role], manager_id=mgr.id,
    )
    token = await login_token(client, email, "Passw0rd!")
    return emp, {"Authorization": f"Bearer {token}"}


async def make_admin_client(db, client, email="admin@x.com"):
    perms = await expense_perms(db)
    role = await make_role(
        db, code=f"adm-{email}", name="Admin", permissions=list(perms.values())
    )
    admin = await make_user(db, email=email, password="Passw0rd!", roles=[role])
    token = await login_token(client, email, "Passw0rd!")
    return admin, {"Authorization": f"Bearer {token}"}


async def submit(client, headers, amount="100", type="travel"):
    return await client.post(
        "/api/v1/expenses",
        data={"type": type, "amount": amount, "reason": "出差打车"},
        files=[("files", ("a.png", PNG, "image/png"))],
        headers=headers,
    )


async def unread_count(client, headers) -> int:
    resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.status_code == 200
    return resp.json()["count"]


async def latest_notification(client, headers) -> dict:
    resp = await client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    return resp.json()["items"][0]


async def test_small_amount_chain_notifications(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    resp = await submit(client, emp_h, amount="1500")
    assert resp.status_code == 201

    n = await latest_notification(client, mgr_h)
    assert n["type"] == "expense_submitted"
    assert n["content"] == "张三 提交了 1500 元的差旅报销,待您审批"
    assert n["ref_type"] == "expense"
    assert n["ref_id"] == resp.json()["id"]

    resp = await client.post(
        f"/api/v1/expenses/{resp.json()['id']}/approve", headers=mgr_h
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    n = await latest_notification(client, emp_h)
    assert n["type"] == "expense_approved"
    assert n["content"] == "您 1500 元的差旅报销已通过"


async def test_large_amount_two_level_chain(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    emp, emp_h = await make_employee_client(db, client, mgr)
    admin, admin_h = await make_admin_client(db, client)

    resp = await submit(client, emp_h, amount="5000")
    eid = resp.json()["id"]
    emp_baseline = await unread_count(client, emp_h)

    resp = await client.post(f"/api/v1/expenses/{eid}/approve", headers=mgr_h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_l2"
    assert resp.json()["approver_id"] is None

    # 二级扇出:admin 收到待审批通知;申请人此时无"已通过"通知
    n = await latest_notification(client, admin_h)
    assert n["type"] == "expense_pending_l2"
    assert n["content"] == "张三 的 5000 元差旅报销已通过主管审批,待您二级审批"
    assert await unread_count(client, emp_h) == emp_baseline

    resp = await client.post(f"/api/v1/expenses/{eid}/approve", headers=admin_h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    n = await latest_notification(client, emp_h)
    assert n["type"] == "expense_approved"
    assert n["content"] == "您 5000 元的差旅报销已通过"


async def test_reject_at_l2_notifies_applicant(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    _, admin_h = await make_admin_client(db, client)

    resp = await submit(client, emp_h, amount="5000")
    eid = resp.json()["id"]
    await client.post(f"/api/v1/expenses/{eid}/approve", headers=mgr_h)

    resp = await client.post(
        f"/api/v1/expenses/{eid}/reject",
        json={"reason": "预算不足"},
        headers=admin_h,
    )
    assert resp.status_code == 200

    n = await latest_notification(client, emp_h)
    assert n["type"] == "expense_rejected"
    assert n["content"] == "您 5000 元的差旅报销已被驳回:预算不足"


async def test_cancel_sends_no_notification(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    resp = await submit(client, emp_h, amount="100")
    eid = resp.json()["id"]
    mgr_baseline = await unread_count(client, mgr_h)
    emp_baseline = await unread_count(client, emp_h)

    resp = await client.post(f"/api/v1/expenses/{eid}/cancel", headers=emp_h)
    assert resp.status_code == 200

    assert await unread_count(client, mgr_h) == mgr_baseline
    assert await unread_count(client, emp_h) == emp_baseline


async def test_double_approve_409_no_extra_notification(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    resp = await submit(client, emp_h, amount="100")
    eid = resp.json()["id"]
    await client.post(f"/api/v1/expenses/{eid}/approve", headers=mgr_h)
    baseline = await unread_count(client, emp_h)

    resp = await client.post(f"/api/v1/expenses/{eid}/approve", headers=mgr_h)
    assert resp.status_code == 409
    assert await unread_count(client, emp_h) == baseline
```

先跑一遍确认通过(接线已在 Task 1-6 完成,本任务的集成测应直接全绿;若有 FAIL 说明前序任务有缺口,修复后再继续):

Run: `cd backend && pytest tests/test_expense_notifications.py -v`
Expected: 5 个 PASS

- [ ] **Step 2: Commit the integration tests**

```bash
git add backend/tests/test_expense_notifications.py
git commit -m "test(backend): 报销两级审批全链路通知集成测试"
```

- [ ] **Step 3: Run full backend test suite**

Run: `cd backend && pytest`
Expected: 全部 PASS(既有 206 + 本分支新增,无回归)

- [ ] **Step 4: Migration reversibility**

Run: `cd backend && alembic downgrade -1 && alembic upgrade head && alembic check`
Expected: downgrade 回到 `b4c7e1a9d253`、upgrade 重回 `c8d3f2a1b947`、`alembic check` 无漂移

- [ ] **Step 5: Tick spec acceptance boxes**

把 `docs/superpowers/specs/2026-07-28-expense-approval-design.md` §10 的 6 个 `- [ ]` 全部改为 `- [x]`。

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-07-28-expense-approval-design.md
git commit -m "test(backend): 报销模块全量验收通过,勾选 spec 验收标准"
```

---

## Self-Review 记录

- **Spec 覆盖**:§3 三表+配置→Task 1/2;§4 状态机→Task 2(transition/clear_approver)+Task 4(审批流);§5 通知→Task 3(生成器/扇出/截断)+Task 7(集成验证);§6 API/附件/权限→Task 5+Task 6(seed);§7 错误语义→Task 4/5 测试;§8 测试策略→各任务测试+Task 7;§9 部署→Task 1/6/7;§10 验收→Task 7 勾选。无缺口。
- **占位符扫描**:无 TBD/TODO;所有代码块为完整可复制内容。
- **类型一致性**:`ExpenseRepository` 签名 Task 2 定义、Task 4 消费一致;`notify_expense_*` Task 3 定义、Task 4 调用一致(pending_l2 为 async,调用点已 await);`make_expense` Task 2 定义、Task 3/4 测试使用一致;`expense_perms/make_*_client` helper 在 Task 5/7 各自测试文件内独立定义(测试文件互不允许 import)。
- **已知取舍**:①列表按 `created_at desc`,SQLite 秒级精度,同秒多行顺序不定——测试一律只断言 total 与集合成员,不断言同秒行序;②Task 5/7 的 helper 重复定义是有意的(测试文件自包含,与既有 test 风格一致);③`test_list_all_filters` 未单独建部门测 department_id 过滤(请假已有同款过滤测试覆盖 join 模式,此处从简)。
