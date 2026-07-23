from sqlalchemy import select

from app.core.config import settings
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from app.services.auth_service import AuthService
from scripts.seed import seed


async def test_seed_creates_permissions_roles_and_admin(db):
    await seed(db)

    perms = (await db.execute(select(Permission))).scalars().all()
    assert {p.code for p in perms} == {
        "user:create", "user:list", "user:update",
        "user:disable", "role:list", "role:assign",
    }

    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    assert set(roles) == {"admin", "manager", "employee"}
    assert len(roles["admin"].permissions) == 6
    assert roles["manager"].permissions == []

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
