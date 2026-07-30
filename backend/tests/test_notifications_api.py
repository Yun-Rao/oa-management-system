import uuid
from datetime import datetime

from tests.conftest import login_token, make_notification, make_user


async def make_client(db, client, email="u1@x.com"):
    user = await make_user(db, email=email, password="Passw0rd!")
    token = await login_token(client, email, "Passw0rd!")
    return user, {"Authorization": f"Bearer {token}"}


async def test_list_empty(db, client):
    _, headers = await make_client(db, client)
    resp = await client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 20}


async def test_list_only_own(db, client):
    u1, headers = await make_client(db, client, "u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_notification(db, u1, title="我的")
    await make_notification(db, u2, title="别人的")

    resp = await client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "我的"


async def test_list_is_read_filter(db, client):
    u1, headers = await make_client(db, client)
    await make_notification(db, u1, title="未读")
    await make_notification(db, u1, title="已读", read_at=datetime(2026, 7, 1, 10, 0, 0))

    resp = await client.get("/api/v1/notifications?is_read=false", headers=headers)
    assert [i["title"] for i in resp.json()["items"]] == ["未读"]
    resp = await client.get("/api/v1/notifications?is_read=true", headers=headers)
    assert [i["title"] for i in resp.json()["items"]] == ["已读"]


async def test_list_pagination(db, client):
    u1, headers = await make_client(db, client)
    for i in range(3):
        await make_notification(db, u1, title=f"n{i}", created_at=datetime(2026, 7, 1, 10, i, 0))

    resp = await client.get("/api/v1/notifications?page=2&page_size=2", headers=headers)
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["page"] == 2
    assert body["page_size"] == 2


async def test_unread_count(db, client):
    u1, headers = await make_client(db, client)
    await make_notification(db, u1)
    await make_notification(db, u1)
    await make_notification(db, u1, read_at=datetime(2026, 7, 1, 10, 0, 0))

    resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"count": 2}


async def test_read_marks_and_idempotent(db, client):
    u1, headers = await make_client(db, client)
    n = await make_notification(db, u1)

    resp = await client.post(f"/api/v1/notifications/{n.id}/read", headers=headers)
    assert resp.status_code == 200
    first = resp.json()["read_at"]
    assert first is not None

    resp = await client.post(f"/api/v1/notifications/{n.id}/read", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["read_at"] == first


async def test_read_not_found_404(db, client):
    _, headers = await make_client(db, client)
    resp = await client.post(f"/api/v1/notifications/{uuid.uuid4()}/read", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_read_forbidden_403(db, client):
    u1 = await make_user(db, email="owner@x.com")
    n = await make_notification(db, u1)
    _, headers = await make_client(db, client, "other@x.com")

    resp = await client.post(f"/api/v1/notifications/{n.id}/read", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_read_all_then_zero(db, client):
    u1, headers = await make_client(db, client)
    await make_notification(db, u1)
    await make_notification(db, u1)

    resp = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"updated": 2}

    resp = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert resp.json() == {"updated": 0}


async def test_unauthenticated_401(client):
    assert (await client.get("/api/v1/notifications")).status_code == 401
    assert (await client.get("/api/v1/notifications/unread-count")).status_code == 401
    assert (await client.post("/api/v1/notifications/read-all")).status_code == 401
    assert (await client.post(f"/api/v1/notifications/{uuid.uuid4()}/read")).status_code == 401
