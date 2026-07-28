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
