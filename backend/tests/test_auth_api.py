from tests.conftest import login_token, make_permission, make_role, make_user


async def test_login_returns_token(client, db):
    await make_user(db, email="u@x.com", password="Secret123")
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "u@x.com", "password": "Secret123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] and body["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(client, db):
    await make_user(db, email="u@x.com", password="Secret123")
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "u@x.com", "password": "bad"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_requires_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_me_rejects_invalid_token(client):
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer garbage-token"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_me_returns_user_with_permissions(client, db):
    perm = await make_permission(db)
    role = await make_role(db, permissions=[perm])
    await make_user(db, email="u@x.com", password="Secret123", roles=[role])
    token = await login_token(client, "u@x.com", "Secret123")
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "u@x.com"
    assert body["roles"] == [{"code": "admin", "name": "管理员"}]
    assert body["permissions"] == ["user:create"]


async def test_me_rejects_disabled_user(client, db):
    user = await make_user(db, email="u@x.com", password="Secret123")
    token = await login_token(client, "u@x.com", "Secret123")
    user.is_active = False
    await db.commit()
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


async def test_change_password_flow(client, db):
    await make_user(db, email="u@x.com", password="Old12345")
    token = await login_token(client, "u@x.com", "Old12345")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "Old12345", "new_password": "New12345"},
        headers=headers,
    )
    assert resp.status_code == 204

    resp = await client.post(
        "/api/v1/auth/login", json={"email": "u@x.com", "password": "Old12345"}
    )
    assert resp.status_code == 401
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "u@x.com", "password": "New12345"}
    )
    assert resp.status_code == 200


async def test_change_password_wrong_old(client, db):
    await make_user(db, email="u@x.com", password="Old12345")
    token = await login_token(client, "u@x.com", "Old12345")
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "bad", "new_password": "New12345"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
