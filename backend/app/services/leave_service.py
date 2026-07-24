import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.leave import LeaveRequest, LeaveStatusHistory
from app.models.user import User
from app.repositories.leave_repository import LeaveRepository
from app.schemas.leave import LeaveCreate


class LeaveService:
    def __init__(self, db: AsyncSession):
        self.leaves = LeaveRepository(db)

    async def create_leave(
        self, data: LeaveCreate, applicant: User
    ) -> LeaveRequest:
        if data.start_date > data.end_date:
            raise ValidationError("开始日期不能晚于结束日期")
        if applicant.manager_id is None:
            raise ValidationError("未设置直属上级,无法提交请假申请")
        if await self.leaves.find_overlapping(
            applicant.id, data.start_date, data.end_date
        ):
            raise ConflictError("该时间段与已有请假申请重叠")
        leave = LeaveRequest(
            applicant_id=applicant.id,
            approver_id=applicant.manager_id,
            type=data.type,
            start_date=data.start_date,
            end_date=data.end_date,
            reason=data.reason,
        )
        history = LeaveStatusHistory(
            request=leave,
            from_status=None,
            to_status="pending",
            actor_id=applicant.id,
        )
        return await self.leaves.create(leave, history)

    async def get_detail(self, leave_id: uuid.UUID, user: User) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        perms = {p.code for role in user.roles for p in role.permissions}
        if (
            user.id != leave.applicant_id
            and user.id != leave.approver_id
            and "leave:list_all" not in perms
        ):
            raise ForbiddenError("无权查看该请假申请")
        return leave

    async def cancel_leave(self, leave_id: uuid.UUID, user: User) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        if leave.applicant_id != user.id:
            raise ForbiddenError("只能撤回自己的请假申请")
        self._check_pending(leave)
        return await self.leaves.transition(
            leave, "pending", "canceled", user.id, None
        )

    async def approve_leave(self, leave_id: uuid.UUID, user: User) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        self._check_approver(leave, user)
        self._check_pending(leave)
        return await self.leaves.transition(
            leave, "pending", "approved", user.id, None
        )

    async def reject_leave(
        self, leave_id: uuid.UUID, user: User, reason: str
    ) -> LeaveRequest:
        leave = await self._get_or_404(leave_id)
        self._check_approver(leave, user)
        self._check_pending(leave)
        if not reason.strip():
            raise ValidationError("驳回必须填写原因")
        return await self.leaves.transition(
            leave, "pending", "rejected", user.id, reason
        )

    async def list_mine(
        self, user: User, status: str | None, page: int, page_size: int
    ) -> tuple[list[LeaveRequest], int]:
        return await self.leaves.list_mine(
            user.id, status, (page - 1) * page_size, page_size
        )

    async def list_todo(
        self, user: User, page: int, page_size: int
    ) -> tuple[list[LeaveRequest], int]:
        return await self.leaves.list_todo(
            user.id, (page - 1) * page_size, page_size
        )

    async def list_all(
        self,
        department_id: uuid.UUID | None,
        status: str | None,
        leave_type: str | None,
        start_from: date | None,
        end_to: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[LeaveRequest], int]:
        return await self.leaves.list_all(
            department_id,
            status,
            leave_type,
            start_from,
            end_to,
            (page - 1) * page_size,
            page_size,
        )

    async def _get_or_404(self, leave_id: uuid.UUID) -> LeaveRequest:
        leave = await self.leaves.get_by_id(leave_id)
        if leave is None:
            raise NotFoundError("请假申请不存在")
        return leave

    def _check_pending(self, leave: LeaveRequest) -> None:
        if leave.status != "pending":
            raise ConflictError("该申请已处理,无法操作")

    def _check_approver(self, leave: LeaveRequest, user: User) -> None:
        if leave.approver_id != user.id:
            raise ForbiddenError("只有审批人本人可以审批")
