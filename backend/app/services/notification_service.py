import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.leave import LeaveRequest
from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository

LEAVE_TYPE_LABELS = {
    "personal": "事假",
    "sick": "病假",
    "annual": "年假",
    "compensatory": "调休",
}


def _leave_span(leave: LeaveRequest) -> str:
    return f"{leave.start_date.isoformat()} ~ {leave.end_date.isoformat()}"


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.notifications = NotificationRepository(db)

    def notify_leave_submitted(
        self, leave: LeaveRequest, applicant_name: str
    ) -> None:
        label = LEAVE_TYPE_LABELS.get(leave.type, leave.type)
        self.db.add(
            Notification(
                user_id=leave.approver_id,
                type="leave_submitted",
                title="新的待审批任务",
                content=f"{applicant_name} 提交了 {_leave_span(leave)} 的{label}申请,待您审批",
                ref_type="leave",
                ref_id=leave.id,
            )
        )

    def notify_leave_approved(self, leave: LeaveRequest) -> None:
        label = LEAVE_TYPE_LABELS.get(leave.type, leave.type)
        self.db.add(
            Notification(
                user_id=leave.applicant_id,
                type="leave_approved",
                title="请假申请已通过",
                content=f"您 {_leave_span(leave)} 的{label}申请已通过",
                ref_type="leave",
                ref_id=leave.id,
            )
        )

    def notify_leave_rejected(self, leave: LeaveRequest, reason: str) -> None:
        label = LEAVE_TYPE_LABELS.get(leave.type, leave.type)
        self.db.add(
            Notification(
                user_id=leave.applicant_id,
                type="leave_rejected",
                title="请假申请已驳回",
                content=f"您 {_leave_span(leave)} 的{label}申请已被驳回:{reason}",
                ref_type="leave",
                ref_id=leave.id,
            )
        )

    async def list_mine(
        self, user: User, is_read: bool | None, page: int, page_size: int
    ) -> tuple[list[Notification], int]:
        return await self.notifications.list_mine(
            user.id, is_read, (page - 1) * page_size, page_size
        )

    async def unread_count(self, user: User) -> int:
        return await self.notifications.unread_count(user.id)

    async def mark_read(
        self, notification_id: uuid.UUID, user: User
    ) -> Notification:
        n = await self.notifications.get_by_id(notification_id)
        if n is None:
            raise NotFoundError("通知不存在")
        if n.user_id != user.id:
            raise ForbiddenError("无权操作该通知")
        return await self.notifications.mark_read(n)

    async def mark_all_read(self, user: User) -> int:
        return await self.notifications.mark_all_read(user.id)
