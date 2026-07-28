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
    "leave:create", "leave:list", "leave:approve", "leave:list_all",
    "expense:create", "expense:list", "expense:approve",
    "expense:approve_l2", "expense:list_all",
    "dashboard:view", "dashboard:view_all",
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
        "leave:create",
        "leave:list",
        "leave:approve",
        "expense:create",
        "expense:list",
        "expense:approve",
        "dashboard:view",
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
    assert {"department:list", "department:members"} <= manager_perms
    assert {p.code for p in roles["employee"].permissions} == {
        "leave:create",
        "leave:list",
        "expense:create",
        "expense:list",
    }


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
        "leave:create",
        "leave:list",
        "leave:approve",
        "expense:create",
        "expense:list",
        "expense:approve",
        "dashboard:view",
    }


async def test_seed_assigns_leave_permissions(db):
    await seed(db)

    perms = {p.code for p in (await db.execute(select(Permission))).scalars()}
    expected = {"leave:create", "leave:list", "leave:approve", "leave:list_all"}
    assert expected <= perms

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    admin_perms = {p.code for p in roles["admin"].permissions}
    manager_perms = {p.code for p in roles["manager"].permissions}
    employee_perms = {p.code for p in roles["employee"].permissions}
    assert expected <= admin_perms
    assert {"leave:create", "leave:list", "leave:approve"} <= manager_perms
    assert "leave:list_all" not in manager_perms
    assert employee_perms == {
        "leave:create",
        "leave:list",
        "expense:create",
        "expense:list",
    }


async def test_seed_assigns_expense_permissions(db):
    await seed(db)

    perms = {p.code for p in (await db.execute(select(Permission))).scalars()}
    expected = {
        "expense:create",
        "expense:list",
        "expense:approve",
        "expense:approve_l2",
        "expense:list_all",
    }
    assert expected <= perms

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    admin_perms = {p.code for p in roles["admin"].permissions}
    manager_perms = {p.code for p in roles["manager"].permissions}
    employee_perms = {p.code for p in roles["employee"].permissions}
    assert expected <= admin_perms
    assert {"expense:create", "expense:list", "expense:approve"} <= manager_perms
    assert "expense:approve_l2" not in manager_perms
    assert "expense:list_all" not in manager_perms
    assert employee_perms == {
        "leave:create",
        "leave:list",
        "expense:create",
        "expense:list",
    }


async def test_seed_assigns_dashboard_permissions(db):
    await seed(db)

    perms = {p.code for p in (await db.execute(select(Permission))).scalars()}
    expected = {"dashboard:view", "dashboard:view_all"}
    assert expected <= perms

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    admin_perms = {p.code for p in roles["admin"].permissions}
    manager_perms = {p.code for p in roles["manager"].permissions}
    employee_perms = {p.code for p in roles["employee"].permissions}
    assert expected <= admin_perms
    assert "dashboard:view" in manager_perms
    assert "dashboard:view_all" not in manager_perms
    assert employee_perms == {
        "leave:create",
        "leave:list",
        "expense:create",
        "expense:list",
    }
