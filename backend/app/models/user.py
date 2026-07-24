import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import user_roles
from app.models.base import Base, TimestampMixin
from app.models.role import Role

if TYPE_CHECKING:
    from app.models.department import Department


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")

    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    department: Mapped["Department | None"] = relationship(
        back_populates="members", lazy="selectin"
    )
    manager: Mapped["User | None"] = relationship(
        remote_side="User.id", foreign_keys=[manager_id], lazy="selectin"
    )
