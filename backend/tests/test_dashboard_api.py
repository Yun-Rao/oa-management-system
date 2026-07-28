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
