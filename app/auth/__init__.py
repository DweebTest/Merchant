from datetime import timedelta
from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from ..extensions import db
from ..forms import ChangePasswordForm, LoginForm
from ..models import User, utcnow

bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only follow ?next= links that stay on this site."""
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if not current_app.config["LOCAL_LOGIN_ENABLED"]:
        abort(404)

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(select(User).where(User.email == email))
        generic_error = "That email and password don't match an active account."

        if user is None or not user.is_active or user.auth_provider != "local":
            flash(generic_error, "error")
            return render_template("auth/login.html", form=form), 401

        if user.is_locked():
            flash("Too many failed attempts. Try again in a few minutes.", "error")
            return render_template("auth/login.html", form=form), 429

        if not user.check_password(form.password.data):
            user.failed_login_count += 1
            if user.failed_login_count >= current_app.config["MAX_FAILED_LOGINS"]:
                user.locked_until = utcnow() + timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])
                user.failed_login_count = 0
            db.session.commit()
            flash(generic_error, "error")
            return render_template("auth/login.html", form=form), 401

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = utcnow()
        db.session.commit()
        login_user(user, remember=form.remember.data)
        return redirect(_safe_next(request.args.get("next")) or url_for("main.index"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You're signed out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if current_user.auth_provider != "local":
        abort(404)
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append("That isn't your current password.")
        elif form.new_password.data == form.current_password.data:
            form.new_password.errors.append("Choose a password you haven't just used.")
        else:
            current_user.set_password(form.new_password.data)
            current_user.must_change_password = False
            db.session.commit()
            flash("Password changed.", "success")
            return redirect(url_for("main.index"))
    return render_template("auth/change_password.html", form=form)
