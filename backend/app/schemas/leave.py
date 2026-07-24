import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserBrief


class LeaveCreate(BaseModel):
    type: Literal["personal", "sick", "annual", "compensatory"]
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=500)


class LeaveReject(BaseModel):
    reason: str = Field(max_length=500)


class LeaveHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    actor: UserBrief
    comment: str | None
    created_at: datetime


class LeaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    start_date: date
    end_date: date
    reason: str
    status: str
    applicant: UserBrief
    approver: UserBrief
    created_at: datetime


class LeaveDetailResponse(LeaveResponse):
    history: list[LeaveHistoryItem]


class LeaveListResponse(BaseModel):
    items: list[LeaveResponse]
    total: int
    page: int
    page_size: int
