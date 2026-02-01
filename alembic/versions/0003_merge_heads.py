"""Merge heads for analysis migrations

Revision ID: 0003
Revises: 0002a, 0002b
Create Date: 2026-01-28
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0003"
down_revision = ("0002a", "0002b")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
