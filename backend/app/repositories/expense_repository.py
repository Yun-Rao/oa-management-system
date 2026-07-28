import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.expense import (
    ExpenseAttachment,
    ExpenseRequest,
    ExpenseStatusHistory,
)
from app.models.user import User


class ExpenseRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, expense_id: uuid.UUID) -> ExpenseRequest | None:
        return await self.db.get(ExpenseRequest, expense_id)

    async def get_attachment(
        self, attachment_id: uuid.UUID
    ) -> ExpenseAttachment | None:
        return await self.db.get(ExpenseAttachment, attachment_id)

    async def create(
        self,
        expense: ExpenseRequest,
        history: ExpenseStatusHistory,
        attachments: list[ExpenseAttachment],
    ) -> ExpenseRequest:
        self.db.add(expense)
        self.db.add(history)
        for att in attachments:
            self.db.add(att)
        await self.db.commit()
        await self.db.refresh(expense)
        return expense

    async def transition(
        self,
        expense: ExpenseRequest,
        from_status: str,
        to_status: str,
        actor_id: uuid.UUID,
        comment: str | None,
        clear_approver: bool = False,
    ) -> ExpenseRequest:
        values: dict = {"status": to_status}
        if clear_approver:
            values["approver_id"] = None
        result = await self.db.execute(
            update(ExpenseRequest)
            .where(
                ExpenseRequest.id == expense.id,
                ExpenseRequest.status == from_status,
            )
            .values(**values)
        )
        if result.rowcount == 0:
            await self.db.rollback()
            raise ConflictError("该申请已处理,无法操作")
        expense.status = to_status
        if clear_approver:
            expense.approver_id = None
        self.db.add(
            ExpenseStatusHistory(
                request_id=expense.id,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor_id,
                comment=comment,
            )
        )
        await self.db.commit()
        await self.db.refresh(expense)
        return expense

    async def list_mine(
        self,
        applicant_id: uuid.UUID,
        status: str | None,
        expense_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ExpenseRequest], int]:
        conditions = [ExpenseRequest.applicant_id == applicant_id]
        if status is not None:
            conditions.append(ExpenseRequest.status == status)
        if expense_type is not None:
            conditions.append(ExpenseRequest.type == expense_type)
        total = (
            await self.db.execute(
                select(func.count()).select_from(ExpenseRequest).where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(ExpenseRequest)
            .where(*conditions)
            .order_by(ExpenseRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_todo(
        self,
        user_id: uuid.UUID,
        can_l1: bool,
        can_l2: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[ExpenseRequest], int]:
        clauses = []
        if can_l1:
            clauses.append(
                and_(
                    ExpenseRequest.status == "pending_l1",
                    ExpenseRequest.approver_id == user_id,
                )
            )
        if can_l2:
            clauses.append(ExpenseRequest.status == "pending_l2")
        condition = or_(*clauses)
        total = (
            await self.db.execute(
                select(func.count()).select_from(ExpenseRequest).where(condition)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(ExpenseRequest)
            .where(condition)
            .order_by(ExpenseRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_all(
        self,
        department_id: uuid.UUID | None,
        status: str | None,
        expense_type: str | None,
        start_from: date | None,
        end_to: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ExpenseRequest], int]:
        join_condition = ExpenseRequest.applicant_id == User.id
        conditions = []
        if department_id is not None:
            conditions.append(User.department_id == department_id)
        if status is not None:
            conditions.append(ExpenseRequest.status == status)
        if expense_type is not None:
            conditions.append(ExpenseRequest.type == expense_type)
        if start_from is not None:
            conditions.append(
                ExpenseRequest.created_at >= datetime.combine(start_from, time.min)
            )
        if end_to is not None:
            conditions.append(
                ExpenseRequest.created_at
                < datetime.combine(end_to + timedelta(days=1), time.min)
            )
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(ExpenseRequest)
                .join(User, join_condition)
                .where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(ExpenseRequest)
            .join(User, join_condition)
            .where(*conditions)
            .order_by(ExpenseRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total
