from datetime import date

from flask import Blueprint, render_template
from flask_login import current_user, login_required
from sqlalchemy import func, select

from ..extensions import db
from ..models import Entry

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    recent = db.session.scalars(
        select(Entry).order_by(Entry.created_at.desc(), Entry.id.desc()).limit(10)
    ).all()
    due = db.session.scalars(
        select(Entry)
        .where(
            Entry.follow_up_status.in_(["open", "in_progress"]),
            Entry.follow_up_date.is_not(None),
            Entry.follow_up_date <= date.today(),
        )
        .order_by(Entry.follow_up_date)
        .limit(10)
    ).all()
    stats = {
        "entries": db.session.scalar(select(func.count(Entry.id))),
        "open": db.session.scalar(
            select(func.count(Entry.id)).where(Entry.follow_up_status.in_(["open", "in_progress"]))
        ),
        "high": db.session.scalar(
            select(func.count(Entry.id)).where(
                Entry.priority == "high", Entry.follow_up_status.in_(["open", "in_progress"])
            )
        ),
        "mine": db.session.scalar(select(func.count(Entry.id)).where(Entry.created_by_id == current_user.id)),
    }
    return render_template("main/index.html", stats=stats, recent=recent, due=due)


@bp.route("/health")
def health():
    """For load balancers and uptime checks: confirms the database answers."""
    db.session.execute(select(1))
    return {"status": "ok"}
