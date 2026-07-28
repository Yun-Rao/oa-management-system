# P2 数据看板(后端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现数据看板后端聚合接口 `GET /api/v1/dashboard`:部门请假统计(approved,跨月切分)、部门报销统计(approved,创建月归属)、审批时效(终审完成月,含驳回不含撤回),Admin 全量、Manager 限本部门。

**Architecture:** 单聚合端点,镜像 expense 分层 `api/v1 → services → repositories`;无新表、无迁移。仓储层 SQL 只做状态/月份/部门过滤返回候选行,聚合(分组/求和/跨月天数切分/平均时长)在 Python 服务层完成(SQLite/Pg 日期算术不可移植)。

**Tech Stack:** FastAPI + SQLAlchemy Async + pydantic v2;pytest + httpx AsyncClient + 内存 SQLite。

## Global Constraints

- 工作分支:`feature/backend-dashboard`(已在此分支,不切分支)
- 提交只 `git add` 明确列出的文件,**严禁** `git add .` / `git add -A`
- Commit message:中文 Conventional Commits(参照 git log 现有风格,如 `feat(backend): ...`)
- 设计依据:`docs/superpowers/specs/2026-07-28-dashboard-design.md`,实现必须与 spec 一致
- 不改 frontend/、不引入新 Python 依赖、无新表无 Alembic 迁移;seed 只追加 2 个 dashboard 权限点及 manager 映射(Task 4)
- 测试库为内存 SQLite:SQL 只用可移植构造(禁止 `julianday`、`EXTRACT` 等方言日期函数);聚合一律在 Python 服务层
- 运行 pytest 的工作目录是 `backend/`(`pytest.ini` 在其中,asyncio_mode=auto)
- 权限作用域判定(关键陷阱):`"dashboard:view_all" ∈ perms` → `department_id=None`(不过滤);否则 `department_id=user.department_id`;**user 无部门时必须在服务层提前返回空集**——`department_id=None` 传给仓储表示"不过滤",直接透传会泄露全公司数据
- 统计口径以 spec §4 为准:请假只算 approved 且与当月有交集、天数按交集切分;报销只算 approved 按 created_at 归属月;时效按 history 终态行(approved/rejected)created_at 落月,cancelled 不计,不拆级别

---

### Task 1: DashboardRepository(行查询)

**Files:**
- Create: `backend/app/repositories/dashboard_repository.py`
- Test: `backend/tests/test_dashboard_repository.py`

**Interfaces:**
- Consumes: 既有 `LeaveRequest`/`LeaveStatusHistory`、`ExpenseRequest`/`ExpenseStatusHistory`、`User`、`Department` 模型;conftest 工厂 `make_user`(支持 department_id)/`make_department`/`make_leave`/`make_expense`
- Produces: `DashboardRepository(db)`:
  - `leave_rows(month_start: date, month_end: date, department_id: uuid.UUID | None) -> list[Row]`,Row = `(department_id, department_name, start_date, end_date)`
  - `expense_rows(month_start, month_end, department_id) -> list[Row]`,Row = `(department_id, department_name, amount)`
  - `duration_rows(month_start, month_end, department_id) -> list[Row]`,Row = `(category: str, created_at: datetime, finished_at: datetime)`;category ∈ `"leave"` / `"expense"`
  - `department_id=None` 一律表示"不过滤"(Task 2 服务层负责拦截无部门 Manager)

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_dashboard_repository.py`:

```python
from datetime import date, datetime
from decimal import Decimal

from app.models.expense import ExpenseStatusHistory
from app.models.leave import LeaveStatusHistory
from tests.conftest import (
    make_department,
    make_expense,
    make_leave,
    make_user,
)


async def test_leave_rows_status_and_overlap(db):
    from app.repositories.dashboard_repository import DashboardRepository

    dept_a = await make_department(db, name="技术部")
    dept_b = await make_department(db, name="市场部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept_a.id)
    u2 = await make_user(db, email="u2@x.com", department_id=dept_b.id)
    u3 = await make_user(db, email="u3@x.com")  # 无部门

    # 当月 approved(计)
    await make_leave(db, u1, mgr, start_date=date(2026, 7, 10), end_date=date(2026, 7, 12), status="approved")
    # 跨月 approved 6/30-7/2(计,原样返回起止,切分在服务层)
    await make_leave(db, u1, mgr, start_date=date(2026, 6, 30), end_date=date(2026, 7, 2), status="approved")
    # pending / rejected(不计)
    await make_leave(db, u1, mgr, start_date=date(2026, 7, 5), end_date=date(2026, 7, 6), status="pending")
    await make_leave(db, u2, mgr, start_date=date(2026, 7, 5), end_date=date(2026, 7, 6), status="rejected")
    # 上月 approved(不计)
    await make_leave(db, u2, mgr, start_date=date(2026, 6, 1), end_date=date(2026, 6, 3), status="approved")
    # 无部门用户 approved(INNER JOIN departments,不计)
    await make_leave(db, u3, mgr, start_date=date(2026, 7, 1), end_date=date(2026, 7, 1), status="approved")

    repo = DashboardRepository(db)
    rows = await repo.leave_rows(date(2026, 7, 1), date(2026, 7, 31), None)
    assert len(rows) == 2
    assert all(r[1] == "技术部" for r in rows)

    # department_id 过滤
    assert len(await repo.leave_rows(date(2026, 7, 1), date(2026, 7, 31), dept_a.id)) == 2
    assert await repo.leave_rows(date(2026, 7, 1), date(2026, 7, 31), dept_b.id) == []


async def test_expense_rows_month_and_status(db):
    from app.repositories.dashboard_repository import DashboardRepository

    dept = await make_department(db, name="技术部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept.id)

    await make_expense(db, u1, mgr, amount=Decimal("100.00"), status="approved")
    # approved 但创建于上月(不计,显式改 created_at)
    e2 = await make_expense(db, u1, mgr, amount=Decimal("200.00"), status="approved")
    e2.created_at = datetime(2026, 6, 15, 10, 0, 0)
    # pending_l1 / rejected(不计)
    await make_expense(db, u1, mgr, status="pending_l1")
    await make_expense(db, u1, mgr, status="rejected")
    await db.commit()

    rows = await DashboardRepository(db).expense_rows(
        date(2026, 7, 1), date(2026, 7, 31), None
    )
    assert len(rows) == 1
    assert rows[0][1] == "技术部"
    assert rows[0][2] == Decimal("100.00")


async def test_duration_rows_leave(db):
    from app.repositories.dashboard_repository import DashboardRepository

    dept = await make_department(db, name="技术部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept.id)

    # 当月 approved(计)
    l1 = await make_leave(db, u1, mgr, status="approved")
    l1.created_at = datetime(2026, 7, 10, 9, 0, 0)
    db.add(LeaveStatusHistory(
        request_id=l1.id, from_status="pending", to_status="approved",
        actor_id=mgr.id, created_at=datetime(2026, 7, 11, 9, 0, 0),
    ))
    # 当月 rejected(计)
    l2 = await make_leave(db, u1, mgr, status="rejected")
    l2.created_at = datetime(2026, 7, 12, 9, 0, 0)
    db.add(LeaveStatusHistory(
        request_id=l2.id, from_status="pending", to_status="rejected",
        actor_id=mgr.id, comment="x", created_at=datetime(2026, 7, 12, 21, 0, 0),
    ))
    # cancelled(不计)
    l3 = await make_leave(db, u1, mgr, status="cancelled")
    l3.created_at = datetime(2026, 7, 1, 9, 0, 0)
    db.add(LeaveStatusHistory(
        request_id=l3.id, from_status="pending", to_status="cancelled",
        actor_id=u1.id, created_at=datetime(2026, 7, 1, 10, 0, 0),
    ))
    # 上月完成(不计)
    l4 = await make_leave(db, u1, mgr, status="approved")
    l4.created_at = datetime(2026, 6, 20, 9, 0, 0)
    db.add(LeaveStatusHistory(
        request_id=l4.id, from_status="pending", to_status="approved",
        actor_id=mgr.id, created_at=datetime(2026, 6, 21, 9, 0, 0),
    ))
    await db.commit()

    rows = await DashboardRepository(db).duration_rows(
        date(2026, 7, 1), date(2026, 7, 31), None
    )
    leave_rows = [r for r in rows if r[0] == "leave"]
    assert len(leave_rows) == 2


async def test_duration_rows_expense_and_department_filter(db):
    from app.repositories.dashboard_repository import DashboardRepository

    dept_a = await make_department(db, name="技术部")
    dept_b = await make_department(db, name="市场部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept_a.id)
    u2 = await make_user(db, email="u2@x.com", department_id=dept_b.id)

    e1 = await make_expense(db, u1, mgr, amount=Decimal("500.00"), status="approved")
    e1.created_at = datetime(2026, 7, 5, 10, 0, 0)
    db.add(ExpenseStatusHistory(
        request_id=e1.id, from_status="pending_l1", to_status="approved",
        actor_id=mgr.id, created_at=datetime(2026, 7, 6, 10, 0, 0),
    ))
    e2 = await make_expense(db, u2, mgr, amount=Decimal("300.00"), status="rejected")
    e2.created_at = datetime(2026, 7, 7, 10, 0, 0)
    db.add(ExpenseStatusHistory(
        request_id=e2.id, from_status="pending_l1", to_status="rejected",
        actor_id=mgr.id, comment="x", created_at=datetime(2026, 7, 8, 10, 0, 0),
    ))
    await db.commit()

    repo = DashboardRepository(db)
    rows = await repo.duration_rows(date(2026, 7, 1), date(2026, 7, 31), None)
    expense_rows = [r for r in rows if r[0] == "expense"]
    assert len(expense_rows) == 2

    rows = await repo.duration_rows(date(2026, 7, 1), date(2026, 7, 31), dept_a.id)
    assert len(rows) == 1
    assert rows[0][0] == "expense"
    assert rows[0][1] == datetime(2026, 7, 5, 10, 0, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_dashboard_repository.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.repositories.dashboard_repository'`

- [ ] **Step 3: Write the repository**

创建 `backend/app/repositories/dashboard_repository.py`:

```python
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.expense import ExpenseRequest, ExpenseStatusHistory
from app.models.leave import LeaveRequest, LeaveStatusHistory
from app.models.user import User

TERMINAL_STATUSES = ("approved", "rejected")


class DashboardRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def leave_rows(
        self, month_start: date, month_end: date, department_id: uuid.UUID | None
    ):
        conditions = [
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= month_end,
            LeaveRequest.end_date >= month_start,
        ]
        if department_id is not None:
            conditions.append(User.department_id == department_id)
        result = await self.db.execute(
            select(
                Department.id,
                Department.name,
                LeaveRequest.start_date,
                LeaveRequest.end_date,
            )
            .select_from(LeaveRequest)
            .join(User, LeaveRequest.applicant_id == User.id)
            .join(Department, User.department_id == Department.id)
            .where(*conditions)
        )
        return list(result.all())

    async def expense_rows(
        self, month_start: date, month_end: date, department_id: uuid.UUID | None
    ):
        start_dt, end_dt = _month_bounds(month_start, month_end)
        conditions = [
            ExpenseRequest.status == "approved",
            ExpenseRequest.created_at >= start_dt,
            ExpenseRequest.created_at < end_dt,
        ]
        if department_id is not None:
            conditions.append(User.department_id == department_id)
        result = await self.db.execute(
            select(Department.id, Department.name, ExpenseRequest.amount)
            .select_from(ExpenseRequest)
            .join(User, ExpenseRequest.applicant_id == User.id)
            .join(Department, User.department_id == Department.id)
            .where(*conditions)
        )
        return list(result.all())

    async def duration_rows(
        self, month_start: date, month_end: date, department_id: uuid.UUID | None
    ):
        start_dt, end_dt = _month_bounds(month_start, month_end)
        leave_q = (
            select(
                literal("leave").label("category"),
                LeaveRequest.created_at,
                LeaveStatusHistory.created_at.label("finished_at"),
            )
            .select_from(LeaveStatusHistory)
            .join(LeaveRequest, LeaveStatusHistory.request_id == LeaveRequest.id)
            .join(User, LeaveRequest.applicant_id == User.id)
            .where(
                LeaveStatusHistory.to_status.in_(TERMINAL_STATUSES),
                LeaveStatusHistory.created_at >= start_dt,
                LeaveStatusHistory.created_at < end_dt,
            )
        )
        expense_q = (
            select(
                literal("expense").label("category"),
                ExpenseRequest.created_at,
                ExpenseStatusHistory.created_at.label("finished_at"),
            )
            .select_from(ExpenseStatusHistory)
            .join(ExpenseRequest, ExpenseStatusHistory.request_id == ExpenseRequest.id)
            .join(User, ExpenseRequest.applicant_id == User.id)
            .where(
                ExpenseStatusHistory.to_status.in_(TERMINAL_STATUSES),
                ExpenseStatusHistory.created_at >= start_dt,
                ExpenseStatusHistory.created_at < end_dt,
            )
        )
        if department_id is not None:
            leave_q = leave_q.where(User.department_id == department_id)
            expense_q = expense_q.where(User.department_id == department_id)
        rows = list((await self.db.execute(leave_q)).all())
        rows += list((await self.db.execute(expense_q)).all())
        return rows


def _month_bounds(month_start: date, month_end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(month_start, time.min),
        datetime.combine(month_end + timedelta(days=1), time.min),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_dashboard_repository.py -v`
Expected: 4 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/dashboard_repository.py backend/tests/test_dashboard_repository.py
git commit -m "feat(backend): DashboardRepository 看板行查询"
```

---

### Task 2: schemas + DashboardService(聚合与作用域)

**Files:**
- Create: `backend/app/schemas/dashboard.py`
- Create: `backend/app/services/dashboard_service.py`
- Test: `backend/tests/test_dashboard_service.py`

**Interfaces:**
- Consumes: Task 1 的 `DashboardRepository.leave_rows / expense_rows / duration_rows`
- Produces:
  - `DashboardService(db).get_summary(month: date | None, user: User) -> DashboardSummaryResponse`(month=None → 当前月)
  - schemas:`LeaveStatItem(department_id/department_name/request_count/total_days: float)`、`ExpenseStatItem(...total_amount: Decimal)`、`ApprovalDurationItem(category/completed_count/avg_hours: float | None)`、`DashboardSummaryResponse(month: str, leave_stats, expense_stats, approval_durations)`
  - Task 3 路由仅调用 `get_summary`

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_dashboard_service.py`:

```python
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models.expense import ExpenseStatusHistory
from app.models.leave import LeaveStatusHistory
from app.models.permission import Permission
from tests.conftest import (
    make_department,
    make_expense,
    make_leave,
    make_permission,
    make_role,
    make_user,
)


async def perms_role(db, codes, role_code):
    existing = {p.code: p for p in (await db.execute(select(Permission))).scalars()}
    perms = [
        existing.get(c) or await make_permission(db, code=c, name=c) for c in codes
    ]
    return await make_role(db, code=role_code, name=role_code, permissions=perms)


async def test_summary_aggregates_and_clips(db):
    from app.services.dashboard_service import DashboardService

    dept = await make_department(db, name="技术部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept.id)
    # 跨月假 7/30-8/2 → 7 月切分计 2 天
    await make_leave(db, u1, mgr, start_date=date(2026, 7, 30), end_date=date(2026, 8, 2), status="approved")
    # 月内假 3 天
    await make_leave(db, u1, mgr, start_date=date(2026, 7, 6), end_date=date(2026, 7, 8), status="approved")
    e1 = await make_expense(db, u1, mgr, amount=Decimal("100.50"), status="approved")
    e1.created_at = datetime(2026, 7, 15, 10, 0, 0)
    e2 = await make_expense(db, u1, mgr, amount=Decimal("200.25"), status="approved")
    e2.created_at = datetime(2026, 7, 16, 10, 0, 0)
    await db.commit()

    admin = await make_user(
        db, email="a@x.com",
        roles=[await perms_role(db, ["dashboard:view", "dashboard:view_all"], "adm-r")],
    )
    summary = await DashboardService(db).get_summary(date(2026, 7, 1), admin)

    assert summary.month == "2026-07"
    assert len(summary.leave_stats) == 1
    ls = summary.leave_stats[0]
    assert ls.department_name == "技术部"
    assert ls.request_count == 2
    assert ls.total_days == 5.0  # 2(切分) + 3
    assert len(summary.expense_stats) == 1
    es = summary.expense_stats[0]
    assert es.request_count == 2
    assert es.total_amount == Decimal("300.75")


async def test_summary_avg_hours(db):
    from app.services.dashboard_service import DashboardService

    dept = await make_department(db, name="技术部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept.id)

    l1 = await make_leave(db, u1, mgr, status="approved")
    l1.created_at = datetime(2026, 7, 10, 9, 0, 0)
    db.add(LeaveStatusHistory(
        request_id=l1.id, from_status="pending", to_status="approved",
        actor_id=mgr.id, created_at=datetime(2026, 7, 11, 9, 0, 0),
    ))
    e1 = await make_expense(db, u1, mgr, amount=Decimal("10.00"), status="approved")
    e1.created_at = datetime(2026, 7, 1, 8, 0, 0)
    db.add(ExpenseStatusHistory(
        request_id=e1.id, from_status="pending_l1", to_status="approved",
        actor_id=mgr.id, created_at=datetime(2026, 7, 1, 20, 0, 0),
    ))
    await db.commit()

    admin = await make_user(
        db, email="a@x.com",
        roles=[await perms_role(db, ["dashboard:view", "dashboard:view_all"], "adm-r")],
    )
    summary = await DashboardService(db).get_summary(date(2026, 7, 1), admin)
    d = {x.category: x for x in summary.approval_durations}
    assert d["leave"].completed_count == 1
    assert d["leave"].avg_hours == 24.0
    assert d["expense"].completed_count == 1
    assert d["expense"].avg_hours == 12.0


async def test_summary_manager_scoped_to_own_department(db):
    from app.services.dashboard_service import DashboardService

    dept_a = await make_department(db, name="技术部")
    dept_b = await make_department(db, name="市场部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept_a.id)
    u2 = await make_user(db, email="u2@x.com", department_id=dept_b.id)
    await make_leave(db, u1, mgr, start_date=date(2026, 7, 6), end_date=date(2026, 7, 7), status="approved")
    await make_leave(db, u2, mgr, start_date=date(2026, 7, 6), end_date=date(2026, 7, 8), status="approved")
    e1 = await make_expense(db, u1, mgr, amount=Decimal("10.00"), status="approved")
    e1.created_at = datetime(2026, 7, 15, 10, 0, 0)
    e2 = await make_expense(db, u2, mgr, amount=Decimal("20.00"), status="approved")
    e2.created_at = datetime(2026, 7, 15, 10, 0, 0)
    await db.commit()

    viewer = await make_user(
        db, email="v@x.com", department_id=dept_a.id,
        roles=[await perms_role(db, ["dashboard:view"], "mgr-r")],
    )
    summary = await DashboardService(db).get_summary(date(2026, 7, 1), viewer)
    assert len(summary.leave_stats) == 1
    assert summary.leave_stats[0].department_name == "技术部"
    assert summary.leave_stats[0].request_count == 1
    assert len(summary.expense_stats) == 1
    assert summary.expense_stats[0].total_amount == Decimal("10.00")


async def test_summary_viewer_without_department_gets_empty(db):
    from app.services.dashboard_service import DashboardService

    dept = await make_department(db, name="技术部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept.id)
    await make_leave(db, u1, mgr, start_date=date(2026, 7, 6), end_date=date(2026, 7, 7), status="approved")

    viewer = await make_user(
        db, email="v@x.com",
        roles=[await perms_role(db, ["dashboard:view"], "mgr-r")],
    )
    summary = await DashboardService(db).get_summary(date(2026, 7, 1), viewer)
    assert summary.month == "2026-07"
    assert summary.leave_stats == []
    assert summary.expense_stats == []
    assert all(
        x.completed_count == 0 and x.avg_hours is None
        for x in summary.approval_durations
    )


async def test_summary_default_month_is_current(db, monkeypatch):
    from app.services.dashboard_service import DashboardService

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 15)

    monkeypatch.setattr("app.services.dashboard_service.date", FakeDate)
    admin = await make_user(
        db, email="a@x.com",
        roles=[await perms_role(db, ["dashboard:view", "dashboard:view_all"], "adm-r")],
    )
    summary = await DashboardService(db).get_summary(None, admin)
    assert summary.month == "2026-03"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_dashboard_service.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'app.services.dashboard_service'`

- [ ] **Step 3: Write schemas + service**

创建 `backend/app/schemas/dashboard.py`:

```python
import uuid
from decimal import Decimal

from pydantic import BaseModel


class LeaveStatItem(BaseModel):
    department_id: uuid.UUID
    department_name: str
    request_count: int
    total_days: float


class ExpenseStatItem(BaseModel):
    department_id: uuid.UUID
    department_name: str
    request_count: int
    total_amount: Decimal


class ApprovalDurationItem(BaseModel):
    category: str
    completed_count: int
    avg_hours: float | None


class DashboardSummaryResponse(BaseModel):
    month: str
    leave_stats: list[LeaveStatItem]
    expense_stats: list[ExpenseStatItem]
    approval_durations: list[ApprovalDurationItem]
```

创建 `backend/app/services/dashboard_service.py`:

```python
import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import (
    ApprovalDurationItem,
    DashboardSummaryResponse,
    ExpenseStatItem,
    LeaveStatItem,
)

CATEGORIES = ("leave", "expense")


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.dashboard = DashboardRepository(db)

    async def get_summary(
        self, month: date | None, user: User
    ) -> DashboardSummaryResponse:
        if month is None:
            month = date.today()
        month_start = month.replace(day=1)
        last_day = calendar.monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)
        month_str = f"{month_start.year:04d}-{month_start.month:02d}"

        perms = {p.code for role in user.roles for p in role.permissions}
        if "dashboard:view_all" not in perms and user.department_id is None:
            # 无部门 Manager:department_id=None 在仓储表示"不过滤",必须在此拦截
            return DashboardSummaryResponse(
                month=month_str,
                leave_stats=[],
                expense_stats=[],
                approval_durations=self._empty_durations(),
            )
        department_id = (
            None if "dashboard:view_all" in perms else user.department_id
        )

        leave_rows = await self.dashboard.leave_rows(
            month_start, month_end, department_id
        )
        expense_rows = await self.dashboard.expense_rows(
            month_start, month_end, department_id
        )
        duration_rows = await self.dashboard.duration_rows(
            month_start, month_end, department_id
        )
        return DashboardSummaryResponse(
            month=month_str,
            leave_stats=self._aggregate_leave(leave_rows, month_start, month_end),
            expense_stats=self._aggregate_expense(expense_rows),
            approval_durations=self._aggregate_durations(duration_rows),
        )

    @staticmethod
    def _aggregate_leave(rows, month_start, month_end) -> list[LeaveStatItem]:
        agg: dict = {}
        for dept_id, dept_name, start, end in rows:
            days = (min(end, month_end) - max(start, month_start)).days + 1
            entry = agg.setdefault(
                dept_id, {"name": dept_name, "count": 0, "days": 0}
            )
            entry["count"] += 1
            entry["days"] += days
        return [
            LeaveStatItem(
                department_id=dept_id,
                department_name=v["name"],
                request_count=v["count"],
                total_days=round(float(v["days"]), 1),
            )
            for dept_id, v in agg.items()
        ]

    @staticmethod
    def _aggregate_expense(rows) -> list[ExpenseStatItem]:
        agg: dict = {}
        for dept_id, dept_name, amount in rows:
            entry = agg.setdefault(
                dept_id, {"name": dept_name, "count": 0, "total": Decimal("0")}
            )
            entry["count"] += 1
            entry["total"] += amount
        return [
            ExpenseStatItem(
                department_id=dept_id,
                department_name=v["name"],
                request_count=v["count"],
                total_amount=v["total"],
            )
            for dept_id, v in agg.items()
        ]

    def _aggregate_durations(self, rows) -> list[ApprovalDurationItem]:
        buckets: dict[str, list[float]] = {c: [] for c in CATEGORIES}
        for category, created_at, finished_at in rows:
            hours = (finished_at - created_at).total_seconds() / 3600
            buckets[category].append(hours)
        return [
            ApprovalDurationItem(
                category=c,
                completed_count=len(buckets[c]),
                avg_hours=(
                    round(sum(buckets[c]) / len(buckets[c]), 1)
                    if buckets[c]
                    else None
                ),
            )
            for c in CATEGORIES
        ]

    @staticmethod
    def _empty_durations() -> list[ApprovalDurationItem]:
        return [
            ApprovalDurationItem(category=c, completed_count=0, avg_hours=None)
            for c in CATEGORIES
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_dashboard_service.py -v`
Expected: 5 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/dashboard.py backend/app/services/dashboard_service.py backend/tests/test_dashboard_service.py
git commit -m "feat(backend): DashboardService 聚合与部门作用域"
```

---

### Task 3: /dashboard API

**Files:**
- Create: `backend/app/api/v1/dashboard.py`
- Modify: `backend/app/main.py:3,17`(import 行 + include_router)
- Test: `backend/tests/test_dashboard_api.py`

**Interfaces:**
- Consumes: Task 2 的 `DashboardService.get_summary(month, user)` 与 schemas;`require_permission`(参照 expenses 路由)
- Produces: `GET /api/v1/dashboard?month=YYYY-MM`(month 缺省当前月;`dashboard:view` 权限)

- [ ] **Step 1: Write the failing tests**

创建 `backend/tests/test_dashboard_api.py`:

```python
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models.leave import LeaveStatusHistory
from app.models.permission import Permission
from tests.conftest import (
    login_token,
    make_department,
    make_expense,
    make_leave,
    make_permission,
    make_role,
    make_user,
)


async def dash_perms(db):
    existing = {p.code: p for p in (await db.execute(select(Permission))).scalars()}
    perms = {}
    for code in ["dashboard:view", "dashboard:view_all"]:
        perms[code] = existing.get(code) or await make_permission(
            db, code=code, name=code
        )
    return perms


async def make_viewer_client(db, client, email, codes, dept=None):
    perms = await dash_perms(db)
    role = await make_role(
        db, code=f"role-{email}", name=email,
        permissions=[perms[c] for c in codes],
    )
    user = await make_user(
        db, email=email, password="Passw0rd!", roles=[role],
        department_id=dept.id if dept else None,
    )
    token = await login_token(client, email, "Passw0rd!")
    return user, {"Authorization": f"Bearer {token}"}


async def test_dashboard_contract(db, client):
    dept = await make_department(db, name="技术部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept.id)
    await make_leave(db, u1, mgr, start_date=date(2026, 7, 6), end_date=date(2026, 7, 8), status="approved")
    l2 = await make_leave(db, u1, mgr, start_date=date(2026, 7, 10), end_date=date(2026, 7, 10), status="approved")
    l2.created_at = datetime(2026, 7, 10, 9, 0, 0)
    db.add(LeaveStatusHistory(
        request_id=l2.id, from_status="pending", to_status="approved",
        actor_id=mgr.id, created_at=datetime(2026, 7, 11, 9, 0, 0),
    ))
    e1 = await make_expense(db, u1, mgr, amount=Decimal("100.50"), status="approved")
    e1.created_at = datetime(2026, 7, 15, 10, 0, 0)
    await db.commit()

    _, headers = await make_viewer_client(
        db, client, "boss@x.com", ["dashboard:view", "dashboard:view_all"]
    )
    resp = await client.get("/api/v1/dashboard?month=2026-07", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["month"] == "2026-07"

    assert len(body["leave_stats"]) == 1
    ls = body["leave_stats"][0]
    assert ls["department_name"] == "技术部"
    assert ls["request_count"] == 2
    assert ls["total_days"] == 4.0  # 3 + 1
    assert "department_id" in ls

    assert len(body["expense_stats"]) == 1
    assert float(body["expense_stats"][0]["total_amount"]) == 100.5

    d = {x["category"]: x for x in body["approval_durations"]}
    assert d["leave"]["completed_count"] == 1
    assert d["leave"]["avg_hours"] == 24.0
    assert d["expense"]["completed_count"] == 0
    assert d["expense"]["avg_hours"] is None


async def test_dashboard_default_month(db, client):
    dept = await make_department(db, name="技术部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept.id)
    today = date.today()
    await make_leave(db, u1, mgr, start_date=today, end_date=today, status="approved")

    _, headers = await make_viewer_client(
        db, client, "boss@x.com", ["dashboard:view", "dashboard:view_all"]
    )
    resp = await client.get("/api/v1/dashboard", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["month"] == today.strftime("%Y-%m")
    assert body["leave_stats"][0]["request_count"] == 1


async def test_dashboard_invalid_month_422(db, client):
    _, headers = await make_viewer_client(
        db, client, "boss@x.com", ["dashboard:view", "dashboard:view_all"]
    )
    for bad in ("2026-13", "abc", "2026-1", "202607"):
        resp = await client.get(f"/api/v1/dashboard?month={bad}", headers=headers)
        assert resp.status_code == 422, bad


async def test_dashboard_manager_scoped(db, client):
    dept_a = await make_department(db, name="技术部")
    dept_b = await make_department(db, name="市场部")
    mgr = await make_user(db, email="m@x.com")
    u1 = await make_user(db, email="u1@x.com", department_id=dept_a.id)
    u2 = await make_user(db, email="u2@x.com", department_id=dept_b.id)
    await make_leave(db, u1, mgr, start_date=date(2026, 7, 6), end_date=date(2026, 7, 6), status="approved")
    await make_leave(db, u2, mgr, start_date=date(2026, 7, 6), end_date=date(2026, 7, 6), status="approved")

    _, headers = await make_viewer_client(
        db, client, "lead@x.com", ["dashboard:view"], dept=dept_a
    )
    resp = await client.get("/api/v1/dashboard?month=2026-07", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["leave_stats"]) == 1
    assert body["leave_stats"][0]["department_name"] == "技术部"


async def test_dashboard_forbidden_without_permission(db, client):
    await make_user(db, email="emp@x.com", password="Passw0rd!")
    token = await login_token(client, "emp@x.com", "Passw0rd!")
    resp = await client.get(
        "/api/v1/dashboard", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


async def test_dashboard_unauthenticated_401(client):
    assert (await client.get("/api/v1/dashboard")).status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_dashboard_api.py -v`
Expected: FAIL,404(路由不存在)

- [ ] **Step 3: Write the router + register**

创建 `backend/app/api/v1/dashboard.py`:

```python
import re
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.core.exceptions import ValidationError
from app.models.user import User
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("", response_model=DashboardSummaryResponse)
async def get_dashboard(
    month: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:view")),
):
    month_start = None
    if month is not None:
        if not _MONTH_RE.match(month):
            raise ValidationError("month 格式须为 YYYY-MM")
        month_start = date(int(month[:4]), int(month[5:7]), 1)
    return await DashboardService(db).get_summary(month_start, current_user)
```

修改 `backend/app/main.py`:

- 第 3 行 import 改为:`from app.api.v1 import auth, dashboard, departments, expenses, leaves, notifications, roles, users`
- 在 `api_v1.include_router(notifications.router)` 后加:`api_v1.include_router(dashboard.router)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_dashboard_api.py -v`
Expected: 6 个 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/dashboard.py backend/app/main.py backend/tests/test_dashboard_api.py
git commit -m "feat(backend): /dashboard 看板聚合接口"
```

---

### Task 4: seed 追加看板权限点

**Files:**
- Modify: `backend/scripts/seed.py`(PERMISSIONS + ROLE_PERMISSIONS)
- Modify: `backend/tests/conftest.py`(ALL_PERMISSIONS 追加 2 条)
- Modify: `backend/tests/test_seed.py`(期望集合更新 + 新增专项测试)

**Interfaces:**
- Consumes: Task 3 的权限点命名
- Produces: 新环境 `python -m scripts.seed` 后 admin 全量(含两个新点)、manager 含 `dashboard:view`(不含 view_all)、employee 不含

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
    "dashboard:view", "dashboard:view_all",
}
```

2) `test_seed_creates_permissions_roles_and_admin` 与 `test_seed_repairs_manager_permissions_on_rerun` 中 manager 期望集合改为:

```python
    {
        "department:list",
        "department:members",
        "leave:create",
        "leave:list",
        "leave:approve",
        "expense:create",
        "expense:list",
        "expense:approve",
        "dashboard:view",
    }
```

(两处分别是 `roles["manager"].permissions` 与 `role.permissions`,断言结构不变,只在集合里加 `"dashboard:view",`。)

3) 文件末尾追加看板专项测试:

```python
async def test_seed_assigns_dashboard_permissions(db):
    await seed(db)

    perms = {p.code for p in (await db.execute(select(Permission))).scalars()}
    expected = {"dashboard:view", "dashboard:view_all"}
    assert expected <= perms

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    admin_perms = {p.code for p in roles["admin"].permissions}
    manager_perms = {p.code for p in roles["manager"].permissions}
    employee_perms = {p.code for p in roles["employee"].permissions}
    assert expected <= admin_perms
    assert "dashboard:view" in manager_perms
    assert "dashboard:view_all" not in manager_perms
    assert employee_perms == {
        "leave:create",
        "leave:list",
        "expense:create",
        "expense:list",
    }
```

修改 `backend/tests/conftest.py` 的 `ALL_PERMISSIONS`,在 `("expense:list_all", "查看全部报销记录"),` 后追加:

```python
    ("dashboard:view", "查看数据看板"),
    ("dashboard:view_all", "查看全公司看板"),
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_seed.py -v`
Expected: FAIL(manager/admin 权限集合不符)

- [ ] **Step 3: Update seed.py**

修改 `backend/scripts/seed.py` 的 `PERMISSIONS`,在 `("expense:list_all", "查看全部报销记录"),` 后追加:

```python
    ("dashboard:view", "查看数据看板"),
    ("dashboard:view_all", "查看全公司看板"),
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
        "dashboard:view",
    ],
```

employee 列表不变。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_seed.py -v`
Expected: 全部 PASS(含幂等/修复既有测试)

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/seed.py backend/tests/conftest.py backend/tests/test_seed.py
git commit -m "feat(backend): seed 追加看板两个权限点与 manager 映射"
```

---

### Task 5: 全量验收 + spec 勾选

**Files:**
- Modify: `docs/superpowers/specs/2026-07-28-dashboard-design.md`(§10 六个 `- [ ]` → `- [x]`)

**Interfaces:**
- Consumes: Task 1-4 全部产出
- Produces: 可 PR 的完整分支

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && pytest`
Expected: 全部 PASS(既有 247 + 本分支新增,无回归)

- [ ] **Step 2: Tick spec acceptance boxes**

把 `docs/superpowers/specs/2026-07-28-dashboard-design.md` §10 的 6 个 `- [ ]` 全部改为 `- [x]`。

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-07-28-dashboard-design.md
git commit -m "test(backend): 看板模块全量验收通过,勾选 spec 验收标准"
```

---

## Self-Review 记录

- **Spec 覆盖**:§3 API 契约→Task 3;§4 口径→Task 1(行过滤)+Task 2(聚合/切分/平均);§5 分层→Task 1/2/3;§6 权限与 seed→Task 4;§7 错误语义→Task 3 测试;§8 测试策略→各任务测试;§9 部署(无)→无需任务;§10 验收→Task 5 勾选。无缺口。
- **占位符扫描**:无 TBD/TODO;所有代码块为完整可复制内容。
- **类型一致性**:`leave_rows/expense_rows/duration_rows` 签名 Task 1 定义、Task 2 消费一致(位置解包与 Row 列序一致);`get_summary(month: date | None, user)` Task 2 定义、Task 3 调用一致;`perms_role`/`dash_perms`/`make_viewer_client` helper 在各自测试文件内独立定义(测试文件自包含,与既有风格一致)。
- **已知取舍**:①仓储返回 `list[Row]` 而非聚合结果——spec §5 已修正为"SQL 过滤 + Python 聚合"(SQLite/Pg 日期算术不可移植);②`duration_rows` 假设每单至多一行终态 history(状态机保证),未用 max 子查询;③Row 用位置解包(`r[0]/r[1]`),与 select 列序绑定,列序在同文件内定义,风险可控;④`test_dashboard_default_month` 依赖真实时钟但自洽(数据 created_at 与期望 month 同取 `date.today()`)。
