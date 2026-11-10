"""Administration: users, groups and the cluster / opportunity type lists."""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from ..extensions import db
from ..forms import ConfirmForm, GroupForm, LookupForm, UserForm
from ..models import Cluster, Group, OpportunityType, User, entry_clusters, entry_opportunity_types

bp = Blueprint("admin", __name__)

LOOKUPS = {
    "clusters": {"model": Cluster, "label": "Economic clusters", "singular": "cluster", "link": entry_clusters.c.cluster_id},
    "types": {"model": OpportunityType, "label": "Opportunity types", "singular": "opportunity type",
              "link": entry_opportunity_types.c.opportunity_type_id},
}


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _group_choices():
    return [(g.id, g.name) for g in db.session.scalars(select(Group).order_by(Group.name))]


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
    rows = db.session.scalars(select(User).order_by(User.display_name)).all()
    return render_template("admin/users.html", users=rows)


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
            form.password.errors.append("Set a temporary password, or choose Microsoft only.")
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
    form.groups.choices = _group_choices()
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
            if user.external_id and email != user.email:
                # A new email means a different person may sign in with Microsoft; relink on next sign-in.
                user.external_id = None
            user.email = email
            user.display_name = form.display_name.data.strip()
            user.auth_provider = form.auth_provider.data
            if user.auth_provider == "entra":
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
    return render_template("admin/user_form.html", form=form, user=user)


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


# --- Clusters and opportunity types ----------------------------------------

def _lookup(kind):
    return LOOKUPS.get(kind) or abort(404)


@bp.route("/lists/<kind>")
@admin_required
def lookup_list(kind):
    spec = _lookup(kind)
    model = spec["model"]
    usage = dict(
        db.session.execute(select(spec["link"], func.count()).group_by(spec["link"])).all()
    )
    rows = db.session.scalars(select(model).order_by(model.sort_order, model.name)).all()
    return render_template("admin/lookups.html", kind=kind, spec=spec, rows=rows, usage=usage)


@bp.route("/lists/<kind>/new", methods=["GET", "POST"])
@bp.route("/lists/<kind>/<int:item_id>", methods=["GET", "POST"])
@admin_required
def lookup_edit(kind, item_id=None):
    spec = _lookup(kind)
    model = spec["model"]
    item = (db.session.get(model, item_id) or abort(404)) if item_id else None
    form = LookupForm(obj=item)
    if item is not None and kind == "types" and not form.is_submitted():
        form.report_group.data = item.report_group or ""
    if form.validate_on_submit():
        name = form.name.data.strip()
        q = select(model).where(model.name == name)
        if item:
            q = q.where(model.id != item.id)
        if db.session.scalar(q):
            form.name.errors.append("That name is already on the list.")
        else:
            if item is None:
                item = model()
                db.session.add(item)
            item.name = name
            item.sort_order = form.sort_order.data or 0
            item.is_active = form.is_active.data
            if kind == "types":
                item.report_group = form.report_group.data or None
            db.session.commit()
            flash(f"Saved {item.name}.", "success")
            return redirect(url_for("admin.lookup_list", kind=kind))
    return render_template("admin/lookup_form.html", form=form, item=item, kind=kind, spec=spec)
