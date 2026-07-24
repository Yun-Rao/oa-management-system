import uuid
from datetime import date, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.leave import LeaveCreate, LeaveDetailResponse, LeaveHistoryItem


def test_leave_create_type_must_be_known():
    with pytest.raises(PydanticValidationError):
        LeaveCreate(
            type="婚假",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
            reason="x",
        )
    ok = LeaveCreate(
        type="annual",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
        reason="家庭旅行",
    )
    assert ok.type == "annual"


def test_leave_create_reason_length():
    with pytest.raises(PydanticValidationError):
        LeaveCreate(
            type="sick",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            reason="",
        )
    with pytest.raises(PydanticValidationError):
        LeaveCreate(
            type="sick",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            reason="x" * 501,
        )


def test_leave_history_item_from_attributes():
    from app.models.leave import LeaveStatusHistory

    entry = LeaveStatusHistory(
        request_id=uuid.uuid4(),
        from_status="pending",
        to_status="rejected",
        actor_id=uuid.uuid4(),
        comment="时间冲突",
    )
    entry.actor = type("U", (), {"id": uuid.uuid4(), "name": "主管"})()
    entry.created_at = datetime(2026, 8, 1, 12, 0, 0)
    item = LeaveHistoryItem.model_validate(entry)
    assert item.from_status == "pending"
    assert item.to_status == "rejected"
    assert item.comment == "时间冲突"
    assert item.actor.name == "主管"


def test_leave_detail_response_extends_base():
    fields = LeaveDetailResponse.model_fields
    for name in ("id", "type", "start_date", "end_date", "reason", "status",
                 "applicant", "approver", "created_at", "history"):
        assert name in fields
