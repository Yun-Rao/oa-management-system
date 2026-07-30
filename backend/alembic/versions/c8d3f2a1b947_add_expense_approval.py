"""add expense approval

Revision ID: c8d3f2a1b947
Revises: b4c7e1a9d253
Create Date: 2026-07-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d3f2a1b947"
down_revision: Union[str, None] = "b4c7e1a9d253"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expense_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("applicant_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approver_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["applicant_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expense_requests_applicant_id"),
        "expense_requests",
        ["applicant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expense_requests_approver_id"),
        "expense_requests",
        ["approver_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expense_requests_status"), "expense_requests", ["status"], unique=False
    )
    op.create_table(
        "expense_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["expense_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expense_status_history_request_id"),
        "expense_status_history",
        ["request_id"],
        unique=False,
    )
    op.create_table(
        "expense_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("expense_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["expense_id"], ["expense_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expense_attachments_expense_id"),
        "expense_attachments",
        ["expense_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_expense_attachments_expense_id"), table_name="expense_attachments"
    )
    op.drop_table("expense_attachments")
    op.drop_index(
        op.f("ix_expense_status_history_request_id"),
        table_name="expense_status_history",
    )
    op.drop_table("expense_status_history")
    op.drop_index(op.f("ix_expense_requests_status"), table_name="expense_requests")
    op.drop_index(
        op.f("ix_expense_requests_approver_id"), table_name="expense_requests"
    )
    op.drop_index(
        op.f("ix_expense_requests_applicant_id"), table_name="expense_requests"
    )
    op.drop_table("expense_requests")
