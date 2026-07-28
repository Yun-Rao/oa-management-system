import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.expense import (
    ExpenseAttachment,
    ExpenseRequest,
    ExpenseStatusHistory,
)
from app.models.user import User
from app.repositories.expense_repository import ExpenseRepository
from app.services.notification_service import NotificationService


class ExpenseService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.expenses = ExpenseRepository(db)
        self.notifications = NotificationService(db)

    async def create_expense(
        self,
        type: str,
        amount: Decimal,
        reason: str,
        files: list[tuple[str, str, bytes]],
        applicant: User,
    ) -> ExpenseRequest:
        if applicant.manager_id is None:
            raise ValidationError("未设置直属上级,无法提交报销申请")
        expense = ExpenseRequest(
            id=uuid.uuid4(),
            applicant_id=applicant.id,
            approver_id=applicant.manager_id,
            type=type,
            amount=amount,
            reason=reason,
        )
        stored = self._store_files(expense.id, files)
        attachments = [
            ExpenseAttachment(
                expense_id=expense.id,
                filename=filename,
                stored_path=stored_path,
                content_type=content_type,
                size_bytes=size,
            )
            for filename, content_type, size, stored_path in stored
        ]
        history = ExpenseStatusHistory(
            request=expense,
            from_status=None,
            to_status="pending_l1",
            actor_id=applicant.id,
        )
        self.notifications.notify_expense_submitted(expense, applicant.name)
        try:
            return await self.expenses.create(expense, history, attachments)
        except Exception:
            self._remove_files([s[3] for s in stored])
            raise

    async def get_detail(
        self, expense_id: uuid.UUID, user: User
    ) -> ExpenseRequest:
        expense = await self._get_or_404(expense_id)
        self._check_visible(expense, user)
        return expense

    async def get_attachment(
        self, expense_id: uuid.UUID, attachment_id: uuid.UUID, user: User
    ) -> ExpenseAttachment:
        expense = await self._get_or_404(expense_id)
        self._check_visible(expense, user)
        att = await self.expenses.get_attachment(attachment_id)
        if att is None or att.expense_id != expense.id:
            raise NotFoundError("附件不存在")
        return att

    async def cancel_expense(
        self, expense_id: uuid.UUID, user: User
    ) -> ExpenseRequest:
        expense = await self._get_or_404(expense_id)
        if expense.applicant_id != user.id:
            raise ForbiddenError("只能撤回自己的报销申请")
        if expense.status not in ("pending_l1", "pending_l2"):
            raise ConflictError("该申请已处理,无法操作")
        return await self.expenses.transition(
            expense, expense.status, "cancelled", user.id, None
        )

    async def approve_expense(
        self, expense_id: uuid.UUID, user: User
    ) -> ExpenseRequest:
        expense = await self._get_or_404(expense_id)
        if expense.status == "pending_l1":
            self._check_l1_approver(expense, user)
            if expense.amount > settings.EXPENSE_L2_THRESHOLD:
                await self.notifications.notify_expense_pending_l2(
                    expense, expense.applicant.name
                )
                return await self.expenses.transition(
                    expense,
                    "pending_l1",
                    "pending_l2",
                    user.id,
                    None,
                    clear_approver=True,
                )
            self.notifications.notify_expense_approved(expense)
            return await self.expenses.transition(
                expense, "pending_l1", "approved", user.id, None
            )
        if expense.status == "pending_l2":
            self._check_l2_approver(expense, user)
            self.notifications.notify_expense_approved(expense)
            return await self.expenses.transition(
                expense, "pending_l2", "approved", user.id, None
            )
        raise ConflictError("该申请已处理,无法操作")

    async def reject_expense(
        self, expense_id: uuid.UUID, user: User, reason: str
    ) -> ExpenseRequest:
        expense = await self._get_or_404(expense_id)
        if expense.status == "pending_l1":
            self._check_l1_approver(expense, user)
        elif expense.status == "pending_l2":
            self._check_l2_approver(expense, user)
        else:
            raise ConflictError("该申请已处理,无法操作")
        if not reason.strip():
            raise ValidationError("驳回必须填写原因")
        self.notifications.notify_expense_rejected(expense, reason)
        return await self.expenses.transition(
            expense, expense.status, "rejected", user.id, reason
        )

    async def list_mine(
        self,
        user: User,
        status: str | None,
        expense_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ExpenseRequest], int]:
        return await self.expenses.list_mine(
            user.id, status, expense_type, (page - 1) * page_size, page_size
        )

    async def list_todo(
        self, user: User, page: int, page_size: int
    ) -> tuple[list[ExpenseRequest], int]:
        perms = self._perms(user)
        can_l1 = "expense:approve" in perms
        can_l2 = "expense:approve_l2" in perms
        if not (can_l1 or can_l2):
            raise ForbiddenError("无权限执行此操作")
        return await self.expenses.list_todo(
            user.id, can_l1, can_l2, (page - 1) * page_size, page_size
        )

    async def list_all(
        self,
        department_id: uuid.UUID | None,
        status: str | None,
        expense_type: str | None,
        start_from: date | None,
        end_to: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ExpenseRequest], int]:
        return await self.expenses.list_all(
            department_id,
            status,
            expense_type,
            start_from,
            end_to,
            (page - 1) * page_size,
            page_size,
        )

    async def _get_or_404(self, expense_id: uuid.UUID) -> ExpenseRequest:
        expense = await self.expenses.get_by_id(expense_id)
        if expense is None:
            raise NotFoundError("报销申请不存在")
        return expense

    def _perms(self, user: User) -> set[str]:
        return {p.code for role in user.roles for p in role.permissions}

    def _check_l1_approver(self, expense: ExpenseRequest, user: User) -> None:
        if (
            "expense:approve" not in self._perms(user)
            or expense.approver_id != user.id
        ):
            raise ForbiddenError("只有当前审批人可以审批")

    def _check_l2_approver(self, expense: ExpenseRequest, user: User) -> None:
        if "expense:approve_l2" not in self._perms(user):
            raise ForbiddenError("只有当前审批人可以审批")
        if expense.applicant_id == user.id:
            raise ForbiddenError("不能审批自己的报销申请")

    def _check_visible(self, expense: ExpenseRequest, user: User) -> None:
        perms = self._perms(user)
        if user.id == expense.applicant_id:
            return
        if expense.status == "pending_l1" and expense.approver_id == user.id:
            return
        if expense.status == "pending_l2" and "expense:approve_l2" in perms:
            return
        if "expense:list_all" in perms:
            return
        raise ForbiddenError("无权查看该报销申请")

    def _store_files(
        self, expense_id: uuid.UUID, files: list[tuple[str, str, bytes]]
    ) -> list[tuple[str, str, int, str]]:
        base = Path(settings.UPLOAD_DIR) / "expenses" / str(expense_id)
        base.mkdir(parents=True, exist_ok=True)
        stored = []
        for filename, content_type, content in files:
            ext = filename.rsplit(".", 1)[-1].lower()
            path = base / f"{uuid.uuid4()}.{ext}"
            path.write_bytes(content)
            stored.append(
                (
                    filename,
                    content_type,
                    len(content),
                    path.relative_to(settings.UPLOAD_DIR).as_posix(),
                )
            )
        return stored

    def _remove_files(self, stored_paths: list[str]) -> None:
        for p in stored_paths:
            target = Path(settings.UPLOAD_DIR) / p
            target.unlink(missing_ok=True)
