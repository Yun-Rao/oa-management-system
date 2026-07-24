from datetime import date

from app.models.leave import LeaveRequest, LeaveStatusHistory
from app.repositories.leave_repository import LeaveRepository
from tests.conftest import make_department, make_leave, make_user


async def test_find_overlapping_detects(db):
    repo = LeaveRepository(db)
    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    await make_leave(
        db, applicant, approver, start_date=date(2026, 8, 1), end_date=date(2026, 8, 3)
    )
    # 完全包含、部分重叠、含共同边界日均算重叠
    assert await repo.find_overlapping(applicant.id, date(2026, 8, 2), date(2026, 8, 5))
    assert await repo.find_overlapping(applicant.id, date(2026, 7, 30), date(2026, 8, 1))
    assert await repo.find_overlapping(applicant.id, date(2026, 8, 3), date(2026, 8, 5))
    # 首尾相接(次日开始)与其他申请人均不算
    assert await repo.find_overlapping(applicant.id, date(2026, 8, 4), date(2026, 8, 5)) is None
    other = await make_user(db, email="b@x.com")
    assert await repo.find_overlapping(other.id, date(2026, 8, 2), date(2026, 8, 5)) is None


async def test_find_overlapping_ignores_inactive_status(db):
    repo = LeaveRepository(db)
    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    await make_leave(db, applicant, approver, status="rejected")
    await make_leave(db, applicant, approver, status="canceled")
    assert (
        await repo.find_overlapping(applicant.id, date(2026, 8, 1), date(2026, 8, 2))
        is None
    )


async def test_create_persists_request_and_history(db):
    repo = LeaveRepository(db)
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
    history = LeaveStatusHistory(
        request=leave, from_status=None, to_status="pending", actor_id=applicant.id
    )
    saved = await repo.create(leave, history)
    assert saved.id is not None
    assert saved.status == "pending"
    assert len(saved.history) == 1
    assert saved.history[0].from_status is None


async def test_transition_updates_status_and_appends_history(db):
    repo = LeaveRepository(db)
    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    leave = await make_leave(db, applicant, approver)
    updated = await repo.transition(
        leave, "pending", "approved", approver.id, None
    )
    assert updated.status == "approved"
    assert len(updated.history) == 1
    entry = updated.history[0]
    assert entry.from_status == "pending"
    assert entry.to_status == "approved"
    assert entry.actor_id == approver.id


async def test_list_mine_filter_and_total(db):
    repo = LeaveRepository(db)
    applicant = await make_user(db, email="a@x.com")
    approver = await make_user(db, email="m@x.com")
    await make_leave(db, applicant, approver, status="pending")
    await make_leave(db, applicant, approver, status="approved")
    await make_leave(db, await make_user(db, email="b@x.com"), approver)

    items, total = await repo.list_mine(applicant.id, None, 0, 20)
    assert total == 2
    items, total = await repo.list_mine(applicant.id, "approved", 0, 20)
    assert total == 1
    assert items[0].status == "approved"


async def test_list_all_department_and_status_filter(db):
    repo = LeaveRepository(db)
    dept = await make_department(db, name="技术部")
    other_dept = await make_department(db, name="市场部")
    approver = await make_user(db, email="m@x.com")
    in_dept = await make_user(db, email="a@x.com", department_id=dept.id)
    out_dept = await make_user(db, email="b@x.com", department_id=other_dept.id)
    await make_leave(db, in_dept, approver, status="pending")
    await make_leave(db, in_dept, approver, status="approved")
    await make_leave(db, out_dept, approver, status="pending")

    items, total = await repo.list_all(dept.id, None, None, None, None, 0, 20)
    assert total == 2
    items, total = await repo.list_all(None, "pending", None, None, None, 0, 20)
    assert total == 2
    items, total = await repo.list_all(dept.id, "pending", None, None, None, 0, 20)
    assert total == 1
    assert items[0].applicant_id == in_dept.id
