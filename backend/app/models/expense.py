import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ExpenseRequest(Base, TimestampMixin):
    __tablename__ = "expense_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(20), default="pending_l1", index=True
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )

    applicant: Mapped["User"] = relationship(
        foreign_keys=[applicant_id], lazy="selectin"
    )
    approver: Mapped["User | None"] = relationship(
        foreign_keys=[approver_id], lazy="selectin"
    )
    history: Mapped[list["ExpenseStatusHistory"]] = relationship(
        back_populates="request",
        lazy="selectin",
        order_by="ExpenseStatusHistory.created_at",
    )
    attachments: Mapped[list["ExpenseAttachment"]] = relationship(
        back_populates="expense", lazy="selectin"
    )


class ExpenseStatusHistory(Base):
    __tablename__ = "expense_status_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("expense_requests.id", ondelete="RESTRICT"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    comment: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    request: Mapped[ExpenseRequest] = relationship(back_populates="history")
    actor: Mapped["User"] = relationship(lazy="selectin")


class ExpenseAttachment(Base):
    __tablename__ = "expense_attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    expense_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("expense_requests.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    expense: Mapped[ExpenseRequest] = relationship(back_populates="attachments")
