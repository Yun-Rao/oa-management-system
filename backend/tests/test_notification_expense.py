from decimal import Decimal

from tests.conftest import (
    make_expense,
    make_permission,
    make_role,
    make_user,
)


async def _notifications_of(db, user_id):
    from app.repositories.notification_repository import NotificationRepository

    items, _ = await NotificationRepository(db).list_mine(user_id, None, 0, 50)
    return items


async def test_notify_expense_submitted_content(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(
        db, email="e@x.com", name="张三", manager_id=mgr.id
    )
    e = await make_expense(db, emp, mgr, type="travel", amount=Decimal("1999.50"))

    NotificationService(db).notify_expense_submitted(e, emp.name)
    await db.commit()

    items = await _notifications_of(db, mgr.id)
    assert len(items) == 1
    n = items[0]
    assert n.type == "expense_submitted"
    assert n.title == "新的待审批任务"
    assert n.content == "张三 提交了 1999.5 元的差旅报销,待您审批"
    assert n.ref_type == "expense"
    assert n.ref_id == e.id


async def test_notify_expense_pending_l2_fans_out(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", name="张三", manager_id=mgr.id)
    perm = await make_permission(db, code="expense:approve_l2", name="二级审批")
    role = await make_role(db, code="hr", name="HR", permissions=[perm])
    admin1 = await make_user(db, email="a1@x.com", roles=[role])
    admin2 = await make_user(db, email="a2@x.com", roles=[role])
    outsider = await make_user(db, email="o@x.com")
    e = await make_expense(db, emp, None, amount=Decimal("2000.00"), status="pending_l2")

    await NotificationService(db).notify_expense_pending_l2(e, emp.name)
    await db.commit()

    for u in (admin1, admin2):
        items = await _notifications_of(db, u.id)
        assert len(items) == 1
        assert items[0].type == "expense_pending_l2"
        assert items[0].content == "张三 的 2000 元差旅报销已通过主管审批,待您二级审批"
    assert await _notifications_of(db, outsider.id) == []


async def test_notify_expense_pending_l2_skips_inactive(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    perm = await make_permission(db, code="expense:approve_l2", name="二级审批")
    role = await make_role(db, code="hr", name="HR", permissions=[perm])
    active = await make_user(db, email="a@x.com", roles=[role])
    await make_user(db, email="i@x.com", roles=[role], is_active=False)
    e = await make_expense(db, emp, None, status="pending_l2")

    await NotificationService(db).notify_expense_pending_l2(e, emp.name)
    await db.commit()

    assert len(await _notifications_of(db, active.id)) == 1


async def test_notify_expense_approved_content(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await make_expense(db, emp, mgr, type="office", amount=Decimal("88.00"))

    NotificationService(db).notify_expense_approved(e)
    await db.commit()

    items = await _notifications_of(db, emp.id)
    assert len(items) == 1
    n = items[0]
    assert n.type == "expense_approved"
    assert n.title == "报销申请已通过"
    assert n.content == "您 88 元的办公报销已通过"


async def test_notify_expense_rejected_content_and_clamp(db):
    from app.services.notification_service import NotificationService

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await make_expense(db, emp, mgr, type="transport", amount=Decimal("66.00"))

    NotificationService(db).notify_expense_rejected(e, "票据不全")
    long_reason = "x" * 500
    NotificationService(db).notify_expense_rejected(e, long_reason)
    await db.commit()

    items = await _notifications_of(db, emp.id)
    assert len(items) == 2
    short = [n for n in items if "票据不全" in n.content][0]
    assert short.type == "expense_rejected"
    assert short.title == "报销申请已驳回"
    assert short.content == "您 66 元的交通报销已被驳回:票据不全"
    long_n = [n for n in items if "票据不全" not in n.content][0]
    assert len(long_n.content) == 500
