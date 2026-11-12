"""Entries get an owner who can be changed (reassign)

Revision ID: b7e2d4f6a8c0
Revises: a1f3c5e7d9b2
Create Date: 2026-11-12 17:10:00
"""
import sqlalchemy as sa
from alembic import op

revision = "b7e2d4f6a8c0"
down_revision = "a1f3c5e7d9b2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("entries") as batch:
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
    entries = sa.table("entries", sa.column("owner_id", sa.Integer), sa.column("created_by_id", sa.Integer))
    op.get_bind().execute(entries.update().values(owner_id=entries.c.created_by_id))
    with op.batch_alter_table("entries") as batch:
        batch.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
        batch.create_index("ix_entries_owner_id", ["owner_id"])
        batch.create_foreign_key("fk_entries_owner_id", "users", ["owner_id"], ["id"], ondelete="RESTRICT")


def downgrade():
    with op.batch_alter_table("entries") as batch:
        batch.drop_constraint("fk_entries_owner_id", type_="foreignkey")
        batch.drop_index("ix_entries_owner_id")
        batch.drop_column("owner_id")
