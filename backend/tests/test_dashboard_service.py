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
