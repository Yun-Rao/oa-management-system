import re
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.core.exceptions import ValidationError
from app.models.user import User
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("", response_model=DashboardSummaryResponse)
async def get_dashboard(
    month: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:view")),
):
    month_start = None
    if month is not None:
        if not _MONTH_RE.match(month):
            raise ValidationError("month 格式须为 YYYY-MM")
        month_start = date(int(month[:4]), int(month[5:7]), 1)
    return await DashboardService(db).get_summary(month_start, current_user)
