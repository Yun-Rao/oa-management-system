from datetime import datetime
from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError
from app.models.expense import ExpenseStatusHistory
from tests.conftest import make_expense, make_user


async def test_list_mine_filter_and_pagination(db):
    from app.repositories.expense_repository import ExpenseRepository

    u1 = await make_user(db, email="u1@x.com")
    u2 = await make_user(db, email="u2@x.com")
    await make_expense(db, u1, None, type="travel")
    await make_expense(db, u1, None, type="office", status="approved")
    await make_expense(db, u2, None, type="travel")

    repo = ExpenseRepository(db)
    _, total_all = await repo.list_mine(u1.id, None, None, 0, 20)
    _, total_travel = await repo.list_mine(u1.id, None, "travel", 0, 20)
    _, total_approved = await repo.list_mine(u1.id, "approved", None, 0, 20)
    assert (total_all, total_travel, total_approved) == (2, 1, 1)

    items, total = await repo.list_mine(u1.id, None, None, 1, 1)
    assert total == 2
    assert len(items) == 1


async def test_list_todo_l1_only(db):
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    await make_expense(db, emp, mgr, status="pending_l1")
    await make_expense(db, emp, None, status="pending_l2")

    items, total = await ExpenseRepository(db).list_todo(
        mgr.id, True, False, 0, 20
    )
    assert total == 1
    assert items[0].status == "pending_l1"


async def test_list_todo_l2_pool_and_merged(db):
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    other_mgr = await make_user(db, email="om@x.com")
    await make_expense(db, emp, mgr, status="pending_l1")
    await make_expense(db, emp, None, status="pending_l2")

    repo = ExpenseRepository(db)
    # L2 视角:看到所有 pending_l2,不看别人的 pending_l1
    items, total = await repo.list_todo(other_mgr.id, False, True, 0, 20)
    assert total == 1
    assert items[0].status == "pending_l2"
    # 合并视角:mgr 两种都有权限 → 自己的 pending_l1 + 全部 pending_l2
    _, total = await repo.list_todo(mgr.id, True, True, 0, 20)
    assert total == 2


async def test_list_todo_no_permission_returns_empty(db):
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    await make_expense(db, emp, mgr, status="pending_l1")
    await make_expense(db, emp, None, status="pending_l2")

    items, total = await ExpenseRepository(db).list_todo(
        emp.id, False, False, 0, 20
    )
    assert items == []
    assert total == 0


async def test_list_all_filters(db):
    from app.repositories.expense_repository import ExpenseRepository

    dept = await make_user(db, email="d@x.com")  # 占位,部门过滤另测
    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    await make_expense(db, emp, mgr, type="travel", status="pending_l1")
    await make_expense(db, emp, mgr, type="office", status="rejected")

    repo = ExpenseRepository(db)
    _, total_all = await repo.list_all(None, None, None, None, None, 0, 20)
    _, total_rejected = await repo.list_all(None, "rejected", None, None, None, 0, 20)
    _, total_office = await repo.list_all(None, None, "office", None, None, 0, 20)
    _, total_none = await repo.list_all(None, "approved", None, None, None, 0, 20)
    assert (total_all, total_rejected, total_office, total_none) == (2, 1, 1, 0)


async def test_transition_optimistic_lock(db):
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await make_expense(db, emp, mgr, status="pending_l1")

    repo = ExpenseRepository(db)
    with pytest.raises(ConflictError):
        await repo.transition(e, "approved", "rejected", mgr.id, None)


async def test_transition_clear_approver(db):
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = await make_expense(db, emp, mgr, status="pending_l1")

    repo = ExpenseRepository(db)
    e = await repo.transition(
        e, "pending_l1", "pending_l2", mgr.id, None, clear_approver=True
    )
    assert e.status == "pending_l2"
    assert e.approver_id is None
    assert len(e.history) == 1
    assert e.history[0].from_status == "pending_l1"
    assert e.history[0].to_status == "pending_l2"
    assert e.history[0].actor_id == mgr.id


async def test_create_persists_attachments_and_history(db):
    from app.models.expense import ExpenseAttachment, ExpenseRequest
    from app.repositories.expense_repository import ExpenseRepository

    mgr = await make_user(db, email="m@x.com")
    emp = await make_user(db, email="e@x.com", manager_id=mgr.id)
    e = ExpenseRequest(
        applicant_id=emp.id,
        approver_id=mgr.id,
        type="travel",
        amount=Decimal("100.00"),
        reason="x",
    )
    history = ExpenseStatusHistory(
        request=e, from_status=None, to_status="pending_l1", actor_id=emp.id
    )
    att = ExpenseAttachment(
        expense=e,
        filename="a.png",
        stored_path="expenses/x/y.png",
        content_type="image/png",
        size_bytes=3,
    )
    repo = ExpenseRepository(db)
    e = await repo.create(e, history, [att])
    assert e.id is not None
    assert len(e.history) == 1
    assert len(e.attachments) == 1
    got = await repo.get_attachment(e.attachments[0].id)
    assert got is not None and got.filename == "a.png"
