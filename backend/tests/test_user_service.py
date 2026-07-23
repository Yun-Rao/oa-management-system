import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService
from tests.conftest import make_role, make_user


async def test_create_user(db):
    service = UserService(db)
    user = await service.create_user(
        UserCreate(email="new@x.com", name="新人", password="Passw0rd!")
    )
    assert user.id is not None
    assert user.hashed_password != "Passw0rd!"
    assert user.roles == []


async def test_create_user_duplicate_email(db):
    await make_user(db, email="dup@x.com")
    with pytest.raises(ConflictError):
        await UserService(db).create_user(
            UserCreate(email="dup@x.com", name="x", password="Passw0rd!")
        )


async def test_list_users(db):
    await make_user(db, email="a@x.com", name="甲")
    await make_user(db, email="b@x.com", name="乙")
    items, total = await UserService(db).list_users(keyword=None, page=1, page_size=20)
    assert total == 2 and len(items) == 2


async def test_update_user(db):
    user = await make_user(db, email="u@x.com", name="旧名")
    updated = await UserService(db).update_user(user.id, UserUpdate(name="新名"))
    assert updated.name == "新名"


async def test_update_user_email_conflict(db):
    await make_user(db, email="taken@x.com")
    user = await make_user(db, email="u@x.com")
    with pytest.raises(ConflictError):
        await UserService(db).update_user(user.id, UserUpdate(email="taken@x.com"))


async def test_update_missing_user(db):
    import uuid

    with pytest.raises(NotFoundError):
        await UserService(db).update_user(uuid.uuid4(), UserUpdate(name="x"))


async def test_set_status(db):
    user = await make_user(db)
    updated = await UserService(db).set_status(user.id, False)
    assert updated.is_active is False


async def test_assign_roles(db):
    role = await make_role(db, code="manager", name="部门主管")
    user = await make_user(db)
    operator = await make_user(db, email="op@x.com")
    updated = await UserService(db).assign_roles(user.id, ["manager"], operator)
    assert [r.code for r in updated.roles] == ["manager"]


async def test_assign_roles_unknown_code(db):
    user = await make_user(db)
    operator = await make_user(db, email="op@x.com")
    with pytest.raises(NotFoundError):
        await UserService(db).assign_roles(user.id, ["ghost"], operator)


async def test_admin_cannot_remove_own_admin_role(db):
    admin_role = await make_role(db, code="admin", name="管理员")
    operator = await make_user(db, email="op@x.com", roles=[admin_role])
    with pytest.raises(ConflictError):
        await UserService(db).assign_roles(operator.id, [], operator)


async def test_admin_can_update_self_keeping_admin(db):
    admin_role = await make_role(db, code="admin", name="管理员")
    employee_role = await make_role(db, code="employee", name="普通员工")
    operator = await make_user(db, email="op@x.com", roles=[admin_role])
    updated = await UserService(db).assign_roles(
        operator.id, ["admin", "employee"], operator
    )
    assert {r.code for r in updated.roles} == {"admin", "employee"}
