"""Entries: the form people fill in after a meeting, and the searchable list."""
import os
import uuid
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import and_, exists, func, or_, select
from werkzeug.utils import secure_filename

from ..extensions import db
from ..forms import ConfirmForm, EntryForm
from ..models import (
    Attachment,
    Cluster,
    Contact,
    Entry,
    FollowUpStatus,
    OpportunityType,
    Organization,
    Priority,
    SavedFilter,
    default_choice,
    entry_clusters,
    entry_opportunity_types,
)

bp = Blueprint("entries", __name__)

PER_PAGE = 25

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "txt", "rtf",
    "png", "jpg", "jpeg", "gif", "webp", "msg", "eml", "odt", "ods", "odp", "zip",
}

DATE_PRESETS = {"7": "Last 7 days", "30": "Last 30 days", "90": "Last 90 days", "365": "Last year"}


# --- Helpers ----------------------------------------------------------------

def can_edit(entry):
    return current_user.is_admin or entry.created_by_id == current_user.id


def _lookup_choices(model, keep_ids=()):
    """Active values, plus any inactive ones this entry already uses."""
    rows = db.session.scalars(
        select(model)
        .where(or_(model.is_active.is_(True), model.id.in_(list(keep_ids) or [-1])))
        .order_by(model.sort_order, model.name)
    )
    return [(r.id, r.name) for r in rows]


def _prepare_form(form, entry=None):
    form.clusters.choices = _lookup_choices(Cluster, [c.id for c in entry.clusters] if entry else ())
    form.opportunity_types.choices = _lookup_choices(
        OpportunityType, [t.id for t in entry.opportunity_types] if entry else ()
    )
    form.priority_id.choices = _lookup_choices(Priority, [entry.priority_id] if entry else ())
    form.status_id.choices = _lookup_choices(FollowUpStatus, [entry.status_id] if entry else ())
    if entry is None and request.method == "GET":
        for fld, model in ((form.priority_id, Priority), (form.status_id, FollowUpStatus)):
            default = default_choice(model)
            fld.data = default.id if default else None


def _organization_names():
    return db.session.scalars(select(Organization.name).order_by(Organization.name)).all()


def _get_or_create_organization(name):
    name = " ".join(name.split())
    org = db.session.scalar(select(Organization).where(func.lower(Organization.name) == name.lower()))
    if org is None:
        org = Organization(name=name)
        db.session.add(org)
    return org


def _resolve_contact(form, org):
    name = " ".join((form.contact_name.data or "").split())
    if not name:
        return None
    contact = None
    if org.id is not None:
        contact = db.session.scalar(
            select(Contact).where(Contact.organization_id == org.id, func.lower(Contact.name) == name.lower())
        )
    if contact is None:
        contact = Contact(name=name, organization=org)
        db.session.add(contact)
    # Fill in or update details that were given.
    for field in ("title", "email", "phone"):
        value = (getattr(form, f"contact_{field}").data or "").strip()
        if value:
            setattr(contact, field, value)
    return contact


def _save_uploads(files, entry):
    """Store uploaded files under random names; return names that were refused."""
    refused = []
    folder = current_app.config["UPLOAD_FOLDER"]
    for f in files or []:
        if not f or not f.filename:
            continue
        original = secure_filename(f.filename) or "file"
        ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
        if ext not in ALLOWED_EXTENSIONS:
            refused.append(f.filename)
            continue
        stored = f"{uuid.uuid4().hex}.{ext}"
        path = os.path.join(folder, stored)
        f.save(path)
        entry.attachments.append(Attachment(
            original_filename=original,
            stored_filename=stored,
            content_type=f.mimetype,
            size_bytes=os.path.getsize(path),
            uploaded_by_id=current_user.id,
        ))
    return refused


def _apply_form(form, entry):
    org = _get_or_create_organization(form.organization.data)
    db.session.flush()  # give a new organization its id before matching contacts
    # Don't let lookups below flush the half-filled entry.
    with db.session.no_autoflush:
        contact = _resolve_contact(form, org)
        clusters = list(db.session.scalars(select(Cluster).where(Cluster.id.in_(form.clusters.data))))
        types = list(db.session.scalars(
            select(OpportunityType).where(OpportunityType.id.in_(form.opportunity_types.data))
        ))
        entry.entry_date = form.entry_date.data
        entry.description = form.description.data.strip()
        entry.organization = org
        entry.contact = contact
        entry.next_step = (form.next_step.data or "").strip() or None
        entry.college_area = (form.college_area.data or "").strip() or None
        entry.link_url = (form.link_url.data or "").strip() or None
        entry.priority_id = form.priority_id.data
        entry.status_id = form.status_id.data
        entry.follow_up_date = form.follow_up_date.data
        entry.clusters = clusters
        entry.opportunity_types = types


def _link_is_safe(url):
    return not url or urlsplit(url).scheme in {"http", "https"}


def _int_list(name):
    out = []
    for v in request.args.getlist(name):
        try:
            out.append(int(v))
        except ValueError:
            pass
    return out


def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _escape_like(term):
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_filters(args):
    """Turn the query string into SQL conditions. Shared with reports later."""
    conds = []
    q = (args.get("q") or "").strip()
    for word in q.split()[:10]:
        like = f"%{_escape_like(word)}%"
        conds.append(or_(
            Entry.description.ilike(like, escape="\\"),
            Entry.next_step.ilike(like, escape="\\"),
            Entry.college_area.ilike(like, escape="\\"),
            Entry.organization.has(Organization.name.ilike(like, escape="\\")),
            Entry.contact.has(Contact.name.ilike(like, escape="\\")),
        ))

    clusters = args["clusters"]
    if clusters:
        conds.append(exists().where(and_(
            entry_clusters.c.entry_id == Entry.id, entry_clusters.c.cluster_id.in_(clusters)
        )))
    types = args["types"]
    if types:
        conds.append(exists().where(and_(
            entry_opportunity_types.c.entry_id == Entry.id,
            entry_opportunity_types.c.opportunity_type_id.in_(types),
        )))

    if args["date_from"]:
        conds.append(Entry.entry_date >= args["date_from"])
    if args["date_to"]:
        conds.append(Entry.entry_date <= args["date_to"])
    if args["status"]:
        conds.append(Entry.status_id.in_(args["status"]))
    if args["priority"]:
        conds.append(Entry.priority_id.in_(args["priority"]))
    if args["mine"]:
        conds.append(Entry.created_by_id == current_user.id)
    return conds


def read_filter_args():
    preset = request.args.get("range", "")
    date_from = _parse_date(request.args.get("from"))
    date_to = _parse_date(request.args.get("to"))
    if preset in DATE_PRESETS and not (date_from or date_to):
        date_from = date.today() - timedelta(days=int(preset))
    return {
        "q": request.args.get("q", ""),
        "clusters": _int_list("cluster"),
        "types": _int_list("type"),
        "date_from": date_from,
        "date_to": date_to,
        "range": preset if preset in DATE_PRESETS else "",
        "status": _int_list("status"),
        "priority": _int_list("priority"),
        "mine": request.args.get("mine") == "1",
        "sort": request.args.get("sort", "date"),
    }


SORTS = {
    "date": (Entry.entry_date.desc(), Entry.id.desc()),
    "date_asc": (Entry.entry_date.asc(), Entry.id.asc()),
    "added": (Entry.created_at.desc(), Entry.id.desc()),
    "follow_up": (Entry.follow_up_date.is_(None), Entry.follow_up_date.asc(), Entry.id.desc()),
}


# --- Views ------------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    args = read_filter_args()
    query = select(Entry).where(*build_filters(args)).order_by(*SORTS.get(args["sort"], SORTS["date"]))
    page = db.paginate(query, per_page=PER_PAGE, error_out=False)
    all_clusters = db.session.scalars(select(Cluster).order_by(Cluster.sort_order, Cluster.name)).all()
    all_types = db.session.scalars(select(OpportunityType).order_by(OpportunityType.sort_order, OpportunityType.name)).all()
    statuses = _lookup_choices(FollowUpStatus, args["status"])
    priorities = _lookup_choices(Priority, args["priority"])
    filtered = any([args["q"], args["clusters"], args["types"], args["date_from"], args["date_to"],
                    args["status"], args["priority"], args["mine"]])
    saved = db.session.scalars(
        select(SavedFilter)
        .where(or_(SavedFilter.user_id == current_user.id, SavedFilter.is_shared.is_(True)))
        .order_by(func.lower(SavedFilter.name))
    ).all()
    return render_template(
        "entries/list.html", page=page, args=args, clusters=all_clusters, types=all_types,
        saved_filters=saved, current_query=clean_query(request.query_string.decode()),
        confirm_form=ConfirmForm(),
        statuses=statuses, priorities=priorities, presets=DATE_PRESETS, filtered=filtered,
    )


@bp.route("/org-defaults")
@login_required
def org_defaults():
    """Details from an organization's most recent entry, used to pre-fill the form."""
    name = " ".join((request.args.get("name") or "").split())
    if not name:
        return {"found": False}
    org = db.session.scalar(select(Organization).where(func.lower(Organization.name) == name.lower()))
    if org is None:
        return {"found": False}
    last = db.session.scalar(
        select(Entry).where(Entry.organization_id == org.id)
        .order_by(Entry.entry_date.desc(), Entry.id.desc()).limit(1)
    )
    if last is None:
        return {"found": True, "organization": org.name, "has_entry": False}
    contact = last.contact
    return {
        "found": True,
        "has_entry": True,
        "organization": org.name,
        "last_entry_date": last.entry_date.isoformat(),
        "last_entry_label": f"{last.entry_date:%b} {last.entry_date.day}, {last.entry_date.year}",
        "clusters": [c.id for c in last.clusters if c.is_active],
        "opportunity_types": [t.id for t in last.opportunity_types if t.is_active],
        "contact": {
            "name": contact.name, "title": contact.title or "", "email": contact.email or "",
            "phone": contact.phone or "",
        } if contact else None,
        "college_area": last.college_area or "",
        "link_url": last.link_url or "",
    }


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = EntryForm()
    _prepare_form(form)
    if request.method == "GET":
        form.entry_date.data = date.today()
    if form.validate_on_submit():
        if not _link_is_safe(form.link_url.data):
            form.link_url.errors.append("Links must start with http:// or https://")
        else:
            entry = Entry(created_by_id=current_user.id)
            _apply_form(form, entry)
            refused = _save_uploads(form.attachments.data, entry)
            db.session.add(entry)
            db.session.commit()
            _flash_refused(refused)
            flash("Entry saved.", "success")
            if request.form.get("another"):
                return redirect(url_for("entries.new"))
            return redirect(url_for("entries.detail", entry_id=entry.id))
    return render_template("entries/form.html", form=form, entry=None, organizations=_organization_names())


@bp.route("/<int:entry_id>")
@login_required
def detail(entry_id):
    entry = db.session.get(Entry, entry_id) or abort(404)
    return render_template("entries/detail.html", entry=entry, can_edit=can_edit(entry),
                           confirm_form=ConfirmForm(), statuses=_lookup_choices(FollowUpStatus, [entry.status_id]))


@bp.route("/<int:entry_id>/edit", methods=["GET", "POST"])
@login_required
def edit(entry_id):
    entry = db.session.get(Entry, entry_id) or abort(404)
    if not can_edit(entry):
        abort(403)
    form = EntryForm(obj=entry)
    _prepare_form(form, entry)
    if request.method == "GET":
        form.organization.data = entry.organization.name
        form.clusters.data = [c.id for c in entry.clusters]
        form.opportunity_types.data = [t.id for t in entry.opportunity_types]
        if entry.contact:
            form.contact_name.data = entry.contact.name
            form.contact_title.data = entry.contact.title
            form.contact_email.data = entry.contact.email
            form.contact_phone.data = entry.contact.phone
    if form.validate_on_submit():
        if not _link_is_safe(form.link_url.data):
            form.link_url.errors.append("Links must start with http:// or https://")
        else:
            _apply_form(form, entry)
            refused = _save_uploads(form.attachments.data, entry)
            db.session.commit()
            _flash_refused(refused)
            flash("Entry updated.", "success")
            return redirect(url_for("entries.detail", entry_id=entry.id))
    return render_template("entries/form.html", form=form, entry=entry, organizations=_organization_names())


@bp.route("/<int:entry_id>/status", methods=["POST"])
@login_required
def set_status(entry_id):
    """Quick status change from the detail page. Anyone signed in can do this,
    so whoever follows up can mark it done."""
    entry = db.session.get(Entry, entry_id) or abort(404)
    try:
        status_id = int(request.form.get("status", ""))
    except ValueError:
        status_id = None
    allowed = {i for i, _ in _lookup_choices(FollowUpStatus, [entry.status_id])}
    if ConfirmForm().validate_on_submit() and status_id in allowed:
        entry.status_id = status_id
        db.session.commit()
        flash("Follow-up status updated.", "success")
    return redirect(url_for("entries.detail", entry_id=entry.id))


@bp.route("/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete(entry_id):
    entry = db.session.get(Entry, entry_id) or abort(404)
    if not can_edit(entry):
        abort(403)
    if ConfirmForm().validate_on_submit():
        files = [a.stored_filename for a in entry.attachments]
        db.session.delete(entry)
        db.session.commit()
        for name in files:
            _remove_file(name)
        flash("Entry deleted.", "success")
    return redirect(url_for("entries.index"))


@bp.route("/attachments/<int:attachment_id>")
@login_required
def download(attachment_id):
    att = db.session.get(Attachment, attachment_id) or abort(404)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"], att.stored_filename,
        as_attachment=True, download_name=att.original_filename,
    )


@bp.route("/attachments/<int:attachment_id>/delete", methods=["POST"])
@login_required
def delete_attachment(attachment_id):
    att = db.session.get(Attachment, attachment_id) or abort(404)
    entry_id = att.entry_id
    if not can_edit(att.entry):
        abort(403)
    if ConfirmForm().validate_on_submit():
        name = att.stored_filename
        db.session.delete(att)
        db.session.commit()
        _remove_file(name)
        flash("Attachment removed.", "success")
    return redirect(url_for("entries.edit", entry_id=entry_id))


def _remove_file(stored_filename):
    try:
        os.remove(os.path.join(current_app.config["UPLOAD_FOLDER"], stored_filename))
    except OSError:
        current_app.logger.warning("Could not remove attachment file %s", stored_filename)


def _flash_refused(refused):
    if refused:
        flash(
            "These files weren't attached because their type isn't allowed: " + ", ".join(refused),
            "error",
        )


# --- Saved filters ----------------------------------------------------------

FILTER_KEYS = {"q", "cluster", "type", "from", "to", "range", "status", "priority", "mine", "sort"}


def clean_query(query):
    """Keep only knowledge base filter parameters (no page number, nothing else)."""
    pairs = [(k, v) for k, v in parse_qsl(query or "", keep_blank_values=False) if k in FILTER_KEYS and v]
    return urlencode(pairs[:100])


@bp.route("/saved-filters", methods=["POST"])
@login_required
def save_filter():
    if not ConfirmForm().validate_on_submit():
        abort(400)
    name = " ".join((request.form.get("name") or "").split())[:100]
    query = clean_query(request.form.get("query", ""))
    if not name:
        flash("Give the saved filter a name.", "error")
    elif not query:
        flash("Choose some filters before saving.", "error")
    else:
        existing = db.session.scalar(
            select(SavedFilter).where(SavedFilter.user_id == current_user.id, func.lower(SavedFilter.name) == name.lower())
        )
        saved = existing or SavedFilter(user_id=current_user.id)
        saved.name = name
        saved.query = query
        saved.is_shared = request.form.get("shared") == "1"
        if existing is None:
            db.session.add(saved)
        db.session.commit()
        flash(f"Saved filter \u201c{name}\u201d{' (updated)' if existing else ''}.", "success")
    return redirect(url_for("entries.index") + (f"?{query}" if query else ""))


@bp.route("/saved-filters/<int:filter_id>/delete", methods=["POST"])
@login_required
def delete_filter(filter_id):
    saved = db.session.get(SavedFilter, filter_id) or abort(404)
    if saved.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    if ConfirmForm().validate_on_submit():
        db.session.delete(saved)
        db.session.commit()
        flash(f"Deleted saved filter \u201c{saved.name}\u201d.", "success")
    return redirect(url_for("entries.index"))
