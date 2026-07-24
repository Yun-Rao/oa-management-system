from datetime import date

import pytest

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.schemas.leave import LeaveCreate
from app.services.leave_service import LeaveService
from tests.conftest import ALL_PERMISSIONS, make_leave, make_user
from app.models.permission import Permission
from app.models.role import Role


def leave_create(start=date(2026, 8, 1), end=date(2026, 8, 2), type="personal"):
    return LeaveCreate(type=type, start_date=start, end_date=end, reason="私事")


async def make_applicant_with_manager(db, applicant_email="a@x.com", manager_email="m@x.com"):
    manager = await make_user(db, email=manager_email)
    applicant = await make_user(db, email=applicant_email, manager_id=manager.id)
    return applicant, manager


async def test_create_leave_snapshots_manager_and_writes_history(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    assert leave.status == "pending"
    assert leave.approver_id == manager.id
    assert len(leave.history) == 1
    assert leave.history[0].from_status is None
    assert leave.history[0].to_status == "pending"


async def test_create_leave_rejects_inverted_dates(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    with pytest.raises(ValidationError, match="开始日期不能晚于结束日期"):
        await svc.create_leave(
            leave_create(start=date(2026, 8, 3), end=date(2026, 8, 1)), applicant
        )


async def test_create_leave_rejects_without_manager(db):
    svc = LeaveService(db)
    applicant = await make_user(db, email="a@x.com")
    with pytest.raises(ValidationError, match="未设置直属上级,无法提交请假申请"):
        await svc.create_leave(leave_create(), applicant)


async def test_create_leave_rejects_overlap(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    await svc.create_leave(leave_create(date(2026, 8, 1), date(2026, 8, 3)), applicant)
    with pytest.raises(ConflictError, match="该时间段与已有请假申请重叠"):
        await svc.create_leave(leave_create(date(2026, 8, 3), date(2026, 8, 5)), applicant)


async def test_create_leave_allows_adjacent_and_inactive_overlap(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    await svc.create_leave(leave_create(date(2026, 8, 1), date(2026, 8, 3)), applicant)
    # 首尾相接不重叠
    await svc.create_leave(leave_create(date(2026, 8, 4), date(2026, 8, 5)), applicant)
    # rejected/canceled 不阻塞
    await make_leave(db, applicant, manager, status="rejected",
                     start_date=date(2026, 9, 1), end_date=date(2026, 9, 2))
    await svc.create_leave(leave_create(date(2026, 9, 1), date(2026, 9, 2)), applicant)


async def test_cancel_leave_success(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    canceled = await svc.cancel_leave(leave.id, applicant)
    assert canceled.status == "canceled"
    assert canceled.history[-1].to_status == "canceled"
    assert canceled.history[-1].actor_id == applicant.id


async def test_cancel_leave_forbidden_for_other_user(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    other = await make_user(db, email="b@x.com")
    with pytest.raises(ForbiddenError, match="只能撤回自己的请假申请"):
        await svc.cancel_leave(leave.id, other)


async def test_cancel_leave_conflict_when_not_pending(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    await svc.approve_leave(leave.id, manager)
    with pytest.raises(ConflictError, match="该申请已处理,无法操作"):
        await svc.cancel_leave(leave.id, applicant)


async def test_approve_leave_success(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    approved = await svc.approve_leave(leave.id, manager)
    assert approved.status == "approved"
    assert approved.history[-1].to_status == "approved"
    assert approved.history[-1].actor_id == manager.id


async def test_approve_leave_forbidden_for_non_approver(db):
    svc = LeaveService(db)
    applicant, _ = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    other_manager = await make_user(db, email="m2@x.com")
    with pytest.raises(ForbiddenError, match="只有审批人本人可以审批"):
        await svc.approve_leave(leave.id, other_manager)


async def test_reject_leave_requires_reason(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    with pytest.raises(ValidationError, match="驳回必须填写原因"):
        await svc.reject_leave(leave.id, manager, "  ")


async def test_reject_leave_success_with_comment(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    rejected = await svc.reject_leave(leave.id, manager, "时间冲突,请调整")
    assert rejected.status == "rejected"
    assert rejected.history[-1].to_status == "rejected"
    assert rejected.history[-1].comment == "时间冲突,请调整"


async def test_approver_snapshot_survives_manager_change(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)
    # 提交后换上级,在途单仍归原审批人
    applicant.manager_id = (await make_user(db, email="m2@x.com")).id
    await db.commit()
    approved = await svc.approve_leave(leave.id, manager)
    assert approved.status == "approved"


async def test_get_detail_scope(db):
    svc = LeaveService(db)
    applicant, manager = await make_applicant_with_manager(db)
    leave = await svc.create_leave(leave_create(), applicant)

    assert (await svc.get_detail(leave.id, applicant)).id == leave.id
    assert (await svc.get_detail(leave.id, manager)).id == leave.id

    perms = [Permission(code=c, name=n) for c, n in ALL_PERMISSIONS]
    admin = await make_user(
        db, email="admin@x.com",
        roles=[Role(code="admin", name="管理员", permissions=perms)],
    )
    assert (await svc.get_detail(leave.id, admin)).id == leave.id

    outsider = await make_user(db, email="b@x.com")
    with pytest.raises(ForbiddenError, match="无权查看该请假申请"):
        await svc.get_detail(leave.id, outsider)


async def test_get_detail_not_found(db):
    import uuid

    svc = LeaveService(db)
    user = await make_user(db, email="a@x.com")
    with pytest.raises(NotFoundError, match="请假申请不存在"):
        await svc.get_detail(uuid.uuid4(), user)
