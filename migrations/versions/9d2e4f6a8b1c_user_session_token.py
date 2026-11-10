"""Per-user session token, so account changes sign people out everywhere

Revision ID: 9d2e4f6a8b1c
Revises: 7c1a2b3d4e5f
Create Date: 2026-11-10 17:40:00
"""
import secrets

import sqlalchemy as sa
from alembic import op

revision = "9d2e4f6a8b1c"
down_revision = "7c1a2b3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("session_token", sa.String(length=32), nullable=True))
    conn = op.get_bind()
    for (uid,) in conn.execute(sa.text("SELECT id FROM users")).fetchall():
        conn.execute(sa.text("UPDATE users SET session_token = :t WHERE id = :i"),
                     {"t": secrets.token_hex(16), "i": uid})
    with op.batch_alter_table("users") as batch:
        batch.alter_column("session_token", existing_type=sa.String(length=32), nullable=False)


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("session_token")
