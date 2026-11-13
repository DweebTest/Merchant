"""Users can be deleted while their name stays on entries; groups can be inactive

Revision ID: c3d5e7f9a1b4
Revises: b7e2d4f6a8c0
Create Date: 2026-11-13 16:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "c3d5e7f9a1b4"
down_revision = "b7e2d4f6a8c0"
branch_labels = None
depends_on = None


def _fk_name(table, column):
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk["constrained_columns"] == [column]:
            return fk["name"]
    return None


def _repoint(table, column, ondelete, nullable):
    """Recreate a users FK with a new ON DELETE rule and nullability."""
    name = _fk_name(table, column)
    with op.batch_alter_table(table) as batch:
        if name:
            batch.drop_constraint(name, type_="foreignkey")
        batch.alter_column(column, existing_type=sa.Integer(), nullable=nullable)
        batch.create_foreign_key(f"fk_{table}_{column}", "users", [column], ["id"], ondelete=ondelete)


def upgrade():
    with op.batch_alter_table("entries") as batch:
        batch.add_column(sa.Column("created_by_name", sa.String(length=200), nullable=False, server_default=""))
    op.execute("UPDATE entries SET created_by_name = "
               "(SELECT display_name FROM users WHERE users.id = entries.created_by_id)")
    _repoint("entries", "created_by_id", "SET NULL", True)
    _repoint("entries", "owner_id", "SET NULL", True)
    _repoint("attachments", "uploaded_by_id", "SET NULL", True)
    with op.batch_alter_table("groups") as batch:
        batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    # Only possible while no user has been deleted (the columns must be filled).
    with op.batch_alter_table("groups") as batch:
        batch.drop_column("is_active")
    _repoint("attachments", "uploaded_by_id", "RESTRICT", False)
    _repoint("entries", "owner_id", "RESTRICT", False)
    _repoint("entries", "created_by_id", "RESTRICT", False)
    with op.batch_alter_table("entries") as batch:
        batch.drop_column("created_by_name")
