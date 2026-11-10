"""Priorities and follow-up statuses become lists administrators can edit

Revision ID: a1f3c5e7d9b2
Revises: 9d2e4f6a8b1c
Create Date: 2026-11-10 18:30:00
"""
from urllib.parse import parse_qsl, urlencode

import sqlalchemy as sa
from alembic import op

revision = "a1f3c5e7d9b2"
down_revision = "9d2e4f6a8b1c"
branch_labels = None
depends_on = None

# old code -> (name, sort order, flags)
PRIORITIES = {
    "high": ("High", 10, {"is_high": True, "is_default": False}),
    "normal": ("Normal", 20, {"is_high": False, "is_default": True}),
    "low": ("Low", 30, {"is_high": False, "is_default": False}),
}
STATUSES = {
    "open": ("Open", 10, {"is_open": True, "is_default": True, "colour": "amber"}),
    "in_progress": ("In progress", 20, {"is_open": True, "is_default": False, "colour": "blue"}),
    "done": ("Done", 30, {"is_open": False, "is_default": False, "colour": "green"}),
    "no_action": ("No action needed", 40, {"is_open": False, "is_default": False, "colour": "grey"}),
}


def _lookup_columns():
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]


def _fill(table, values):
    """Insert the defaults and return {old code: new id}."""
    conn = op.get_bind()
    ids = {}
    for code, (name, order, flags) in values.items():
        conn.execute(table.insert().values(name=name, sort_order=order, is_active=True, **flags))
        ids[code] = conn.execute(sa.select(table.c.id).where(table.c.name == name)).scalar_one()
    return ids


def _rewrite_saved_filters(mapping):
    """Saved searches stored status=open etc.; switch them to the new ids."""
    conn = op.get_bind()
    saved = sa.table("saved_filters", sa.column("id", sa.Integer), sa.column("query", sa.String))
    for row in conn.execute(sa.select(saved.c.id, saved.c.query)).all():
        pairs = parse_qsl(row.query or "", keep_blank_values=False)
        new = [(k, str(mapping[k].get(v, v))) if k in mapping else (k, v) for k, v in pairs]
        if new != pairs:
            conn.execute(saved.update().where(saved.c.id == row.id).values(query=urlencode(new)))


def upgrade():
    priorities = op.create_table("priorities", *_lookup_columns(),
                                 sa.Column("is_high", sa.Boolean(), nullable=False, server_default=sa.false()))
    statuses = op.create_table("follow_up_statuses", *_lookup_columns(),
                               sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
                               sa.Column("colour", sa.String(length=10), nullable=False, server_default="grey"))
    p_ids = _fill(priorities, PRIORITIES)
    s_ids = _fill(statuses, STATUSES)

    with op.batch_alter_table("entries") as batch:
        batch.add_column(sa.Column("priority_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("status_id", sa.Integer(), nullable=True))

    entries = sa.table("entries", sa.column("priority", sa.String), sa.column("follow_up_status", sa.String),
                       sa.column("priority_id", sa.Integer), sa.column("status_id", sa.Integer))
    conn = op.get_bind()
    for code, new_id in p_ids.items():
        conn.execute(entries.update().where(entries.c.priority == code).values(priority_id=new_id))
    for code, new_id in s_ids.items():
        conn.execute(entries.update().where(entries.c.follow_up_status == code).values(status_id=new_id))
    # Anything unexpected falls back to the defaults.
    conn.execute(entries.update().where(entries.c.priority_id.is_(None)).values(priority_id=p_ids["normal"]))
    conn.execute(entries.update().where(entries.c.status_id.is_(None)).values(status_id=s_ids["open"]))

    with op.batch_alter_table("entries") as batch:
        batch.alter_column("priority_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("status_id", existing_type=sa.Integer(), nullable=False)
        batch.create_index("ix_entries_priority_id", ["priority_id"])
        batch.create_index("ix_entries_status_id", ["status_id"])
        batch.create_foreign_key("fk_entries_priority_id", "priorities", ["priority_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_entries_status_id", "follow_up_statuses", ["status_id"], ["id"],
                                 ondelete="RESTRICT")
        batch.drop_index("ix_entries_priority")
        batch.drop_index("ix_entries_follow_up_status")
        batch.drop_column("priority")
        batch.drop_column("follow_up_status")

    _rewrite_saved_filters({"priority": {k: v for k, v in p_ids.items()},
                            "status": {k: v for k, v in s_ids.items()}})


def downgrade():
    conn = op.get_bind()
    with op.batch_alter_table("entries") as batch:
        batch.add_column(sa.Column("follow_up_status", sa.String(length=20), nullable=False, server_default="open"))
        batch.add_column(sa.Column("priority", sa.String(length=10), nullable=False, server_default="normal"))

    priorities = sa.table("priorities", sa.column("id", sa.Integer), sa.column("name", sa.String),
                          sa.column("is_high", sa.Boolean))
    statuses = sa.table("follow_up_statuses", sa.column("id", sa.Integer), sa.column("name", sa.String),
                        sa.column("is_open", sa.Boolean))
    entries = sa.table("entries", sa.column("priority", sa.String), sa.column("follow_up_status", sa.String),
                       sa.column("priority_id", sa.Integer), sa.column("status_id", sa.Integer))
    by_name_p = {name: code for code, (name, _, _) in PRIORITIES.items()}
    by_name_s = {name: code for code, (name, _, _) in STATUSES.items()}
    p_back, s_back = {}, {}
    for row in conn.execute(sa.select(priorities)).all():
        code = by_name_p.get(row.name) or ("high" if row.is_high else "normal")
        p_back[row.id] = code
        conn.execute(entries.update().where(entries.c.priority_id == row.id).values(priority=code))
    for row in conn.execute(sa.select(statuses)).all():
        code = by_name_s.get(row.name) or ("open" if row.is_open else "done")
        s_back[row.id] = code
        conn.execute(entries.update().where(entries.c.status_id == row.id).values(follow_up_status=code))

    with op.batch_alter_table("entries") as batch:
        batch.drop_constraint("fk_entries_priority_id", type_="foreignkey")
        batch.drop_constraint("fk_entries_status_id", type_="foreignkey")
        batch.drop_index("ix_entries_priority_id")
        batch.drop_index("ix_entries_status_id")
        batch.drop_column("priority_id")
        batch.drop_column("status_id")
        batch.create_index("ix_entries_priority", ["priority"])
        batch.create_index("ix_entries_follow_up_status", ["follow_up_status"])
    _rewrite_saved_filters({"priority": {str(k): v for k, v in p_back.items()},
                            "status": {str(k): v for k, v in s_back.items()}})
    op.drop_table("follow_up_statuses")
    op.drop_table("priorities")
