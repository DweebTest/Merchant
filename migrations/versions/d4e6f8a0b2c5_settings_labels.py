"""Settings table, used for admin-editable labels

Revision ID: d4e6f8a0b2c5
Revises: c3d5e7f9a1b4
Create Date: 2026-11-16 14:30:00
"""
import sqlalchemy as sa
from alembic import op

revision = "d4e6f8a0b2c5"
down_revision = "c3d5e7f9a1b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade():
    op.drop_table("settings")
