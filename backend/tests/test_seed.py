from sqlalchemy import select

from app.core.config import settings
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from app.services.auth_service import AuthService
from scripts.seed import seed

ALL_PERMISSION_CODES = {
    "user:create", "user:list", "user:update",
    "user:disable", "role:list", "role:assign",
    "department:create", "department:update", "department:delete",
    "department:list", "department:members",
}

DEPARTMENT_PERMISSION_CODES = {
    "department:create",
    "department:update",
    "department:delete",
    "department:list",
    "department:members",
}


async def test_seed_creates_permissions_roles_and_admin(db):
    await seed(db)

    perms = (await db.execute(select(Permission))).scalars().all()
    assert {p.code for p in perms} == ALL_PERMISSION_CODES

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    assert set(roles) == {"admin", "manager", "employee"}
    assert len(roles["admin"].permissions) == len(ALL_PERMISSION_CODES)
    assert {p.code for p in roles["manager"].permissions} == {
        "department:list",
        "department:members",
    }

    result = await db.execute(select(User).where(User.email == settings.SEED_ADMIN_EMAIL))
    admin = result.scalar_one()
    assert [r.code for r in admin.roles] == ["admin"]

    token = await AuthService(db).login(
        settings.SEED_ADMIN_EMAIL, settings.SEED_ADMIN_PASSWORD
    )
    assert token.access_token


async def test_seed_is_idempotent(db):
    await seed(db)
    await seed(db)
    assert len((await db.execute(select(User))).scalars().all()) == 1
    assert len((await db.execute(select(Role))).scalars().all()) == 3


async def test_seed_repairs_stale_admin_permissions(db):
    stale = Role(code="admin", name="管理员", permissions=[])
    db.add(stale)
    await db.commit()

    await seed(db)

    result = await db.execute(select(Role).where(Role.code == "admin"))
    admin = result.scalar_one()
    assert len(admin.permissions) == len(ALL_PERMISSION_CODES)
    assert len((await db.execute(select(Permission))).scalars().all()) == len(
        ALL_PERMISSION_CODES
    )


async def test_seed_assigns_department_permissions(db):
    await seed(db)

    perms = {p.code for p in (await db.execute(select(Permission))).scalars()}
    assert DEPARTMENT_PERMISSION_CODES <= perms

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    admin_perms = {p.code for p in roles["admin"].permissions}
    manager_perms = {p.code for p in roles["manager"].permissions}
    assert DEPARTMENT_PERMISSION_CODES <= admin_perms
    assert manager_perms == {"department:list", "department:members"}
    assert roles["employee"].permissions == []


async def test_seed_repairs_manager_permissions_on_rerun(db):
    await seed(db)
    role = (
        await db.execute(select(Role).where(Role.code == "manager"))
    ).scalar_one()
    role.permissions = []
    await db.commit()

    await seed(db)
    role = (
        await db.execute(select(Role).where(Role.code == "manager"))
    ).scalar_one()
    assert {p.code for p in role.permissions} == {
        "department:list",
        "department:members",
    }
