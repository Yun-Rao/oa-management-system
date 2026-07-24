"""add org structure

Revision ID: 9c8e2f4a1b07
Revises: f70a6caabc83
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c8e2f4a1b07"
down_revision: Union[str, None] = "f70a6caabc83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["parent_id"], ["departments.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_departments_parent_id"), "departments", ["parent_id"], unique=False
    )
    op.create_index(
        "uq_departments_parent_name",
        "departments",
        ["parent_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )
    op.add_column("users", sa.Column("department_id", sa.Uuid(), nullable=True))
    op.add_column("users", sa.Column("manager_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_users_department_id"), "users", ["department_id"], unique=False
    )
    op.create_index(op.f("ix_users_manager_id"), "users", ["manager_id"], unique=False)
    op.create_foreign_key(
        "fk_users_department_id",
        "users",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_users_manager_id",
        "users",
        "users",
        ["manager_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_manager_id", "users", type_="foreignkey")
    op.drop_constraint("fk_users_department_id", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_manager_id"), table_name="users")
    op.drop_index(op.f("ix_users_department_id"), table_name="users")
    op.drop_column("users", "manager_id")
    op.drop_column("users", "department_id")
    op.drop_index("uq_departments_parent_name", table_name="departments")
    op.drop_index(op.f("ix_departments_parent_id"), table_name="departments")
    op.drop_table("departments")
