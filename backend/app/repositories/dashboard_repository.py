import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.expense import ExpenseRequest, ExpenseStatusHistory
from app.models.leave import LeaveRequest, LeaveStatusHistory
from app.models.user import User

TERMINAL_STATUSES = ("approved", "rejected")


class DashboardRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def leave_rows(
        self, month_start: date, month_end: date, department_id: uuid.UUID | None
    ):
        conditions = [
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= month_end,
            LeaveRequest.end_date >= month_start,
        ]
        if department_id is not None:
            conditions.append(User.department_id == department_id)
        result = await self.db.execute(
            select(
                Department.id,
                Department.name,
                LeaveRequest.start_date,
                LeaveRequest.end_date,
            )
            .select_from(LeaveRequest)
            .join(User, LeaveRequest.applicant_id == User.id)
            .join(Department, User.department_id == Department.id)
            .where(*conditions)
        )
        return list(result.all())

    async def expense_rows(
        self, month_start: date, month_end: date, department_id: uuid.UUID | None
    ):
        start_dt, end_dt = _month_bounds(month_start, month_end)
        conditions = [
            ExpenseRequest.status == "approved",
            ExpenseRequest.created_at >= start_dt,
            ExpenseRequest.created_at < end_dt,
        ]
        if department_id is not None:
            conditions.append(User.department_id == department_id)
        result = await self.db.execute(
            select(Department.id, Department.name, ExpenseRequest.amount)
            .select_from(ExpenseRequest)
            .join(User, ExpenseRequest.applicant_id == User.id)
            .join(Department, User.department_id == Department.id)
            .where(*conditions)
        )
        return list(result.all())

    async def duration_rows(
        self, month_start: date, month_end: date, department_id: uuid.UUID | None
    ):
        start_dt, end_dt = _month_bounds(month_start, month_end)
        leave_q = (
            select(
                literal("leave").label("category"),
                LeaveRequest.created_at,
                LeaveStatusHistory.created_at.label("finished_at"),
            )
            .select_from(LeaveStatusHistory)
            .join(LeaveRequest, LeaveStatusHistory.request_id == LeaveRequest.id)
            .join(User, LeaveRequest.applicant_id == User.id)
            .where(
                LeaveStatusHistory.to_status.in_(TERMINAL_STATUSES),
                LeaveStatusHistory.created_at >= start_dt,
                LeaveStatusHistory.created_at < end_dt,
            )
        )
        expense_q = (
            select(
                literal("expense").label("category"),
                ExpenseRequest.created_at,
                ExpenseStatusHistory.created_at.label("finished_at"),
            )
            .select_from(ExpenseStatusHistory)
            .join(ExpenseRequest, ExpenseStatusHistory.request_id == ExpenseRequest.id)
            .join(User, ExpenseRequest.applicant_id == User.id)
            .where(
                ExpenseStatusHistory.to_status.in_(TERMINAL_STATUSES),
                ExpenseStatusHistory.created_at >= start_dt,
                ExpenseStatusHistory.created_at < end_dt,
            )
        )
        if department_id is not None:
            leave_q = leave_q.where(User.department_id == department_id)
            expense_q = expense_q.where(User.department_id == department_id)
        rows = list((await self.db.execute(leave_q)).all())
        rows += list((await self.db.execute(expense_q)).all())
        return rows


def _month_bounds(month_start: date, month_end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(month_start, time.min),
        datetime.combine(month_end + timedelta(days=1), time.min),
    )
