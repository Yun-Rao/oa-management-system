import uuid
from decimal import Decimal

from pydantic import BaseModel


class LeaveStatItem(BaseModel):
    department_id: uuid.UUID
    department_name: str
    request_count: int
    total_days: float


class ExpenseStatItem(BaseModel):
    department_id: uuid.UUID
    department_name: str
    request_count: int
    total_amount: Decimal


class ApprovalDurationItem(BaseModel):
    category: str
    completed_count: int
    avg_hours: float | None


class DashboardSummaryResponse(BaseModel):
    month: str
    leave_stats: list[LeaveStatItem]
    expense_stats: list[ExpenseStatItem]
    approval_durations: list[ApprovalDurationItem]
