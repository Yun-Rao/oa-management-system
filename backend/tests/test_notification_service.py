from datetime import date, datetime

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from tests.conftest import make_leave, make_notification, make_user


async def test_notify_leave_submitted_content(db):
    from app.services.notification_service import NotificationService

    approver = await make_user(db, email="m@x.com")
    applicant = await make_user(
        db, email="e@x.com", name="张三", manager_id=approver.id
    )
    leave = await make_leave(
        db, applicant, approver, type="sick",
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
    )

    NotificationService(db).notify_leave_submitted(leave, applicant.name)
    await db.commit()

    from app.repositories.notification_repository import NotificationRepository
    items, total = await NotificationRepository(db).list_mine(approver.id, None, 0, 20)
    assert total == 1
    n = items[0]
    assert n.type == "leave_submitted"
    assert n.title == "新的待审批任务"
    assert n.content == "张三 提交了 2026-08-01 ~ 2026-08-02 的病假申请,待您审批"
    assert n.ref_type == "leave"
    assert n.ref_id == leave.id
    assert n.read_at is None


async def test_notify_leave_approved_content(db):
    from app.services.notification_service import NotificationService

    approver = await make_user(db, email="m@x.com")
    applicant = await make_user(db, email="e@x.com", manager_id=approver.id)
    leave = await make_leave(db, applicant, approver, type="annual")

    NotificationService(db).notify_leave_approved(leave)
    await db.commit()

    from app.repositories.notification_repository import NotificationRepository
    items, total = await NotificationRepository(db).list_mine(applicant.id, None, 0, 20)
    assert total == 1
    n = items[0]
    assert n.type == "leave_approved"
    assert n.title == "请假申请已通过"
    assert n.content == "您 2026-08-01 ~ 2026-08-02 的年假申请已通过"


async def test_notify_leave_rejected_content(db):
    from app.services.notification_service import NotificationService

    approver = await make_user(db, email="m@x.com")
    applicant = await make_user(db, email="e@x.com", manager_id=approver.id)
    leave = await make_leave(db, applicant, approver, type="personal")

    NotificationService(db).notify_leave_rejected(leave, "人手不足")
    await db.commit()

    from app.repositories.notification_repository import NotificationRepository
    items, total = await NotificationRepository(db).list_mine(applicant.id, None, 0, 20)
    assert total == 1
    n = items[0]
    assert n.type == "leave_rejected"
    assert n.title == "请假申请已驳回"
    assert n.content == "您 2026-08-01 ~ 2026-08-02 的事假申请已被驳回:人手不足"


async def test_mark_read_not_found(db):
    import uuid

    from app.services.notification_service import NotificationService

    u = await make_user(db, email="u1@x.com")
    with pytest.raises(NotFoundError):
        await NotificationService(db).mark_read(uuid.uuid4(), u)


async def test_mark_read_forbidden_when_not_owner(db):
    from app.services.notification_service import NotificationService

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    n = await make_notification(db, u1)

    with pytest.raises(ForbiddenError):
        await NotificationService(db).mark_read(n.id, u2)


async def test_mark_read_success_idempotent(db):
    from app.services.notification_service import NotificationService

    u = await make_user(db, email="u1@x.com")
    n = await make_notification(db, u)
    svc = NotificationService(db)

    n = await svc.mark_read(n.id, u)
    assert n.read_at is not None
    again = await svc.mark_read(n.id, u)
    assert again.read_at == n.read_at


async def test_mark_all_read_only_own(db):
    from app.services.notification_service import NotificationService

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_notification(db, u1)
    await make_notification(db, u1, read_at=datetime(2026, 7, 1, 10, 0, 0))
    await make_notification(db, u2)

    svc = NotificationService(db)
    assert await svc.mark_all_read(u1) == 1
    assert await svc.mark_all_read(u1) == 0
    assert await svc.unread_count(u2) == 1
