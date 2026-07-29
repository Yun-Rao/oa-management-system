import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import (
    ApprovalDurationItem,
    DashboardSummaryResponse,
    ExpenseStatItem,
    LeaveStatItem,
)

CATEGORIES = ("leave", "expense")


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.dashboard = DashboardRepository(db)

    async def get_summary(
        self, month: date | None, user: User
    ) -> DashboardSummaryResponse:
        if month is None:
            month = date.today()
        month_start = month.replace(day=1)
        last_day = calendar.monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)
        month_str = f"{month_start.year:04d}-{month_start.month:02d}"

        perms = {p.code for role in user.roles for p in role.permissions}
        if "dashboard:view_all" not in perms and user.department_id is None:
            # 无部门 Manager:department_id=None 在仓储表示"不过滤",必须在此拦截
            return DashboardSummaryResponse(
                month=month_str,
                leave_stats=[],
                expense_stats=[],
                approval_durations=self._empty_durations(),
            )
        department_id = (
            None if "dashboard:view_all" in perms else user.department_id
        )

        leave_rows = await self.dashboard.leave_rows(
            month_start, month_end, department_id
        )
        expense_rows = await self.dashboard.expense_rows(
            month_start, month_end, department_id
        )
        duration_rows = await self.dashboard.duration_rows(
            month_start, month_end, department_id
        )
        return DashboardSummaryResponse(
            month=month_str,
            leave_stats=self._aggregate_leave(leave_rows, month_start, month_end),
            expense_stats=self._aggregate_expense(expense_rows),
            approval_durations=self._aggregate_durations(duration_rows),
        )

    @staticmethod
    def _aggregate_leave(rows, month_start, month_end) -> list[LeaveStatItem]:
        agg: dict = {}
        for dept_id, dept_name, start, end in rows:
            days = (min(end, month_end) - max(start, month_start)).days + 1
            entry = agg.setdefault(
                dept_id, {"name": dept_name, "count": 0, "days": 0}
            )
            entry["count"] += 1
            entry["days"] += days
        return [
            LeaveStatItem(
                department_id=dept_id,
                department_name=v["name"],
                request_count=v["count"],
                total_days=round(float(v["days"]), 1),
            )
            for dept_id, v in agg.items()
        ]

    @staticmethod
    def _aggregate_expense(rows) -> list[ExpenseStatItem]:
        agg: dict = {}
        for dept_id, dept_name, amount in rows:
            entry = agg.setdefault(
                dept_id, {"name": dept_name, "count": 0, "total": Decimal("0")}
            )
            entry["count"] += 1
            entry["total"] += amount
        return [
            ExpenseStatItem(
                department_id=dept_id,
                department_name=v["name"],
                request_count=v["count"],
                total_amount=v["total"],
            )
            for dept_id, v in agg.items()
        ]

    def _aggregate_durations(self, rows) -> list[ApprovalDurationItem]:
        buckets: dict[str, list[float]] = {c: [] for c in CATEGORIES}
        for category, created_at, finished_at in rows:
            hours = (finished_at - created_at).total_seconds() / 3600
            buckets[category].append(hours)
        return [
            ApprovalDurationItem(
                category=c,
                completed_count=len(buckets[c]),
                avg_hours=(
                    round(sum(buckets[c]) / len(buckets[c]), 1)
                    if buckets[c]
                    else None
                ),
            )
            for c in CATEGORIES
        ]

    @staticmethod
    def _empty_durations() -> list[ApprovalDurationItem]:
        return [
            ApprovalDurationItem(category=c, completed_count=0, avg_hours=None)
            for c in CATEGORIES
        ]
