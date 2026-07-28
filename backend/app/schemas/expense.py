import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserBrief


class ExpenseReject(BaseModel):
    reason: str = Field(max_length=500)


class ExpenseHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    actor: UserBrief
    comment: str | None
    created_at: datetime


class ExpenseAttachmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    amount: Decimal
    reason: str
    status: str
    applicant_id: uuid.UUID
    approver_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ExpenseDetailResponse(ExpenseResponse):
    history: list[ExpenseHistoryItem]
    attachments: list[ExpenseAttachmentItem]


class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse]
    total: int
    page: int
    page_size: int
