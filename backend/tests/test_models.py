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


async def test_department_create_with_parent(db):
    from app.models.department import Department

    parent = Department(name="技术部")
    db.add(parent)
    await db.commit()
    child = Department(name="后端组", parent_id=parent.id)
    db.add(child)
    await db.commit()
    await db.refresh(child)
    assert child.parent_id == parent.id


async def test_user_org_fields_default_none(db):
    user = User(
        email="org@x.com",
        name="Org",
        hashed_password="x",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    assert user.department_id is None
    assert user.manager_id is None
