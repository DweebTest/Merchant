from datetime import date

from flask import Blueprint, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from ..extensions import db
from ..models import Entry, FollowUpStatus, Priority

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    open_ids = db.session.scalars(select(FollowUpStatus.id).where(FollowUpStatus.is_open.is_(True))).all()
    high_ids = db.session.scalars(select(Priority.id).where(Priority.is_high.is_(True))).all()
    recent = db.session.scalars(
        select(Entry).order_by(Entry.created_at.desc(), Entry.id.desc()).limit(10)
    ).all()
    due = db.session.scalars(
        select(Entry)
        .where(
            Entry.status_id.in_(open_ids),
            Entry.follow_up_date.is_not(None),
            Entry.follow_up_date <= date.today(),
        )
        .order_by(Entry.follow_up_date)
        .limit(10)
    ).all()
    stats = {
        "entries": db.session.scalar(select(func.count(Entry.id))),
        "open": db.session.scalar(
            select(func.count(Entry.id)).where(Entry.status_id.in_(open_ids))
        ),
        "high": db.session.scalar(
            select(func.count(Entry.id)).where(
                Entry.priority_id.in_(high_ids), Entry.status_id.in_(open_ids)
            )
        ),
        "mine": db.session.scalar(select(func.count(Entry.id)).where(Entry.owner_id == current_user.id)),
    }
    return render_template("main/index.html", stats=stats, recent=recent, due=due,
                           open_ids=open_ids, high_ids=high_ids)


@bp.route("/health")
def health():
    """For load balancers and uptime checks: confirms the database answers."""
    db.session.execute(select(1))
    return {"status": "ok"}


@bp.route("/theme/<name>")
def set_theme(name):
    """Switch the look; remembered in a cookie for a year."""
    from ..urls import safe_next
    from ..themes import available_themes

    resp = make_response(redirect(safe_next(request.args.get("next")) or url_for("main.index")))
    if name in available_themes():
        resp.set_cookie("theme", name, max_age=365 * 24 * 3600, samesite="Lax", httponly=True)
    return resp
