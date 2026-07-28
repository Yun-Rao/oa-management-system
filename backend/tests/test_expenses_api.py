import uuid

import pytest_asyncio

from app.core.config import settings
from tests.conftest import (
    login_token,
    make_expense,
    make_permission,
    make_role,
    make_user,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.4 fake-pdf-bytes"


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


async def make_admin_client(db, client, email="admin@x.com"):
    perms = await expense_perms(db)
    role = await make_role(
        db, code=f"adm-{email}", name="Admin", permissions=list(perms.values())
    )
    admin = await make_user(db, email=email, password="Passw0rd!", roles=[role])
    token = await login_token(client, email, "Passw0rd!")
    return admin, {"Authorization": f"Bearer {token}"}


def form(**over):
    data = {"type": "travel", "amount": "1999.50", "reason": "出差打车"}
    data.update(over)
    files = [("files", ("a.png", PNG, "image/png"))]
    return data, files


async def submit(client, headers, **over):
    data, files = form(**over)
    return await client.post(
        "/api/v1/expenses", data=data, files=files, headers=headers
    )


async def test_create_201_and_file_on_disk(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    resp = await submit(client, emp_h)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending_l1"
    assert body["approver_id"] == str(mgr.id)
    assert float(body["amount"]) == 1999.5

    detail = await client.get(f"/api/v1/expenses/{body['id']}", headers=emp_h)
    assert detail.status_code == 200
    atts = detail.json()["attachments"]
    assert len(atts) == 1
    assert atts[0]["filename"] == "a.png"
    assert "stored_path" not in atts[0]
    assert detail.json()["history"][0]["to_status"] == "pending_l1"


async def test_create_validation_errors(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    # 类型非法
    resp = await submit(client, emp_h, type="luxury")
    assert resp.status_code == 422
    # 金额 ≤ 0
    resp = await submit(client, emp_h, amount="0")
    assert resp.status_code == 422
    # 扩展名非法
    data, _ = form()
    resp = await client.post(
        "/api/v1/expenses",
        data=data,
        files=[("files", ("a.gif", b"GIF89a fake", "image/gif"))],
        headers=emp_h,
    )
    assert resp.status_code == 422
    # 魔数不符( .png 文件装 JPEG 字节)
    resp = await client.post(
        "/api/v1/expenses",
        data=data,
        files=[("files", ("a.png", b"\xff\xd8\xff\xe0 jpeg", "image/png"))],
        headers=emp_h,
    )
    assert resp.status_code == 422
    # 附件超 5 个
    resp = await client.post(
        "/api/v1/expenses",
        data=data,
        files=[("files", (f"{i}.png", PNG, "image/png")) for i in range(6)],
        headers=emp_h,
    )
    assert resp.status_code == 422


async def test_unauthenticated_401(client):
    assert (await client.post("/api/v1/expenses")).status_code == 401
    assert (await client.get("/api/v1/expenses/mine")).status_code == 401
    assert (await client.get("/api/v1/expenses/todo")).status_code == 401
    assert (await client.get(f"/api/v1/expenses/{uuid.uuid4()}")).status_code == 401


async def test_employee_without_create_perm_403(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    perms = await expense_perms(db)
    role = await make_role(
        db, code="noperm", name="无权限", permissions=[perms["expense:list"]]
    )
    await make_user(
        db, email="np@x.com", password="Passw0rd!", roles=[role],
        manager_id=mgr.id,
    )
    token = await login_token(client, "np@x.com", "Passw0rd!")
    resp = await submit(client, {"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


async def test_todo_merged_view(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    admin, admin_h = await make_admin_client(db, client)

    small = await submit(client, emp_h, amount="100")
    assert small.status_code == 201
    big = await submit(client, emp_h, amount="3000")
    assert big.status_code == 201
    # 大额 L1 通过 → pending_l2
    resp = await client.post(
        f"/api/v1/expenses/{big.json()['id']}/approve", headers=mgr_h
    )
    assert resp.status_code == 200

    # 主管 todo:自己的 pending_l1(1 笔)+ 权限池 pending_l2(0,无 l2 权限)
    resp = await client.get("/api/v1/expenses/todo", headers=mgr_h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "pending_l1"

    # Admin todo:pending_l2 1 笔(admin 无 expense:approve,看不到 pending_l1)
    resp = await client.get("/api/v1/expenses/todo", headers=admin_h)
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "pending_l2"


async def test_mine_and_list_all(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    admin, admin_h = await make_admin_client(db, client)
    await submit(client, emp_h, amount="10")
    await submit(client, emp_h, amount="20", type="office")

    resp = await client.get("/api/v1/expenses/mine?type=office", headers=emp_h)
    assert resp.json()["total"] == 1
    resp = await client.get("/api/v1/expenses/mine", headers=emp_h)
    assert resp.json()["total"] == 2

    resp = await client.get("/api/v1/expenses", headers=admin_h)
    assert resp.json()["total"] == 2
    # 主管无 list_all
    mgr_h2 = (await make_manager_client(db, client, "m2@x.com"))[1]
    resp = await client.get("/api/v1/expenses", headers=mgr_h2)
    assert resp.status_code == 403


async def test_download_attachment_auth(db, client, upload_dir):
    mgr, _ = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)
    created = await submit(client, emp_h)
    eid = created.json()["id"]
    detail = await client.get(f"/api/v1/expenses/{eid}", headers=emp_h)
    att_id = detail.json()["attachments"][0]["id"]

    resp = await client.get(
        f"/api/v1/expenses/{eid}/attachments/{att_id}", headers=emp_h
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"\x89PNG")

    # 陌生人 403(先建一个只有 create+list 的另一员工)
    _, stranger_h = await make_employee_client(db, client, mgr, "s@x.com", "李四")
    resp = await client.get(
        f"/api/v1/expenses/{eid}/attachments/{att_id}", headers=stranger_h
    )
    assert resp.status_code == 403

    # 附件不属于该单 → 404
    created2 = await submit(client, emp_h)
    resp = await client.get(
        f"/api/v1/expenses/{created2.json()['id']}/attachments/{att_id}",
        headers=emp_h,
    )
    assert resp.status_code == 404


async def test_approve_reject_cancel_via_api(db, client, upload_dir):
    mgr, mgr_h = await make_manager_client(db, client)
    _, emp_h = await make_employee_client(db, client, mgr)

    # approve 直达(≤2000)
    small = await submit(client, emp_h, amount="1500")
    resp = await client.post(
        f"/api/v1/expenses/{small.json()['id']}/approve", headers=mgr_h
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    # 驳回缺原因 422
    big = await submit(client, emp_h, amount="5000")
    resp = await client.post(
        f"/api/v1/expenses/{big.json()['id']}/reject",
        json={"reason": " "},
        headers=mgr_h,
    )
    assert resp.status_code == 422
    resp = await client.post(
        f"/api/v1/expenses/{big.json()['id']}/reject",
        json={"reason": "超标"},
        headers=mgr_h,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    # 已终态再操作 409
    resp = await client.post(
        f"/api/v1/expenses/{big.json()['id']}/approve", headers=mgr_h
    )
    assert resp.status_code == 409

    # 撤回
    e3 = await submit(client, emp_h, amount="50")
    resp = await client.post(
        f"/api/v1/expenses/{e3.json()['id']}/cancel", headers=emp_h
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
