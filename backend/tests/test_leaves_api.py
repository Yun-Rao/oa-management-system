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


async def test_approve_leave_twice_409(client, db):
    manager, mgr_headers = await make_manager_client(db, client)
    _, headers = await make_employee_client(db, client, manager)
    leave = (
        await client.post("/api/v1/leaves", json=LEAVE_JSON, headers=headers)
    ).json()
    resp = await client.post(f"/api/v1/leaves/{leave['id']}/approve", headers=mgr_headers)
    assert resp.status_code == 200
    resp = await client.post(f"/api/v1/leaves/{leave['id']}/approve", headers=mgr_headers)
    assert resp.status_code == 409
