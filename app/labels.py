"""The names the app uses for its lists and the "area" field.

Admins can rename them under Configuration > Labels, so Merchant can be used for
something other than market intelligence without changing any code. Anything
left blank falls back to the default below.
"""
from flask import g, has_app_context
from sqlalchemy import select

from .extensions import db

# key: (what it is, default)
FIELDS = {
    "cluster": ("One economic cluster", "Economic cluster"),
    "clusters": ("Economic clusters, plural", "Economic clusters"),
    "type": ("One opportunity type", "Opportunity type"),
    "types": ("Opportunity types, plural", "Opportunity types"),
    "priority": ("One priority", "Priority"),
    "priorities": ("Priorities, plural", "Priorities"),
    "status": ("One follow-up status", "Follow-up status"),
    "statuses": ("Follow-up statuses, plural", "Follow-up statuses"),
    "area": ("The free-text area field on an entry", "Area impacted"),
}
GROUPS = [
    ("Economic clusters", ["cluster", "clusters"]),
    ("Opportunity types", ["type", "types"]),
    ("Priorities", ["priority", "priorities"]),
    ("Follow-up statuses", ["status", "statuses"]),
    ("Entry form", ["area"]),
]
PREFIX = "label."


def lc(text):
    """Lower-case a label for use mid-sentence, leaving acronyms alone ("CRM area")."""
    if len(text) > 1 and text[1].isupper():
        return text
    return text[:1].lower() + text[1:]


class Labels:
    def __init__(self, values):
        for key, (_, default) in FIELDS.items():
            setattr(self, key, values.get(key) or default)

    def lc(self, key):
        return lc(getattr(self, key))


def _load():
    from .models import Setting
    rows = db.session.execute(select(Setting.key, Setting.value).where(Setting.key.startswith(PREFIX))).all()
    return {k[len(PREFIX):]: v.strip() for k, v in rows if v and v.strip()}


def labels():
    """This request's labels (read from the database once per request)."""
    if not has_app_context():
        return Labels({})
    if "_labels" not in g:
        try:
            g._labels = Labels(_load())
        except Exception:  # table not there yet (before the first upgrade)
            db.session.rollback()
            g._labels = Labels({})
    return g._labels


def save(values):
    from .models import Setting
    for key in FIELDS:
        value = (values.get(key) or "").strip()
        row = db.session.get(Setting, PREFIX + key)
        if value and value != FIELDS[key][1]:
            if row is None:
                db.session.add(Setting(key=PREFIX + key, value=value))
            else:
                row.value = value
        elif row is not None:
            db.session.delete(row)
    db.session.commit()
    g.pop("_labels", None)
