import pytest

from tests.conftest import (
    login_token,
    make_department,
    make_permission,
    make_role,
    make_user,
)


async def test_create_department(admin_client):
    resp = await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "技术部"
    assert body["parent_id"] is None


async def test_create_department_requires_auth(client):
    resp = await client.post("/api/v1/departments", json={"name": "技术部"})
    assert resp.status_code == 401


async def test_create_department_requires_permission(employee_client):
    resp = await employee_client.post("/api/v1/departments", json={"name": "技术部"})
    assert resp.status_code == 403


async def test_create_department_duplicate_409(admin_client):
    await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    resp = await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    assert resp.status_code == 409


async def test_get_tree(admin_client):
    root = (
        await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    ).json()
    await admin_client.post(
        "/api/v1/departments", json={"name": "后端组", "parent_id": root["id"]}
    )
    resp = await admin_client.get("/api/v1/departments")
    assert resp.status_code == 200
    tree = resp.json()
    assert len(tree) == 1
    assert tree[0]["name"] == "技术部"
    assert tree[0]["children"][0]["name"] == "后端组"
    assert tree[0]["children"][0]["member_count"] == 0


async def test_update_department_move_rejects_cycle(admin_client):
    root = (
        await admin_client.post("/api/v1/departments", json={"name": "技术部"})
    ).json()
    child = (
        await admin_client.post(
            "/api/v1/departments", json={"name": "后端组", "parent_id": root["id"]}
        )
    ).json()
    resp = await admin_client.patch(
        f"/api/v1/departments/{root['id']}", json={"parent_id": child["id"]}
    )
    assert resp.status_code == 409


async def test_delete_department(admin_client):
    dept = (await admin_client.post("/api/v1/departments", json={"name": "技术部"})).json()
    resp = await admin_client.delete(f"/api/v1/departments/{dept['id']}")
    assert resp.status_code == 204
    resp = await admin_client.get("/api/v1/departments")
    assert resp.json() == []


async def test_delete_department_with_members_409(admin_client, db):
    dept = await make_department(db, name="技术部")
    await make_user(db, email="a@x.com", department_id=dept.id)
    resp = await admin_client.delete(f"/api/v1/departments/{dept.id}")
    assert resp.status_code == 409


@pytest.mark.parametrize(
    "method,url",
    [
        ("POST", "/api/v1/departments"),
        ("GET", "/api/v1/departments"),
    ],
)
async def test_department_endpoints_reject_anonymous(client, method, url):
    resp = await client.request(method, url)
    assert resp.status_code == 401


async def test_members_manager_scope(client, db):
    dept = await make_department(db, name="技术部")
    other = await make_department(db, name="市场部")
    await make_user(db, email="a@x.com", department_id=dept.id)

    p1 = await make_permission(db, code="department:list", name="查看部门树")
    p2 = await make_permission(db, code="department:members", name="查看部门人员")
    role = await make_role(db, code="manager", name="部门主管", permissions=[p1, p2])
    await make_user(
        db, email="mgr@x.com", password="Passw0rd!", roles=[role], department_id=dept.id
    )
    token = await login_token(client, "mgr@x.com", "Passw0rd!")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/departments/{dept.id}/members", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2  # mgr 自己 + a@x.com

    resp = await client.get(f"/api/v1/departments/{other.id}/members", headers=headers)
    assert resp.status_code == 403


async def test_members_admin_can_view_any(admin_client, db):
    dept = await make_department(db, name="技术部")
    await make_user(db, email="a@x.com", department_id=dept.id)
    resp = await admin_client.get(f"/api/v1/departments/{dept.id}/members")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
