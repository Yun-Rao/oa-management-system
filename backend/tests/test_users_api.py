import uuid

import pytest
from sqlalchemy import select

from app.models.user import User
from tests.conftest import ALL_PERMISSIONS, login_token, make_role, make_user


async def test_create_user_requires_auth(client):
    resp = await client.post(
        "/api/v1/users",
        json={"email": "a@x.com", "name": "甲", "password": "Passw0rd!"},
    )
    assert resp.status_code == 401


async def test_create_user_forbidden_for_employee(employee_client):
    resp = await employee_client.post(
        "/api/v1/users",
        json={"email": "a@x.com", "name": "甲", "password": "Passw0rd!"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_create_user(admin_client, db):
    resp = await admin_client.post(
        "/api/v1/users",
        json={"email": "a@x.com", "name": "甲", "password": "Passw0rd!"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "a@x.com" and body["is_active"] is True
    assert "password" not in body and "hashed_password" not in body


async def test_create_user_duplicate_email_409(admin_client, db):
    await make_user(db, email="dup@x.com")
    resp = await admin_client.post(
        "/api/v1/users",
        json={"email": "dup@x.com", "name": "甲", "password": "Passw0rd!"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_list_users_pagination(admin_client, db):
    await make_user(db, email="a@x.com", name="甲")
    await make_user(db, email="b@x.com", name="乙")
    resp = await admin_client.get("/api/v1/users?page=1&page_size=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3  # 含 fixture 创建的 admin
    assert len(body["items"]) == 1

    resp = await admin_client.get("/api/v1/users?keyword=甲")
    assert resp.json()["total"] == 1


async def test_update_user(admin_client, db):
    user = await make_user(db, email="a@x.com", name="旧")
    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}", json={"name": "新"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "新"


async def test_update_missing_user_404(admin_client):
    resp = await admin_client.patch(
        f"/api/v1/users/{uuid.uuid4()}", json={"name": "新"}
    )
    assert resp.status_code == 404


async def test_disable_user_blocks_access(admin_client, db):
    await make_user(db, email="a@x.com", password="Passw0rd!")
    token = await login_token(admin_client, "a@x.com", "Passw0rd!")
    result = await db.execute(select(User).where(User.email == "a@x.com"))
    target = result.scalar_one()

    resp = await admin_client.patch(
        f"/api/v1/users/{target.id}/status", json={"is_active": False}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # admin_client 的 headers 已带 admin token,这里显式传目标用户的 token 覆盖
    resp = await admin_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


async def test_assign_roles(admin_client, db):
    await make_role(db, code="manager", name="部门主管")
    user = await make_user(db, email="a@x.com")
    resp = await admin_client.put(
        f"/api/v1/users/{user.id}/roles", json={"role_codes": ["manager"]}
    )
    assert resp.status_code == 200
    assert resp.json()["roles"] == [{"code": "manager", "name": "部门主管"}]


async def test_assign_unknown_role_404(admin_client, db):
    user = await make_user(db, email="a@x.com")
    resp = await admin_client.put(
        f"/api/v1/users/{user.id}/roles", json={"role_codes": ["ghost"]}
    )
    assert resp.status_code == 404


async def test_admin_self_demotion_409(admin_client, db):
    result = await db.execute(select(User).where(User.email == "admin@x.com"))
    admin_user = result.scalar_one()
    resp = await admin_client.put(
        f"/api/v1/users/{admin_user.id}/roles", json={"role_codes": []}
    )
    assert resp.status_code == 409


async def test_list_roles(admin_client, db):
    await make_role(db, code="manager", name="部门主管")
    resp = await admin_client.get("/api/v1/roles")
    assert resp.status_code == 200
    codes = {r["code"] for r in resp.json()}
    assert {"admin", "manager"} <= codes
    admin_body = next(r for r in resp.json() if r["code"] == "admin")
    assert len(admin_body["permissions"]) == len(ALL_PERMISSIONS)


async def test_list_roles_forbidden_for_employee(employee_client):
    resp = await employee_client.get("/api/v1/roles")
    assert resp.status_code == 403


PROTECTED_ENDPOINTS = [
    (
        "post",
        "/api/v1/users",
        {"email": "a@x.com", "name": "甲", "password": "Passw0rd!"},
    ),
    ("get", "/api/v1/users", None),
    ("patch", "/api/v1/users/{id}", {"name": "新"}),
    ("patch", "/api/v1/users/{id}/status", {"is_active": False}),
    ("put", "/api/v1/users/{id}/roles", {"role_codes": []}),
    ("get", "/api/v1/roles", None),
]


@pytest.mark.parametrize(
    "method,url,payload",
    PROTECTED_ENDPOINTS,
    ids=[f"{m.upper()} {u}" for m, u, _ in PROTECTED_ENDPOINTS],
)
async def test_protected_endpoints_reject_anonymous(client, method, url, payload):
    kwargs = {"json": payload} if payload is not None else {}
    resp = await getattr(client, method)(url.format(id=uuid.uuid4()), **kwargs)
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "method,url,payload",
    PROTECTED_ENDPOINTS,
    ids=[f"{m.upper()} {u}" for m, u, _ in PROTECTED_ENDPOINTS],
)
async def test_protected_endpoints_forbid_employee(
    employee_client, method, url, payload
):
    kwargs = {"json": payload} if payload is not None else {}
    resp = await getattr(employee_client, method)(
        url.format(id=uuid.uuid4()), **kwargs
    )
    assert resp.status_code == 403


async def test_list_users_page_below_one_422(admin_client):
    resp = await admin_client.get("/api/v1/users?page=0")
    assert resp.status_code == 422


async def test_list_users_page_size_above_max_422(admin_client):
    resp = await admin_client.get("/api/v1/users?page_size=101")
    assert resp.status_code == 422
