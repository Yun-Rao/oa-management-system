import uuid
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError

from app.models.leave import LeaveRequest, LeaveStatusHistory
from app.models.user import User


class LeaveRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, leave_id: uuid.UUID) -> LeaveRequest | None:
        return await self.db.get(LeaveRequest, leave_id)

    async def find_overlapping(
        self, applicant_id: uuid.UUID, start_date: date, end_date: date
    ) -> LeaveRequest | None:
        result = await self.db.execute(
            select(LeaveRequest).where(
                LeaveRequest.applicant_id == applicant_id,
                LeaveRequest.status.in_(["pending", "approved"]),
                LeaveRequest.end_date >= start_date,
                LeaveRequest.start_date <= end_date,
            )
        )
        return result.scalars().first()

    async def create(
        self, leave: LeaveRequest, history: LeaveStatusHistory
    ) -> LeaveRequest:
        self.db.add(leave)
        self.db.add(history)
        await self.db.commit()
        await self.db.refresh(leave)
        return leave

    async def transition(
        self,
        leave: LeaveRequest,
        from_status: str,
        to_status: str,
        actor_id: uuid.UUID,
        comment: str | None,
    ) -> LeaveRequest:
        result = await self.db.execute(
            update(LeaveRequest)
            .where(LeaveRequest.id == leave.id, LeaveRequest.status == from_status)
            .values(status=to_status)
        )
        if result.rowcount == 0:
            await self.db.rollback()
            raise ConflictError("该申请已处理,无法操作")
        leave.status = to_status
        self.db.add(
            LeaveStatusHistory(
                request_id=leave.id,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor_id,
                comment=comment,
            )
        )
        await self.db.commit()
        await self.db.refresh(leave)
        return leave

    async def list_mine(
        self, applicant_id: uuid.UUID, status: str | None, offset: int, limit: int
    ) -> tuple[list[LeaveRequest], int]:
        conditions = [LeaveRequest.applicant_id == applicant_id]
        if status is not None:
            conditions.append(LeaveRequest.status == status)
        total = (
            await self.db.execute(
                select(func.count()).select_from(LeaveRequest).where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(LeaveRequest)
            .where(*conditions)
            .order_by(LeaveRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_todo(
        self, approver_id: uuid.UUID, offset: int, limit: int
    ) -> tuple[list[LeaveRequest], int]:
        conditions = [
            LeaveRequest.approver_id == approver_id,
            LeaveRequest.status == "pending",
        ]
        total = (
            await self.db.execute(
                select(func.count()).select_from(LeaveRequest).where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(LeaveRequest)
            .where(*conditions)
            .order_by(LeaveRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_all(
        self,
        department_id: uuid.UUID | None,
        status: str | None,
        leave_type: str | None,
        start_from: date | None,
        end_to: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[LeaveRequest], int]:
        join_condition = LeaveRequest.applicant_id == User.id
        conditions = []
        if department_id is not None:
            conditions.append(User.department_id == department_id)
        if status is not None:
            conditions.append(LeaveRequest.status == status)
        if leave_type is not None:
            conditions.append(LeaveRequest.type == leave_type)
        if start_from is not None:
            conditions.append(LeaveRequest.end_date >= start_from)
        if end_to is not None:
            conditions.append(LeaveRequest.start_date <= end_to)
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(LeaveRequest)
                .join(User, join_condition)
                .where(*conditions)
            )
        ).scalar_one()
        result = await self.db.execute(
            select(LeaveRequest)
            .join(User, join_condition)
            .where(*conditions)
            .order_by(LeaveRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total
