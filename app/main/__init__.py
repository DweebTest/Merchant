from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func, select

from ..extensions import db
from ..models import Cluster, Entry, OpportunityType

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    stats = {
        "entries": db.session.scalar(select(func.count(Entry.id))),
        "clusters": db.session.scalar(select(func.count(Cluster.id)).where(Cluster.is_active.is_(True))),
        "types": db.session.scalar(select(func.count(OpportunityType.id)).where(OpportunityType.is_active.is_(True))),
    }
    return render_template("main/index.html", stats=stats)


@bp.route("/health")
def health():
    """For load balancers and uptime checks: confirms the database answers."""
    db.session.execute(select(1))
    return {"status": "ok"}
