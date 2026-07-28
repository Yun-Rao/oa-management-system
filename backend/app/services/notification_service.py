import uuid

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.expense import ExpenseRequest
from app.models.leave import LeaveRequest
from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_repository import UserRepository

LEAVE_TYPE_LABELS = {
    "personal": "事假",
    "sick": "病假",
    "annual": "年假",
    "compensatory": "调休",
}

EXPENSE_TYPE_LABELS = {
    "travel": "差旅",
    "office": "办公",
    "entertainment": "招待",
    "transport": "交通",
    "other": "其他",
}


def _fmt_amount(amount: Decimal) -> str:
    return format(amount.normalize(), "f")


def _leave_span(leave: LeaveRequest) -> str:
    return f"{leave.start_date.isoformat()} ~ {leave.end_date.isoformat()}"


def _clamp_content(text: str) -> str:
    # Notification.content is String(500); Postgres enforces varchar(500),
    # so clamp here to keep the surrounding action (e.g. leave reject) from
    # failing on the notification INSERT.
    return text[:500]


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
                content=_clamp_content(
                    f"{applicant_name} 提交了 {_leave_span(leave)} 的{label}申请,待您审批"
                ),
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
                content=_clamp_content(
                    f"您 {_leave_span(leave)} 的{label}申请已通过"
                ),
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
                content=_clamp_content(
                    f"您 {_leave_span(leave)} 的{label}申请已被驳回:{reason}"
                ),
                ref_type="leave",
                ref_id=leave.id,
            )
        )

    def notify_expense_submitted(
        self, expense: ExpenseRequest, applicant_name: str
    ) -> None:
        label = EXPENSE_TYPE_LABELS.get(expense.type, expense.type)
        self.db.add(
            Notification(
                user_id=expense.approver_id,
                type="expense_submitted",
                title="新的待审批任务",
                content=_clamp_content(
                    f"{applicant_name} 提交了 {_fmt_amount(expense.amount)} 元的{label}报销,待您审批"
                ),
                ref_type="expense",
                ref_id=expense.id,
            )
        )

    async def notify_expense_pending_l2(
        self, expense: ExpenseRequest, applicant_name: str
    ) -> None:
        label = EXPENSE_TYPE_LABELS.get(expense.type, expense.type)
        approvers = await UserRepository(self.db).list_by_permission(
            "expense:approve_l2"
        )
        for u in approvers:
            self.db.add(
                Notification(
                    user_id=u.id,
                    type="expense_pending_l2",
                    title="新的待审批任务",
                    content=_clamp_content(
                        f"{applicant_name} 的 {_fmt_amount(expense.amount)} 元{label}报销已通过主管审批,待您二级审批"
                    ),
                    ref_type="expense",
                    ref_id=expense.id,
                )
            )

    def notify_expense_approved(self, expense: ExpenseRequest) -> None:
        label = EXPENSE_TYPE_LABELS.get(expense.type, expense.type)
        self.db.add(
            Notification(
                user_id=expense.applicant_id,
                type="expense_approved",
                title="报销申请已通过",
                content=_clamp_content(
                    f"您 {_fmt_amount(expense.amount)} 元的{label}报销已通过"
                ),
                ref_type="expense",
                ref_id=expense.id,
            )
        )

    def notify_expense_rejected(
        self, expense: ExpenseRequest, reason: str
    ) -> None:
        label = EXPENSE_TYPE_LABELS.get(expense.type, expense.type)
        self.db.add(
            Notification(
                user_id=expense.applicant_id,
                type="expense_rejected",
                title="报销申请已驳回",
                content=_clamp_content(
                    f"您 {_fmt_amount(expense.amount)} 元的{label}报销已被驳回:{reason}"
                ),
                ref_type="expense",
                ref_id=expense.id,
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
