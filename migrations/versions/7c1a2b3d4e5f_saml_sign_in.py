"""SAML sign-in: link column, and rename the "entra" sign-in method to "sso"

Revision ID: 7c1a2b3d4e5f
Revises: 250ff65686dd
Create Date: 2026-11-10 16:10:00
"""
import sqlalchemy as sa
from alembic import op

revision = "7c1a2b3d4e5f"
down_revision = "250ff65686dd"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("saml_name_id", sa.String(length=255), nullable=True))
        batch.create_unique_constraint("uq_users_saml_name_id", ["saml_name_id"])
    op.execute("UPDATE users SET auth_provider = 'sso' WHERE auth_provider = 'entra'")


def downgrade():
    op.execute("UPDATE users SET auth_provider = 'entra' WHERE auth_provider = 'sso'")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_saml_name_id", type_="unique")
        batch.drop_column("saml_name_id")
