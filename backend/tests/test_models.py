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


async def test_leave_request_create(db):
    from datetime import date

    from app.models.leave import LeaveRequest

    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    leave = LeaveRequest(
        applicant_id=applicant.id,
        approver_id=approver.id,
        type="annual",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
        reason="家庭旅行",
    )
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    assert leave.status == "pending"
    assert leave.applicant.id == applicant.id
    assert leave.approver.id == approver.id


async def test_leave_status_history_append(db):
    from datetime import date

    from app.models.leave import LeaveRequest, LeaveStatusHistory

    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    leave = LeaveRequest(
        applicant_id=applicant.id,
        approver_id=approver.id,
        type="sick",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
        reason="感冒",
    )
    db.add(leave)
    await db.commit()
    entry = LeaveStatusHistory(
        request_id=leave.id,
        from_status=None,
        to_status="pending",
        actor_id=applicant.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    assert entry.from_status is None
    assert entry.to_status == "pending"
    assert entry.comment is None


async def test_leave_history_backref(db):
    from datetime import date

    from app.models.leave import LeaveRequest, LeaveStatusHistory

    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    leave = LeaveRequest(
        applicant_id=applicant.id,
        approver_id=approver.id,
        type="personal",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
        reason="私事",
    )
    db.add(leave)
    await db.commit()
    db.add(
        LeaveStatusHistory(
            request_id=leave.id,
            from_status=None,
            to_status="pending",
            actor_id=applicant.id,
        )
    )
    await db.commit()
    await db.refresh(leave)
    assert len(leave.history) == 1
    assert leave.history[0].to_status == "pending"
