"""Sign in with Microsoft (Entra ID) using MSAL's authorization code flow.

Only people an administrator has already added can sign in. The first time a
person signs in, their Microsoft account is matched to their Merchant account by
email and then linked by its permanent Entra object id, so a later email
change in Entra doesn't lock them out.
"""
import re
from urllib.parse import urlsplit

import msal
from flask import current_app, flash, redirect, request, session, url_for
from flask_login import login_user
from sqlalchemy import func, select

from ..extensions import db
from ..models import User, utcnow

GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
FLOW_KEY = "entra_flow"
NEXT_KEY = "entra_next"


def entra_enabled(app=None):
    cfg = (app or current_app).config
    return bool(cfg.get("ENTRA_TENANT_ID") and cfg.get("ENTRA_CLIENT_ID") and cfg.get("ENTRA_CLIENT_SECRET"))


def _client():
    cfg = current_app.config
    return msal.ConfidentialClientApplication(
        cfg["ENTRA_CLIENT_ID"],
        authority=f"{cfg['ENTRA_AUTHORITY_HOST']}/{cfg['ENTRA_TENANT_ID']}",
        client_credential=cfg["ENTRA_CLIENT_SECRET"],
    )


def _redirect_uri():
    return current_app.config["ENTRA_REDIRECT_URI"] or url_for("auth.microsoft_callback", _external=True)


def _safe_next(target):
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def start_login():
    """Send the browser to Microsoft's sign-in page."""
    flow = _client().initiate_auth_code_flow(
        scopes=[], redirect_uri=_redirect_uri(), prompt="select_account",
    )
    session[FLOW_KEY] = flow
    session[NEXT_KEY] = _safe_next(request.args.get("next"))
    return redirect(flow["auth_uri"])


def _fail(message, log_detail=None):
    if log_detail:
        current_app.logger.warning("Microsoft sign-in failed: %s", log_detail)
    flash(message, "error")
    return redirect(url_for("auth.login"))


def finish_login():
    """Handle Microsoft's redirect back: check the response and sign the person in."""
    flow = session.pop(FLOW_KEY, None)
    next_url = session.pop(NEXT_KEY, None)
    if not flow:
        return _fail("Your Microsoft sign-in expired. Please try again.")

    try:
        result = _client().acquire_token_by_auth_code_flow(flow, request.args.to_dict())
    except ValueError as exc:  # state mismatch, i.e. a forged or replayed response
        return _fail("Microsoft sign-in couldn't be verified. Please try again.", repr(exc))

    if "error" in result:
        detail = f"{result.get('error')}: {result.get('error_description', '')[:300]}"
        if result.get("error") == "access_denied":
            return _fail("Microsoft sign-in was cancelled.", detail)
        return _fail("Microsoft sign-in didn't work. Please try again or contact an administrator.", detail)

    claims = result.get("id_token_claims") or {}
    tenant = current_app.config["ENTRA_TENANT_ID"]
    if GUID.match(tenant) and claims.get("tid", "").lower() != tenant.lower():
        return _fail("That Microsoft account isn't from your organization.", f"unexpected tid {claims.get('tid')}")

    oid = claims.get("oid")
    email = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if not oid:
        return _fail("Microsoft didn't return an account id. Contact an administrator.", "missing oid")

    user = db.session.scalar(select(User).where(User.external_id == oid))
    if user is None and email:
        user = db.session.scalar(select(User).where(func.lower(User.email) == email))
        if user is not None and user.external_id and user.external_id != oid:
            # The email now belongs to a different Microsoft account. Don't let it take over.
            return _fail(
                "This email is linked to a different Microsoft account. Ask an administrator to reset it.",
                f"oid mismatch for {email}",
            )

    if user is None or not user.is_active:
        shown = email or "your account"
        return _fail(f"{shown} isn't set up in Merchant yet. Ask an administrator to add you.",
                     f"no active user for {email or oid}")

    user.external_id = oid
    user.last_login_at = utcnow()
    user.failed_login_count = 0
    user.locked_until = None
    db.session.commit()
    login_user(user)
    session["auth_method"] = "microsoft"
    return redirect(next_url or url_for("main.index"))

