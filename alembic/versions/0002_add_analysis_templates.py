"""Add analysis templates

Revision ID: 0002b
Revises: 0001
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0002b"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
    )
    op.create_index(op.f("ix_analysis_templates_id"), "analysis_templates", ["id"], unique=False)
    op.create_index(op.f("ix_analysis_templates_owner_id"), "analysis_templates", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_templates_owner_id"), table_name="analysis_templates")
    op.drop_index(op.f("ix_analysis_templates_id"), table_name="analysis_templates")
    op.drop_table("analysis_templates")
