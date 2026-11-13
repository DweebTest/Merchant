"""Administration: users, groups and the lists people pick from (clusters,
opportunity types, priorities and follow-up statuses)."""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import delete as sql_delete, func, or_, select, update

from ..extensions import db
from ..forms import ConfirmForm, GroupForm, LookupForm, UserForm
from ..models import (Attachment, Cluster, Entry, FollowUpStatus, Group, OpportunityType, Priority, SavedFilter, User,
                      default_choice, entry_clusters, entry_opportunity_types)

bp = Blueprint("admin", __name__)

LOOKUPS = {
    "clusters": {"model": Cluster, "label": "Economic clusters", "singular": "cluster",
                 "link": entry_clusters.c.cluster_id,
                 "help": "Sectors an entry can be tagged with. An entry can have several."},
    "types": {"model": OpportunityType, "label": "Opportunity types", "singular": "opportunity type",
              "link": entry_opportunity_types.c.opportunity_type_id,
              "help": "Kinds of opportunity. Each can feed the funding or partnership report."},
    "priorities": {"model": Priority, "label": "Priorities", "singular": "priority",
                   "link": Entry.priority_id, "single": True,
                   "help": "How urgent an entry is. Reports list them in this order, most urgent first."},
    "statuses": {"model": FollowUpStatus, "label": "Follow-up statuses", "singular": "follow-up status",
                 "link": Entry.status_id, "single": True,
                 "help": "Where a follow-up stands. Anyone signed in can change an entry's status."},
}


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _group_choices(user=None):
    """Active groups, plus any inactive ones this person is already in."""
    keep = [g.id for g in user.groups] if user else []
    rows = db.session.scalars(select(Group).where(or_(Group.is_active.is_(True), Group.id.in_(keep or [-1])))
                              .order_by(Group.name))
    return [(g.id, g.name + ("" if g.is_active else " (inactive)")) for g in rows]


def _user_choices():
    return [
        (u.id, f"{u.display_name} ({u.email})")
        for u in db.session.scalars(select(User).order_by(User.display_name))
    ]


def _active_admin_count(excluding=None):
    q = select(func.count(User.id)).where(User.is_admin.is_(True), User.is_active_flag.is_(True))
    if excluding is not None:
        q = q.where(User.id != excluding.id)
    return db.session.scalar(q)


@bp.route("/")
@admin_required
def index():
    return redirect(url_for("admin.users"))


# --- Users ------------------------------------------------------------------

@bp.route("/users")
@admin_required
def users():
    show_all = request.args.get("show") == "all"
    q = select(User).order_by(User.display_name)
    if not show_all:
        q = q.where(User.is_active_flag.is_(True))
    rows = db.session.scalars(q).all()
    inactive = db.session.scalar(select(func.count(User.id)).where(User.is_active_flag.is_(False)))
    return render_template("admin/users.html", users=rows, show_all=show_all, inactive=inactive)


@bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def user_new():
    form = UserForm()
    form.groups.choices = _group_choices()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if db.session.scalar(select(User).where(User.email == email)):
            form.email.errors.append("Someone already has this email.")
        elif form.auth_provider.data == "local" and not form.password.data:
            form.password.errors.append("Set a temporary password, or choose single sign-on only.")
        else:
            user = User(
                email=email,
                display_name=form.display_name.data.strip(),
                auth_provider=form.auth_provider.data,
                is_admin=form.is_admin.data,
                is_active_flag=form.is_active.data,
                must_change_password=form.auth_provider.data == "local",
            )
            if form.auth_provider.data == "local":
                user.set_password(form.password.data)
            user.groups = [db.session.get(Group, gid) for gid in form.groups.data]
            db.session.add(user)
            db.session.commit()
            flash(f"Added {user.display_name}.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, user=None)


@bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    user = db.session.get(User, user_id) or abort(404)
    form = UserForm(obj=user)
    form.groups.choices = _group_choices(user)
    form.password.label.text = "Reset password (optional)"
    form.password.description = "Leave blank to keep their current password."
    if not form.is_submitted():
        form.is_active.data = user.is_active
        form.groups.data = [g.id for g in user.groups]

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        clash = db.session.scalar(select(User).where(User.email == email, User.id != user.id))
        losing_admin = user.is_admin and (not form.is_admin.data or not form.is_active.data)
        needs_password = form.auth_provider.data == "local" and not user.password_hash and not form.password.data
        if clash:
            form.email.errors.append("Someone already has this email.")
        elif losing_admin and _active_admin_count(excluding=user) == 0:
            flash("Keep at least one active administrator.", "error")
        elif needs_password:
            form.password.errors.append("Set a temporary password to switch this person to password sign-in.")
        else:
            if (email != user.email or form.auth_provider.data != user.auth_provider
                    or (user.is_active_flag and not form.is_active.data)):
                user.end_sessions()  # sign them out everywhere so the change takes effect now
            if email != user.email:
                # A new email means a different person may sign in; relink at their next single sign-on.
                user.external_id = None
                user.saml_name_id = None
            user.email = email
            user.display_name = form.display_name.data.strip()
            user.auth_provider = form.auth_provider.data
            if user.auth_provider != "local":
                user.password_hash = None
                user.must_change_password = False
            user.is_admin = form.is_admin.data
            user.is_active_flag = form.is_active.data
            user.groups = [db.session.get(Group, gid) for gid in form.groups.data]
            if form.password.data and user.auth_provider == "local":
                user.set_password(form.password.data)
                user.must_change_password = True
                user.failed_login_count = 0
                user.locked_until = None
            db.session.commit()
            flash(f"Saved {user.display_name}.", "success")
            return redirect(url_for("admin.users"))
    owned = db.session.scalar(select(func.count(Entry.id)).where(Entry.owner_id == user.id))
    open_owned = db.session.scalar(select(func.count(Entry.id)).where(
        Entry.owner_id == user.id, Entry.status.has(FollowUpStatus.is_open.is_(True))))
    others = db.session.scalars(select(User).where(User.is_active_flag.is_(True), User.id != user.id)
                                .order_by(func.lower(User.display_name))).all()
    return render_template("admin/user_form.html", form=form, user=user, owned=owned, open_owned=open_owned,
                           others=others, confirm_form=ConfirmForm(), is_self=user.id == current_user.id)


def _open_owned(user):
    return db.session.scalar(select(func.count(Entry.id)).where(
        Entry.owner_id == user.id, Entry.status.has(FollowUpStatus.is_open.is_(True))))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def user_delete(user_id):
    """Remove an account for good. Their name stays on the entries they added.
    Only allowed once everything they look after is marked done."""
    user = db.session.get(User, user_id) or abort(404)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    back = redirect(url_for("admin.user_edit", user_id=user.id))
    if user.id == current_user.id:
        flash("You can't delete your own account.", "error")
        return back
    if user.is_admin and user.is_active and _active_admin_count(excluding=user) == 0:
        flash("Keep at least one active administrator.", "error")
        return back
    open_count = _open_owned(user)
    if open_count:
        flash(f"{user.display_name} still looks after {open_count} open "
              f"{'follow-up' if open_count == 1 else 'follow-ups'}. Mark them done or hand them over first.", "error")
        return back
    name = user.display_name
    # Keep their name on what they added; let go of everything else.
    db.session.execute(update(Entry).where(Entry.created_by_id == user.id, Entry.created_by_name == "")
                       .values(created_by_name=name))
    db.session.execute(update(Entry).where(Entry.created_by_id == user.id).values(created_by_id=None))
    db.session.execute(update(Entry).where(Entry.owner_id == user.id).values(owner_id=None))
    db.session.execute(update(Attachment).where(Attachment.uploaded_by_id == user.id).values(uploaded_by_id=None))
    db.session.execute(sql_delete(SavedFilter).where(SavedFilter.user_id == user.id))
    user.groups = []
    db.session.delete(user)
    db.session.commit()
    flash(f"Deleted {name}. Entries they added still show their name.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/reassign", methods=["POST"])
@admin_required
def user_reassign(user_id):
    """Hand everything someone looks after to another person, e.g. when they leave."""
    user = db.session.get(User, user_id) or abort(404)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    try:
        target = db.session.get(User, int(request.form.get("owner", "")))
    except ValueError:
        target = None
    if target is None or not target.is_active or target.id == user.id:
        flash("Pick an active person to hand the entries to.", "error")
        return redirect(url_for("admin.user_edit", user_id=user.id))
    only_open = request.form.get("only_open") == "1"
    q = select(Entry).where(Entry.owner_id == user.id)
    if only_open:
        q = q.where(Entry.status.has(FollowUpStatus.is_open.is_(True)))
    moved = 0
    for entry in db.session.scalars(q):
        entry.owner_id = target.id
        moved += 1
    db.session.commit()
    flash(f"Moved {moved} {'entry' if moved == 1 else 'entries'} from {user.display_name} to {target.display_name}.",
          "success")
    return redirect(url_for("admin.user_edit", user_id=user.id))


# --- Groups -----------------------------------------------------------------

@bp.route("/groups")
@admin_required
def groups():
    rows = db.session.scalars(select(Group).order_by(Group.name)).all()
    return render_template("admin/groups.html", groups=rows, delete_form=ConfirmForm())


@bp.route("/groups/new", methods=["GET", "POST"])
@bp.route("/groups/<int:group_id>", methods=["GET", "POST"])
@admin_required
def group_edit(group_id=None):
    group = (db.session.get(Group, group_id) or abort(404)) if group_id else None
    form = GroupForm(obj=group)
    form.members.choices = _user_choices()
    if group and not form.is_submitted():
        form.members.data = [u.id for u in group.members]

    if form.validate_on_submit():
        name = form.name.data.strip()
        q = select(Group).where(Group.name == name)
        if group:
            q = q.where(Group.id != group.id)
        if db.session.scalar(q):
            form.name.errors.append("A group with this name already exists.")
        else:
            if group is None:
                group = Group()
                db.session.add(group)
            group.name = name
            group.description = (form.description.data or "").strip() or None
            group.members = [db.session.get(User, uid) for uid in form.members.data]
            group.is_active = form.is_active.data
            db.session.commit()
            flash(f"Saved group {group.name}.", "success")
            return redirect(url_for("admin.groups"))
    return render_template("admin/group_form.html", form=form, group=group)


@bp.route("/groups/<int:group_id>/delete", methods=["POST"])
@admin_required
def group_delete(group_id):
    group = db.session.get(Group, group_id) or abort(404)
    if ConfirmForm().validate_on_submit():
        db.session.delete(group)
        db.session.commit()
        flash(f"Deleted group {group.name}.", "success")
    return redirect(url_for("admin.groups"))


# --- Lists: clusters, opportunity types, priorities, statuses ----------------

def _lookup(kind):
    return LOOKUPS.get(kind) or abort(404)


def _usage(spec, open_only=False):
    """{value id: number of entries using it}, optionally only entries still open."""
    link = spec["link"]
    q = select(link, func.count()).group_by(link)
    if open_only:
        q = q.where(Entry.id == link.table.c.entry_id) if link.table is not Entry.__table__ else q
        q = q.where(Entry.status.has(FollowUpStatus.is_open.is_(True)))
    return dict(db.session.execute(q).all())


def _single_choice_problem(spec, item, active, default):
    """Priorities and statuses need one active default, since every entry has one.
    Returns a reason the change can't be made, or None."""
    if not spec.get("single") or item is None or item.id is None:
        return None
    model = spec["model"]
    others_active = db.session.scalar(
        select(func.count(model.id)).where(model.id != item.id, model.is_active.is_(True)))
    if not active and not others_active:
        return f"Keep at least one {spec['singular']} active."
    if item.is_default and not (active and default):
        return f"This is the default for new entries. Make another {spec['singular']} the default first."
    return None


@bp.route("/lists")
@admin_required
def lists():
    """One page for all the lists people pick from."""
    overview = []
    for kind, spec in LOOKUPS.items():
        model = spec["model"]
        rows = db.session.scalars(select(model).order_by(model.sort_order, model.name)).all()
        overview.append({"kind": kind, "spec": spec, "rows": rows,
                         "active": sum(r.is_active for r in rows)})
    return render_template("admin/lists.html", overview=overview)


@bp.route("/lists/<kind>")
@admin_required
def lookup_list(kind):
    spec = _lookup(kind)
    model = spec["model"]
    rows = db.session.scalars(select(model).order_by(model.sort_order, model.name)).all()
    return render_template("admin/lookups.html", kind=kind, spec=spec, rows=rows, usage=_usage(spec),
                           open_usage=_usage(spec, open_only=True), confirm_form=ConfirmForm())


@bp.route("/lists/<kind>/new", methods=["GET", "POST"])
@bp.route("/lists/<kind>/<int:item_id>", methods=["GET", "POST"])
@admin_required
def lookup_edit(kind, item_id=None):
    spec = _lookup(kind)
    model = spec["model"]
    item = (db.session.get(model, item_id) or abort(404)) if item_id else None
    form = LookupForm(obj=item)
    if item is None and not form.is_submitted():
        # New values go to the bottom of the list.
        form.sort_order.data = (db.session.scalar(select(func.max(model.sort_order))) or 0) + 10
        if kind == "statuses":
            form.is_open.data = True
    if item is not None and kind == "types" and not form.is_submitted():
        form.report_group.data = item.report_group or ""
    if form.validate_on_submit():
        name = " ".join(form.name.data.split())
        q = select(model).where(func.lower(model.name) == name.lower())
        if item:
            q = q.where(model.id != item.id)
        problem = _single_choice_problem(spec, item, form.is_active.data, form.is_default.data)
        if db.session.scalar(q):
            form.name.errors.append("That name is already on the list.")
        elif problem:
            flash(problem, "error")
        elif spec.get("single") and form.is_default.data and not form.is_active.data:
            form.is_default.errors.append("An inactive value can't be the default.")
        else:
            if item is None:
                item = model()
                db.session.add(item)
            item.name = name
            item.sort_order = form.sort_order.data or 0
            item.is_active = form.is_active.data
            if kind == "types":
                item.report_group = form.report_group.data or None
            if kind == "priorities":
                item.is_high = form.is_high.data
            if kind == "statuses":
                item.is_open = form.is_open.data
                item.colour = form.colour.data if form.colour.data in FollowUpStatus.COLOURS else "grey"
            if spec.get("single"):
                if form.is_default.data:
                    db.session.flush()
                    db.session.execute(model.__table__.update().where(model.id != item.id).values(is_default=False))
                item.is_default = form.is_default.data
            db.session.commit()
            flash(f"Saved {item.name}.", "success")
            return redirect(url_for("admin.lookup_list", kind=kind))
    used = _usage(spec).get(item.id, 0) if item else 0
    open_used = _usage(spec, open_only=True).get(item.id, 0) if item else 0
    return render_template("admin/lookup_form.html", form=form, item=item, kind=kind, spec=spec, used=used,
                           open_used=open_used, confirm_form=ConfirmForm())


@bp.route("/lists/<kind>/<int:item_id>/delete", methods=["POST"])
@admin_required
def lookup_delete(kind, item_id):
    """Delete a value for good, once every entry using it is marked done.

    Clusters and opportunity types are taken off those entries. Entries with a
    deleted priority move to the default priority; entries with a deleted
    (closed) status move to another closed status."""
    spec = _lookup(kind)
    model = spec["model"]
    item = db.session.get(model, item_id) or abort(404)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    back = redirect(url_for("admin.lookup_edit", kind=kind, item_id=item.id))
    used = _usage(spec).get(item.id, 0)
    open_used = _usage(spec, open_only=True).get(item.id, 0)
    if open_used:
        flash(f"{open_used} {'entry' if open_used == 1 else 'entries'} using {item.name} still "
              f"{'has an open follow-up' if open_used == 1 else 'have open follow-ups'}. Mark them done first, "
              "or untick Active to retire it instead.", "error")
        return back
    problem = _single_choice_problem(spec, item, active=False, default=False)
    if problem:
        flash(problem, "error")
        return back

    moved_to = None
    if used and kind in ("clusters", "types"):
        link = spec["link"]
        db.session.execute(sql_delete(link.table).where(link == item.id))
    elif used and kind == "priorities":
        moved_to = default_choice(Priority)
        db.session.execute(update(Entry).where(Entry.priority_id == item.id).values(priority_id=moved_to.id))
    elif used and kind == "statuses":
        moved_to = db.session.scalar(
            select(FollowUpStatus).where(FollowUpStatus.id != item.id, FollowUpStatus.is_open.is_(False))
            .order_by(FollowUpStatus.is_active.desc(), FollowUpStatus.sort_order).limit(1))
        if moved_to is None:
            flash("Add another status that doesn't count as open first, so these entries have somewhere to go.",
                  "error")
            return back
        db.session.execute(update(Entry).where(Entry.status_id == item.id).values(status_id=moved_to.id))
    name = item.name
    db.session.delete(item)
    db.session.commit()
    if not used:
        flash(f"Deleted {name}.", "success")
    elif moved_to is not None:
        flash(f"Deleted {name}. Its {used} {'entry' if used == 1 else 'entries'} now show {moved_to.name}.", "success")
    else:
        flash(f"Deleted {name} and took it off {used} finished {'entry' if used == 1 else 'entries'}.", "success")
    return redirect(url_for("admin.lookup_list", kind=kind))
