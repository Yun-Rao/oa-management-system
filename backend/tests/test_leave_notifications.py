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
