# 消息通知模块(后端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为请假审批三个动作点(提交/通过/驳回)同步生成站内通知,并提供通知列表/未读数/标记已读(单条/全部)四个后端接口。

**Architecture:** 沿用现有分层(api/v1 → services → repositories → models)。Notification 为只追加 + read_at 单字段更新的表;通知行由 LeaveService 在动作成功点调用 NotificationService 生成,只 `db.add()` 不 commit,随请假动作在同一事务提交(动作回滚则通知一并回滚)。查询侧接口仅需登录(get_current_user),无新权限点。

**Tech Stack:** FastAPI + SQLAlchemy Async + Alembic + pydantic v2;pytest + httpx AsyncClient + 内存 SQLite。

## Global Constraints

- 工作分支:`feature/backend-notification`(已在此分支,不切分支)
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- Commit message:中文 Conventional Commits(参照 git log 现有风格,如 `feat(backend): ...`)
- 设计依据:`docs/superpowers/specs/2026-07-26-backend-notification-design.md`,实现必须与 spec 一致;触发场景严格两个半(提交→审批人;通过/驳回→申请人;撤回不通知)
- 不新增权限点、不改 seed、不改 frontend/、不引入新依赖
- 通知生成只做 `db.add()`,commit 一律由 LeaveRepository 既有方法完成(同事务原子性的实现关键)
- 测试库为内存 SQLite,迁移 DDL 须 SQLite 兼容(server_default 用 `sa.text("(CURRENT_TIMESTAMP)")`,参照 5f3a8c1d9e02 迁移)
- 运行 pytest 的工作目录是 `backend/`(`pytest.ini` 在其中,asyncio_mode=auto)

---

### Task 1: Notification 模型 + Alembic 迁移

**Files:**
- Create: `backend/app/models/notification.py`
- Create: `backend/alembic/versions/b4c7e1a9d253_add_notifications.py`
- Modify: `backend/alembic/env.py:11`(import 行加 notification)
- Modify: `backend/tests/conftest.py:14`(import 区加 Notification)
- Test: `backend/tests/test_notification_model.py`

**Interfaces:**
- Consumes: `app.models.base.Base`(不挂 TimestampMixin,参照 LeaveStatusHistory)
- Produces: `app.models.notification.Notification`,字段 `id/user_id/type/title/content/ref_type/ref_id/read_at/created_at`,关系 `user`;后续所有任务依赖此模型

- [ ] **Step 1: Write the failing test**

创建 `backend/tests/test_notification_model.py`:

```python
import uuid

from app.core.security import hash_password
from app.models.user import User


async def test_notification_persist(db):
    from app.models.notification import Notification

    user = User(
        email="n@x.com", name="N", hashed_password=hash_password("Passw0rd!")
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    ref_id = uuid.uuid4()
    n = Notification(
        user_id=user.id,
        type="leave_submitted",
        title="新的待审批任务",
        content="张三 提交了 2026-08-01 ~ 2026-08-02 的事假申请,待您审批",
        ref_type="leave",
        ref_id=ref_id,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)

    assert n.id is not None
    assert n.user_id == user.id
    assert n.ref_id == ref_id
    assert n.read_at is None
    assert n.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_notification_model.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.models.notification'`

- [ ] **Step 3: Write the model**

创建 `backend/app/models/notification.py`:

```python
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(String(500))
    ref_type: Mapped[str] = mapped_column(String(20))
    ref_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(lazy="selectin")

    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)
```

修改 `backend/alembic/env.py:11`,import 行加入 notification:

```python
from app.models import associations, department, leave, notification, permission, role, user  # noqa: F401
```

修改 `backend/tests/conftest.py`,在 `from app.models.leave import LeaveRequest` 一行后加:

```python
from app.models.notification import Notification  # noqa: F401  # 注册进 metadata,create_all 用
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_notification_model.py -v`
Expected: PASS

- [ ] **Step 5: Write the migration**

创建 `backend/alembic/versions/b4c7e1a9d253_add_notifications.py`(down_revision 为当前 head `5f3a8c1d9e02`):

```python
"""add notifications

Revision ID: b4c7e1a9d253
Revises: 5f3a8c1d9e02
Create Date: 2026-07-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c7e1a9d253"
down_revision: Union[str, None] = "5f3a8c1d9e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("content", sa.String(length=500), nullable=False),
        sa.Column("ref_type", sa.String(length=20), nullable=False),
        sa.Column("ref_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_user_read", "notifications", ["user_id", "read_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_table("notifications")
```

- [ ] **Step 6: Verify migration on dev DB**

前置:确认开发库在跑(`docker compose up -d db`,若已在跑跳过)。

Run: `cd backend && alembic upgrade head && alembic check`
Expected: upgrade 应用 `b4c7e1a9d253`;`alembic check` 输出无漂移(No new upgrade operations detected)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/notification.py backend/alembic/versions/b4c7e1a9d253_add_notifications.py backend/alembic/env.py backend/tests/conftest.py backend/tests/test_notification_model.py
git commit -m "feat(backend): 新增 Notification 模型与 notifications 表迁移"
```

---

### Task 2: 通知 schemas + NotificationRepository

**Files:**
- Create: `backend/app/schemas/notification.py`
- Create: `backend/app/repositories/notification_repository.py`
- Modify: `backend/tests/conftest.py`(追加 make_notification 工厂 + `import uuid`)
- Test: `backend/tests/test_notification_repository.py`

**Interfaces:**
- Consumes: Task 1 的 `Notification` 模型
- Produces:
  - `NotificationRepository(db)`,方法:`get_by_id(notification_id) -> Notification | None`、`list_mine(user_id, is_read: bool | None, offset, limit) -> tuple[list[Notification], int]`、`unread_count(user_id) -> int`、`mark_read(notification) -> Notification`、`mark_all_read(user_id) -> int`
  - schemas:`NotificationResponse`、`NotificationListResponse`、`UnreadCountResponse`、`ReadAllResponse`(Task 4 用)
  - conftest 工厂 `make_notification(db, user, ..., read_at=None, created_at=None)`(后续测试任务用)

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_notification_repository.py`:

```python
from datetime import datetime

from sqlalchemy import select

from app.models.notification import Notification
from tests.conftest import make_notification, make_user


async def test_list_mine_only_own_and_desc(db):
    from app.repositories.notification_repository import NotificationRepository

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_notification(db, u1, title="旧", created_at=datetime(2026, 7, 1, 9, 0, 0))
    await make_notification(db, u1, title="新", created_at=datetime(2026, 7, 2, 9, 0, 0))
    await make_notification(db, u2, title="别人的")

    items, total = await NotificationRepository(db).list_mine(u1.id, None, 0, 20)
    assert total == 2
    assert [n.title for n in items] == ["新", "旧"]


async def test_list_mine_is_read_filter(db):
    from app.repositories.notification_repository import NotificationRepository

    u = await make_user(db, email="u1@x.com")
    await make_notification(db, u, title="未读")
    await make_notification(db, u, title="已读", read_at=datetime(2026, 7, 1, 10, 0, 0))

    repo = NotificationRepository(db)
    _, total_unread = await repo.list_mine(u.id, False, 0, 20)
    _, total_read = await repo.list_mine(u.id, True, 0, 20)
    _, total_all = await repo.list_mine(u.id, None, 0, 20)
    assert (total_unread, total_read, total_all) == (1, 1, 2)


async def test_list_mine_pagination(db):
    from app.repositories.notification_repository import NotificationRepository

    u = await make_user(db, email="u1@x.com")
    for i in range(3):
        await make_notification(db, u, title=f"n{i}", created_at=datetime(2026, 7, 1, 10, i, 0))

    items, total = await NotificationRepository(db).list_mine(u.id, None, 2, 2)
    assert total == 3
    assert len(items) == 1


async def test_unread_count(db):
    from app.repositories.notification_repository import NotificationRepository

    u = await make_user(db, email="u1@x.com")
    await make_notification(db, u)
    await make_notification(db, u)
    await make_notification(db, u, read_at=datetime(2026, 7, 1, 10, 0, 0))

    assert await NotificationRepository(db).unread_count(u.id) == 2


async def test_mark_read_sets_read_at_and_idempotent(db):
    from app.repositories.notification_repository import NotificationRepository

    u = await make_user(db, email="u1@x.com")
    n = await make_notification(db, u)
    repo = NotificationRepository(db)

    n = await repo.mark_read(n)
    assert n.read_at is not None
    first_read_at = n.read_at

    n = await repo.mark_read(n)
    assert n.read_at == first_read_at


async def test_mark_all_read_returns_updated_count(db):
    from app.repositories.notification_repository import NotificationRepository

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_notification(db, u1)
    await make_notification(db, u1)
    await make_notification(db, u1, read_at=datetime(2026, 7, 1, 10, 0, 0))
    await make_notification(db, u2)

    repo = NotificationRepository(db)
    assert await repo.mark_all_read(u1.id) == 2
    assert await repo.mark_all_read(u1.id) == 0
    assert await repo.unread_count(u2.id) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_notification_repository.py -v`
Expected: FAIL,conftest 无 `make_notification`(ImportError)

- [ ] **Step 3: Add factory + schemas + repository**

修改 `backend/tests/conftest.py`:文件顶部 import 区加 `import uuid`(若无),并在 `make_leave` 函数后追加:

```python
async def make_notification(
    db,
    user: User,
    type="leave_submitted",
    title="新的待审批任务",
    content="测试通知",
    ref_type="leave",
    ref_id=None,
    read_at=None,
    created_at=None,
) -> Notification:
    n = Notification(
        user_id=user.id,
        type=type,
        title=title,
        content=content,
        ref_type=ref_type,
        ref_id=ref_id or uuid.uuid4(),
        read_at=read_at,
    )
    if created_at is not None:
        n.created_at = created_at
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n
```

(注意:上面工厂签名里的 `user: User` 注解与 `Notification` 均已在 conftest import 区可用;同时把 conftest 中 Task 1 加的 `from app.models.notification import Notification` 行尾的 `# noqa: F401  # 注册进 metadata,create_all 用` 注释去掉——工厂真实引用后不再需要 noqa。)

创建 `backend/app/schemas/notification.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    title: str
    content: str
    ref_type: str
    ref_id: uuid.UUID
    read_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    count: int


class ReadAllResponse(BaseModel):
    updated: int
```

创建 `backend/app/repositories/notification_repository.py`:

```python
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        return await self.db.get(Notification, notification_id)

    async def list_mine(
        self, user_id: uuid.UUID, is_read: bool | None, offset: int, limit: int
    ) -> tuple[list[Notification], int]:
        conditions = [Notification.user_id == user_id]
        if is_read is True:
            conditions.append(Notification.read_at.is_not(None))
        elif is_read is False:
            conditions.append(Notification.read_at.is_(None))
        total = (
            await self.db.execute(
                select(func.count()).select_from(Notification).where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def unread_count(self, user_id: uuid.UUID) -> int:
        return (
            await self.db.execute(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ).scalar_one()

    async def mark_read(self, notification: Notification) -> Notification:
        if notification.read_at is None:
            await self.db.execute(
                update(Notification)
                .where(
                    Notification.id == notification.id,
                    Notification.read_at.is_(None),
                )
                .values(read_at=func.now())
            )
            await self.db.commit()
            await self.db.refresh(notification)
        return notification

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=func.now())
        )
        await self.db.commit()
        return result.rowcount
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_notification_repository.py -v`
Expected: 6 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/notification.py backend/app/repositories/notification_repository.py backend/tests/conftest.py backend/tests/test_notification_repository.py
git commit -m "feat(backend): 通知 schemas 与 NotificationRepository"
```

---

### Task 3: NotificationService(查询侧 + 三个通知生成器)

**Files:**
- Create: `backend/app/services/notification_service.py`
- Test: `backend/tests/test_notification_service.py`

**Interfaces:**
- Consumes: Task 2 的 `NotificationRepository`;conftest 的 `make_user/make_leave/make_notification`
- Produces:
  - `LEAVE_TYPE_LABELS: dict[str, str]`(personal/sick/annual/compensatory → 事假/病假/年假/调休)
  - `NotificationService(db)`:
    - `notify_leave_submitted(leave: LeaveRequest, applicant_name: str) -> None`(只 db.add,不 commit)
    - `notify_leave_approved(leave: LeaveRequest) -> None`(同上)
    - `notify_leave_rejected(leave: LeaveRequest, reason: str) -> None`(同上)
    - `list_mine(user, is_read, page, page_size) -> tuple[list[Notification], int]`
    - `unread_count(user) -> int`
    - `mark_read(notification_id, user) -> Notification`(不存在 404 NotFoundError("通知不存在"),非本人 403 ForbiddenError("无权操作该通知"))
    - `mark_all_read(user) -> int`

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_notification_service.py`:

```python
from datetime import date, datetime

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from tests.conftest import make_leave, make_notification, make_user


async def test_notify_leave_submitted_content(db):
    from app.services.notification_service import NotificationService

    approver = await make_user(db, email="m@x.com")
    applicant = await make_user(
        db, email="e@x.com", name="张三", manager_id=approver.id
    )
    leave = await make_leave(
        db, applicant, approver, type="sick",
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
    )

    NotificationService(db).notify_leave_submitted(leave, applicant.name)
    await db.commit()

    from app.repositories.notification_repository import NotificationRepository
    items, total = await NotificationRepository(db).list_mine(approver.id, None, 0, 20)
    assert total == 1
    n = items[0]
    assert n.type == "leave_submitted"
    assert n.title == "新的待审批任务"
    assert n.content == "张三 提交了 2026-08-01 ~ 2026-08-02 的病假申请,待您审批"
    assert n.ref_type == "leave"
    assert n.ref_id == leave.id
    assert n.read_at is None


async def test_notify_leave_approved_content(db):
    from app.services.notification_service import NotificationService

    approver = await make_user(db, email="m@x.com")
    applicant = await make_user(db, email="e@x.com", manager_id=approver.id)
    leave = await make_leave(db, applicant, approver, type="annual")

    NotificationService(db).notify_leave_approved(leave)
    await db.commit()

    from app.repositories.notification_repository import NotificationRepository
    items, total = await NotificationRepository(db).list_mine(applicant.id, None, 0, 20)
    assert total == 1
    n = items[0]
    assert n.type == "leave_approved"
    assert n.title == "请假申请已通过"
    assert n.content == "您 2026-08-01 ~ 2026-08-02 的年假申请已通过"


async def test_notify_leave_rejected_content(db):
    from app.services.notification_service import NotificationService

    approver = await make_user(db, email="m@x.com")
    applicant = await make_user(db, email="e@x.com", manager_id=approver.id)
    leave = await make_leave(db, applicant, approver, type="personal")

    NotificationService(db).notify_leave_rejected(leave, "人手不足")
    await db.commit()

    from app.repositories.notification_repository import NotificationRepository
    items, total = await NotificationRepository(db).list_mine(applicant.id, None, 0, 20)
    assert total == 1
    n = items[0]
    assert n.type == "leave_rejected"
    assert n.title == "请假申请已驳回"
    assert n.content == "您 2026-08-01 ~ 2026-08-02 的事假申请已被驳回:人手不足"


async def test_mark_read_not_found(db):
    import uuid

    from app.services.notification_service import NotificationService

    u = await make_user(db, email="u1@x.com")
    with pytest.raises(NotFoundError):
        await NotificationService(db).mark_read(uuid.uuid4(), u)


async def test_mark_read_forbidden_when_not_owner(db):
    from app.services.notification_service import NotificationService

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    n = await make_notification(db, u1)

    with pytest.raises(ForbiddenError):
        await NotificationService(db).mark_read(n.id, u2)


async def test_mark_read_success_idempotent(db):
    from app.services.notification_service import NotificationService

    u = await make_user(db, email="u1@x.com")
    n = await make_notification(db, u)
    svc = NotificationService(db)

    n = await svc.mark_read(n.id, u)
    assert n.read_at is not None
    again = await svc.mark_read(n.id, u)
    assert again.read_at == n.read_at


async def test_mark_all_read_only_own(db):
    from app.services.notification_service import NotificationService

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_notification(db, u1)
    await make_notification(db, u1, read_at=datetime(2026, 7, 1, 10, 0, 0))
    await make_notification(db, u2)

    svc = NotificationService(db)
    assert await svc.mark_all_read(u1) == 1
    assert await svc.mark_all_read(u1) == 0
    assert await svc.unread_count(u2) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_notification_service.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.services.notification_service'`

- [ ] **Step 3: Write the service**

创建 `backend/app/services/notification_service.py`:

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.leave import LeaveRequest
from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository

LEAVE_TYPE_LABELS = {
    "personal": "事假",
    "sick": "病假",
    "annual": "年假",
    "compensatory": "调休",
}


def _leave_span(leave: LeaveRequest) -> str:
    return f"{leave.start_date.isoformat()} ~ {leave.end_date.isoformat()}"


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.notifications = NotificationRepository(db)

    def notify_leave_submitted(
        self, leave: LeaveRequest, applicant_name: str
    ) -> None:
        label = LEAVE_TYPE_LABELS.get(leave.type, leave.type)
        self.db.add(
            Notification(
                user_id=leave.approver_id,
                type="leave_submitted",
                title="新的待审批任务",
                content=f"{applicant_name} 提交了 {_leave_span(leave)} 的{label}申请,待您审批",
                ref_type="leave",
                ref_id=leave.id,
            )
        )

    def notify_leave_approved(self, leave: LeaveRequest) -> None:
        label = LEAVE_TYPE_LABELS.get(leave.type, leave.type)
        self.db.add(
            Notification(
                user_id=leave.applicant_id,
                type="leave_approved",
                title="请假申请已通过",
                content=f"您 {_leave_span(leave)} 的{label}申请已通过",
                ref_type="leave",
                ref_id=leave.id,
            )
        )

    def notify_leave_rejected(self, leave: LeaveRequest, reason: str) -> None:
        label = LEAVE_TYPE_LABELS.get(leave.type, leave.type)
        self.db.add(
            Notification(
                user_id=leave.applicant_id,
                type="leave_rejected",
                title="请假申请已驳回",
                content=f"您 {_leave_span(leave)} 的{label}申请已被驳回:{reason}",
                ref_type="leave",
                ref_id=leave.id,
            )
        )

    async def list_mine(
        self, user: User, is_read: bool | None, page: int, page_size: int
    ) -> tuple[list[Notification], int]:
        return await self.notifications.list_mine(
            user.id, is_read, (page - 1) * page_size, page_size
        )

    async def unread_count(self, user: User) -> int:
        return await self.notifications.unread_count(user.id)

    async def mark_read(
        self, notification_id: uuid.UUID, user: User
    ) -> Notification:
        n = await self.notifications.get_by_id(notification_id)
        if n is None:
            raise NotFoundError("通知不存在")
        if n.user_id != user.id:
            raise ForbiddenError("无权操作该通知")
        return await self.notifications.mark_read(n)

    async def mark_all_read(self, user: User) -> int:
        return await self.notifications.mark_all_read(user.id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_notification_service.py -v`
Expected: 7 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notification_service.py backend/tests/test_notification_service.py
git commit -m "feat(backend): NotificationService 查询与三个通知生成器"
```

---

### Task 4: /notifications 四个 API 接口

**Files:**
- Create: `backend/app/api/v1/notifications.py`
- Modify: `backend/app/main.py:3,14`(import + include_router)
- Test: `backend/tests/test_notifications_api.py`

**Interfaces:**
- Consumes: Task 3 的 `NotificationService`;Task 2 的 schemas;`app.core.dependencies.get_current_user`
- Produces: `GET /api/v1/notifications`、`GET /api/v1/notifications/unread-count`、`POST /api/v1/notifications/read-all`、`POST /api/v1/notifications/{id}/read`(Task 5 集成测直接调这些接口验证触发结果)

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_notifications_api.py`:

```python
import uuid
from datetime import datetime

from tests.conftest import login_token, make_notification, make_user


async def make_client(db, client, email="u1@x.com"):
    user = await make_user(db, email=email, password="Passw0rd!")
    token = await login_token(client, email, "Passw0rd!")
    return user, {"Authorization": f"Bearer {token}"}


async def test_list_empty(db, client):
    _, headers = await make_client(db, client)
    resp = await client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 20}


async def test_list_only_own(db, client):
    u1, headers = await make_client(db, client, "u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_notification(db, u1, title="我的")
    await make_notification(db, u2, title="别人的")

    resp = await client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "我的"


async def test_list_is_read_filter(db, client):
    u1, headers = await make_client(db, client)
    await make_notification(db, u1, title="未读")
    await make_notification(db, u1, title="已读", read_at=datetime(2026, 7, 1, 10, 0, 0))

    resp = await client.get("/api/v1/notifications?is_read=false", headers=headers)
    assert [i["title"] for i in resp.json()["items"]] == ["未读"]
    resp = await client.get("/api/v1/notifications?is_read=true", headers=headers)
    assert [i["title"] for i in resp.json()["items"]] == ["已读"]


async def test_list_pagination(db, client):
    u1, headers = await make_client(db, client)
    for i in range(3):
        await make_notification(db, u1, title=f"n{i}", created_at=datetime(2026, 7, 1, 10, i, 0))

    resp = await client.get("/api/v1/notifications?page=2&page_size=2", headers=headers)
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["page"] == 2
    assert body["page_size"] == 2


async def test_unread_count(db, client):
    u1, headers = await make_client(db, client)
    await make_notification(db, u1)
    await make_notification(db, u1)
    await make_notification(db, u1, read_at=datetime(2026, 7, 1, 10, 0, 0))

    resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"count": 2}


async def test_read_marks_and_idempotent(db, client):
    u1, headers = await make_client(db, client)
    n = await make_notification(db, u1)

    resp = await client.post(f"/api/v1/notifications/{n.id}/read", headers=headers)
    assert resp.status_code == 200
    first = resp.json()["read_at"]
    assert first is not None

    resp = await client.post(f"/api/v1/notifications/{n.id}/read", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["read_at"] == first


async def test_read_not_found_404(db, client):
    _, headers = await make_client(db, client)
    resp = await client.post(f"/api/v1/notifications/{uuid.uuid4()}/read", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_read_forbidden_403(db, client):
    u1 = await make_user(db, email="owner@x.com")
    n = await make_notification(db, u1)
    _, headers = await make_client(db, client, "other@x.com")

    resp = await client.post(f"/api/v1/notifications/{n.id}/read", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_read_all_then_zero(db, client):
    u1, headers = await make_client(db, client)
    await make_notification(db, u1)
    await make_notification(db, u1)

    resp = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"updated": 2}

    resp = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert resp.json() == {"updated": 0}


async def test_unauthenticated_401(client):
    assert (await client.get("/api/v1/notifications")).status_code == 401
    assert (await client.get("/api/v1/notifications/unread-count")).status_code == 401
    assert (await client.post("/api/v1/notifications/read-all")).status_code == 401
    assert (await client.post(f"/api/v1/notifications/{uuid.uuid4()}/read")).status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_notifications_api.py -v`
Expected: FAIL,404/405(路由不存在)

- [ ] **Step 3: Write the router + register**

创建 `backend/app/api/v1/notifications.py`:

```python
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    ReadAllResponse,
    UnreadCountResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    is_read: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await NotificationService(db).list_mine(
        current_user, is_read, page, page_size
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = await NotificationService(db).unread_count(current_user)
    return UnreadCountResponse(count=count)


@router.post("/read-all", response_model=ReadAllResponse)
async def read_all(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = await NotificationService(db).mark_all_read(current_user)
    return ReadAllResponse(updated=updated)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def read_one(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await NotificationService(db).mark_read(notification_id, current_user)
```

修改 `backend/app/main.py`:

- 第 3 行 import 改为:`from app.api.v1 import auth, departments, leaves, notifications, roles, users`
- 在 `api_v1.include_router(leaves.router)` 后加:`api_v1.include_router(notifications.router)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_notifications_api.py -v`
Expected: 10 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/notifications.py backend/app/main.py backend/tests/test_notifications_api.py
git commit -m "feat(backend): /notifications 列表/未读数/标记已读四个接口"
```

---

### Task 5: LeaveService 三触发点接线

**Files:**
- Modify: `backend/app/services/leave_service.py`(__init__ 持有 db + NotificationService;create/approve/reject 三个触发点)
- Test: `backend/tests/test_leave_notifications.py`

**Interfaces:**
- Consumes: Task 3 的 `NotificationService.notify_leave_*`;Task 4 的 `/notifications` 接口(验证用)
- Produces: 提交请假→审批人收 leave_submitted;通过→申请人收 leave_approved;驳回→申请人收 leave_rejected(含原因);撤回→无通知。通知与动作同事务提交

**关键实现约束(必须遵守,否则原子性失效):**
- `notify_leave_*` 只做 `db.add()`,**不得** commit;commit 由 `LeaveRepository.create/transition` 既有逻辑完成
- `create_leave` 中 `LeaveRequest` 必须显式传 `id=uuid.uuid4()`——否则 add 通知时 `leave.id` 还是 None(client 端 default 要到 INSERT 才生成),ref_id 会落空
- approve/reject 中 notify 调用放在 `_check_pending` 之后、`transition` 之前;若 transition 因并发 rowcount=0 回滚,挂起的通知 add 会随 rollback 一并丢弃,语义正确

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_leave_notifications.py`(helper 风格对齐 test_leaves_api.py):

```python
from sqlalchemy import select

from app.models.permission import Permission
from tests.conftest import (
    login_token,
    make_leave,
    make_permission,
    make_role,
    make_user,
)

LEAVE_JSON = {
    "type": "personal",
    "start_date": "2026-08-01",
    "end_date": "2026-08-02",
    "reason": "私事",
}


async def leave_permissions(db):
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


async def make_employee_client(db, client, manager, email="emp@x.com", name="张三"):
    perms = await leave_permissions(db)
    role = await make_role(db, code=f"employee-{email}", name="员工", permissions=perms[:2])
    emp = await make_user(
        db, email=email, password="Passw0rd!", name=name,
        roles=[role], manager_id=manager.id,
    )
    token = await login_token(client, email, "Passw0rd!")
    return emp, {"Authorization": f"Bearer {token}"}


async def unread_count(client, headers) -> int:
    resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.status_code == 200
    return resp.json()["count"]


async def latest_notification(client, headers) -> dict:
    resp = await client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    return resp.json()["items"][0]


async def test_submit_notifies_approver(db, client):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    resp = await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=emp_h)
    assert resp.status_code == 201

    assert await unread_count(client, mgr_h) == 1
    n = await latest_notification(client, mgr_h)
    assert n["type"] == "leave_submitted"
    assert n["title"] == "新的待审批任务"
    assert n["content"] == "张三 提交了 2026-08-01 ~ 2026-08-02 的事假申请,待您审批"
    assert n["ref_type"] == "leave"
    assert n["ref_id"] == resp.json()["id"]
    assert n["read_at"] is None


async def test_approve_notifies_applicant(db, client):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    leave_id = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=emp_h)
    ).json()["id"]

    resp = await client.post(f"/api/v1/leaves/{leave_id}/approve", headers=mgr_h)
    assert resp.status_code == 200

    n = await latest_notification(client, emp_h)
    assert n["type"] == "leave_approved"
    assert n["title"] == "请假申请已通过"
    assert n["content"] == "您 2026-08-01 ~ 2026-08-02 的事假申请已通过"


async def test_reject_notifies_applicant_with_reason(db, client):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    leave_id = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=emp_h)
    ).json()["id"]

    resp = await client.post(
        f"/api/v1/leaves/{leave_id}/reject",
        json={"reason": "人手不足"},
        headers=mgr_h,
    )
    assert resp.status_code == 200

    n = await latest_notification(client, emp_h)
    assert n["type"] == "leave_rejected"
    assert n["title"] == "请假申请已驳回"
    assert n["content"] == "您 2026-08-01 ~ 2026-08-02 的事假申请已被驳回:人手不足"


async def test_cancel_sends_no_notification(db, client):
    mgr, mgr_h = await make_manager_client(db, client)
    emp, emp_h = await make_employee_client(db, client, mgr)
    leave_id = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=emp_h)
    ).json()["id"]
    # 提交已各产生 1 条(审批人 1 条),记录基线
    mgr_baseline = await unread_count(client, mgr_h)
    emp_baseline = await unread_count(client, emp_h)

    resp = await client.post(f"/api/v1/leaves/{leave_id}/cancel", headers=emp_h)
    assert resp.status_code == 200

    assert await unread_count(client, mgr_h) == mgr_baseline
    assert await unread_count(client, emp_h) == emp_baseline


async def test_failed_action_rolls_back_notification(db, client):
    """重复审批第二次 409:第一次的通知保留,第二次不产生新通知。"""
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    leave_id = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=emp_h)
    ).json()["id"]
    await client.post(f"/api/v1/leaves/{leave_id}/approve", headers=mgr_h)
    baseline = await unread_count(client, emp_h)

    resp = await client.post(f"/api/v1/leaves/{leave_id}/approve", headers=mgr_h)
    assert resp.status_code == 409
    assert await unread_count(client, emp_h) == baseline
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_leave_notifications.py -v`
Expected: `test_submit_notifies_approver` FAIL(unread_count 为 0,`latest_notification` 取 items[0] IndexError 或断言不等)

- [ ] **Step 3: Wire the triggers in LeaveService**

修改 `backend/app/services/leave_service.py`:

1) import 区追加:

```python
from app.services.notification_service import NotificationService
```

2) `__init__` 改为:

```python
    def __init__(self, db: AsyncSession):
        self.db = db
        self.leaves = LeaveRepository(db)
        self.notifications = NotificationService(db)
```

3) `create_leave` 中,`leave = LeaveRequest(...)` 改为显式带 id,并在 `return await self.leaves.create(leave, history)` 前加 notify:

```python
        leave = LeaveRequest(
            id=uuid.uuid4(),
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
        self.notifications.notify_leave_submitted(leave, applicant.name)
        return await self.leaves.create(leave, history)
```

4) `approve_leave` 改为:

```python
    async def approve_leave(self, leave_id: uuid.UUID, user: User) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        self._check_approver(leave, user)
        self._check_pending(leave)
        self.notifications.notify_leave_approved(leave)
        return await self.leaves.transition(
            leave, "pending", "approved", user.id, None
        )
```

5) `reject_leave` 改为:

```python
    async def reject_leave(
        self, leave_id: uuid.UUID, user: User, reason: str
    ) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        self._check_approver(leave, user)
        self._check_pending(leave)
        if not reason.strip():
            raise ValidationError("驳回必须填写原因")
        self.notifications.notify_leave_rejected(leave, reason)
        return await self.leaves.transition(
            leave, "pending", "rejected", user.id, reason
        )
```

`cancel_leave` **不改**(撤回不通知)。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_leave_notifications.py -v`
Expected: 5 个 PASS

- [ ] **Step 5: Run leave regression suite**

Run: `cd backend && pytest tests/test_leave_service.py tests/test_leaves_api.py tests/test_leave_repository.py -v`
Expected: 全部 PASS(create_leave 显式 id 不改变任何既有行为)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/leave_service.py backend/tests/test_leave_notifications.py
git commit -m "feat(backend): 请假提交/通过/驳回同步生成站内通知"
```

---

### Task 6: 全量验收 + spec 勾选

**Files:**
- Modify: `docs/superpowers/specs/2026-07-26-backend-notification-design.md`(§9 五个 `- [ ]` → `- [x]`)

**Interfaces:**
- Consumes: Task 1-5 全部产出
- Produces: 可 PR 的完整分支

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && pytest`
Expected: 全部 PASS(既有 176 + 本分支新增 28,无回归)

- [ ] **Step 2: Migration reversibility**

Run: `cd backend && alembic downgrade -1 && alembic upgrade head && alembic check`
Expected: downgrade 回到 `5f3a8c1d9e02`、upgrade 重回 `b4c7e1a9d253`、`alembic check` 无漂移

- [ ] **Step 3: Tick spec acceptance boxes**

把 `docs/superpowers/specs/2026-07-26-backend-notification-design.md` §9 的 5 个 `- [ ]` 全部改为 `- [x]`:

```markdown
- [x] 有新的待审批任务时,审批人收到站内通知
- [x] 申请被通过/驳回时,申请人收到站内通知(驳回通知含原因)
- [x] 通知可标记已读/未读,支持单条与全部标记
- [x] 用户可在消息中心(列表接口)查看历史通知(含全部读态)
- [x] 未读数接口可供前端轮询角标
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-26-backend-notification-design.md
git commit -m "test(backend): 通知模块全量验收通过,勾选 spec 验收标准"
```

---

## Self-Review 记录

- **Spec 覆盖**:spec §3 表结构→Task 1;§4 触发点与模板→Task 3(生成器)+Task 5(接线);§5 四接口→Task 4;§6 错误语义→Task 3(404/403)+Task 4(401);§7 测试策略→各任务测试 + Task 6 迁移验证;§8 部署→Task 1/6 alembic;§9 验收→Task 6 勾选。无缺口。
- **占位符扫描**:无 TBD/TODO;所有代码块为完整可复制内容。
- **类型一致性**:`NotificationRepository` 方法签名在 Task 2 定义、Task 3 消费一致;`NotificationService.notify_leave_*(leave, ...)` 在 Task 3 定义、Task 5 调用一致;`make_notification` 工厂在 Task 2 定义、Task 3/4 测试使用一致;接口路径与 Task 4 测试、Task 5 集成测一致。
- **已知取舍**:`list_mine` 按 `created_at desc` 排序,SQLite CURRENT_TIMESTAMP 为秒级精度,同秒插入的多行顺序不定——测试一律用 `make_notification(created_at=...)` 显式区分时间,避免 flaky。
