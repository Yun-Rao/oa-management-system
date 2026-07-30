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
