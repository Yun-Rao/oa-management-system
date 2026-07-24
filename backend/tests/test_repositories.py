from app.core.security import hash_password
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from tests.conftest import make_role, make_user


async def test_get_by_email(db):
    await make_user(db, email="find@me.com")
    repo = UserRepository(db)
    found = await repo.get_by_email("find@me.com")
    assert found is not None
    assert await repo.get_by_email("nobody@x.com") is None


async def test_get_by_id(db):
    user = await make_user(db)
    assert (await UserRepository(db).get_by_id(user.id)).email == user.email


async def test_list_with_keyword_and_pagination(db):
    await make_user(db, email="zhangsan@x.com", name="张三")
    await make_user(db, email="lisi@x.com", name="李四")
    await make_user(db, email="wangwu@x.com", name="王五")
    repo = UserRepository(db)

    items, total = await repo.list(keyword="张三", offset=0, limit=20)
    assert total == 1 and items[0].name == "张三"

    items, total = await repo.list(keyword=None, offset=1, limit=2)
    assert total == 3 and len(items) == 2


async def test_create_and_save(db):
    repo = UserRepository(db)
    user = User(email="new@x.com", name="新人", hashed_password=hash_password("Passw0rd!"))
    await repo.create(user)
    assert (await repo.get_by_email("new@x.com")) is not None

    user.name = "改名"
    await repo.save(user)
    assert (await repo.get_by_email("new@x.com")).name == "改名"


async def test_role_repository(db):
    await make_role(db, code="admin", name="管理员")
    await make_role(db, code="employee", name="普通员工")
    repo = RoleRepository(db)

    all_roles = await repo.list_all()
    assert {r.code for r in all_roles} == {"admin", "employee"}

    roles = await repo.get_by_codes(["admin", "missing"])
    assert [r.code for r in roles] == ["admin"]
