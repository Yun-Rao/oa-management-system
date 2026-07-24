import uuid
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class _Item(Base, TimestampMixin):
    __tablename__ = "_test_items"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50))


def test_base_metadata_registers_models():
    assert "_test_items" in Base.metadata.tables


def test_timestamp_mixin_columns():
    table = Base.metadata.tables["_test_items"]
    assert "created_at" in table.c
    assert "updated_at" in table.c
