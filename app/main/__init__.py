from datetime import date

from flask import Blueprint, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from ..extensions import db
from ..models import Entry

bp = Blueprint("main", __name__)

THEMES = ("spaceage", "classic")


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


@bp.route("/theme/<name>")
def set_theme(name):
    """Switch between the space-age and classic look; remembered in a cookie for a year."""
    from ..auth import _safe_next

    resp = make_response(redirect(_safe_next(request.args.get("next")) or url_for("main.index")))
    if name in THEMES:
        resp.set_cookie("theme", name, max_age=365 * 24 * 3600, samesite="Lax", httponly=True)
    return resp
