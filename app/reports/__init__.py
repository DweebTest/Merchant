"""Reports: on-screen view and PDF download for each report."""
from datetime import date, timedelta

from flask import Blueprint, Response, abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from ..extensions import db
from ..models import Cluster
from .data import SPECS, build_report
from .pdf import render_pdf

bp = Blueprint("reports", __name__)

PRESETS = {"30": "Last 30 days", "90": "Last 90 days", "180": "Last 6 months", "365": "Last 12 months"}


def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _read_args(spec):
    """Work out the period and cluster filter from the query string."""
    today = date.today()
    date_to = _parse_date(request.args.get("to")) or today
    date_from = _parse_date(request.args.get("from"))
    preset = request.args.get("range", "")
    if date_from is None:
        days = int(preset) if preset in PRESETS else spec.default_days
        date_from = date_to - timedelta(days=max(days, 1) - 1)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    cluster_ids = []
    for v in request.args.getlist("cluster"):
        try:
            cluster_ids.append(int(v))
        except ValueError:
            pass
    return date_from, date_to, cluster_ids


@bp.route("/")
@login_required
def index():
    return render_template("reports/index.html", specs=SPECS.values())


def _get_spec(key):
    return SPECS.get(key) or abort(404)


@bp.route("/<key>")
@login_required
def view(key):
    spec = _get_spec(key)
    date_from, date_to, cluster_ids = _read_args(spec)
    report = build_report(key, date_from, date_to, cluster_ids)
    clusters = db.session.scalars(select(Cluster).order_by(Cluster.sort_order, Cluster.name)).all()
    return render_template(
        "reports/view.html", report=report, spec=spec, clusters=clusters, presets=PRESETS,
        date_from=date_from, date_to=date_to, cluster_ids=cluster_ids,
        query=request.query_string.decode(),
    )


@bp.route("/<key>.pdf")
@login_required
def pdf(key):
    spec = _get_spec(key)
    date_from, date_to, cluster_ids = _read_args(spec)
    report = build_report(key, date_from, date_to, cluster_ids)
    data = render_pdf(report, generated_by=current_user.display_name)
    stamp = date.today().isoformat() if not spec.uses_period else f"{date_from.isoformat()}_to_{date_to.isoformat()}"
    filename = f"merchant-{key}-{stamp}.pdf"
    return Response(
        data,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
