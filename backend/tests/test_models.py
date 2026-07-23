from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.user import User
from tests.conftest import make_permission, make_role, make_user


async def test_user_role_permission_relationships(db, client):
    perm = await make_permission(db)
    role = await make_role(db, permissions=[perm])
    await make_user(db, roles=[role])

    result = await db.execute(
        select(User).options(selectinload(User.roles))
    )
    user = result.scalar_one()
    assert user.roles[0].code == "admin"
    assert user.roles[0].permissions[0].code == "user:create"


async def test_user_defaults_active(db):
    user = await make_user(db)
    assert user.is_active is True
    assert user.id is not None
