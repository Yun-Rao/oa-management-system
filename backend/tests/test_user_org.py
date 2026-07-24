from tests.conftest import make_department, make_user


async def test_set_org_assigns_department_and_manager(admin_client, db):
    dept = await make_department(db, name="技术部")
    manager = await make_user(db, email="m@x.com", department_id=dept.id)
    user = await make_user(db, email="u@x.com")

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org",
        json={"department_id": str(dept.id), "manager_id": str(manager.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["department"]["id"] == str(dept.id)
    assert body["manager"]["id"] == str(manager.id)


async def test_set_org_manager_must_be_same_department(admin_client, db):
    dept = await make_department(db, name="技术部")
    other = await make_department(db, name="市场部")
    manager = await make_user(db, email="m@x.com", department_id=other.id)
    user = await make_user(db, email="u@x.com")

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org",
        json={"department_id": str(dept.id), "manager_id": str(manager.id)},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_set_org_manager_without_department_422(admin_client, db):
    manager = await make_user(db, email="m@x.com")
    user = await make_user(db, email="u@x.com")

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org", json={"manager_id": str(manager.id)}
    )
    assert resp.status_code == 422


async def test_set_org_manager_cannot_be_self(admin_client, db):
    dept = await make_department(db, name="技术部")
    user = await make_user(db, email="u@x.com", department_id=dept.id)

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org",
        json={"manager_id": str(user.id)},
    )
    assert resp.status_code == 422


async def test_set_org_clear_manager(admin_client, db):
    dept = await make_department(db, name="技术部")
    manager = await make_user(db, email="m@x.com", department_id=dept.id)
    user = await make_user(
        db, email="u@x.com", department_id=dept.id, manager_id=manager.id
    )

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org", json={"manager_id": None}
    )
    assert resp.status_code == 200
    assert resp.json()["manager"] is None
    assert resp.json()["department"]["id"] == str(dept.id)


async def test_set_org_move_department_without_manager_change_422(admin_client, db):
    dept_a = await make_department(db, name="技术部")
    dept_b = await make_department(db, name="市场部")
    manager = await make_user(db, email="m@x.com", department_id=dept_a.id)
    user = await make_user(
        db, email="u@x.com", department_id=dept_a.id, manager_id=manager.id
    )

    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org", json={"department_id": str(dept_b.id)}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_set_org_unknown_department_404(admin_client, db):
    import uuid

    user = await make_user(db, email="u@x.com")
    resp = await admin_client.patch(
        f"/api/v1/users/{user.id}/org", json={"department_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404


async def test_set_org_requires_permission(employee_client, db):
    user = await make_user(db, email="u2@x.com")
    resp = await employee_client.patch(f"/api/v1/users/{user.id}/org", json={})
    assert resp.status_code == 403
