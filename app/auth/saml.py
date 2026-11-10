"""Single sign-on with SAML 2.0, for AWS IAM Identity Center or any SAML
identity provider (Okta, Google Workspace, Entra ID, ADFS...).

Same rule as Microsoft sign-in: only people an administrator has already added
can get in. The first SAML sign-in matches the person by email; after that
Merchant remembers the identity provider's NameID for them.

Only sign-ins that start at Merchant are accepted (no unsolicited responses).
The request id travels in a signed, short-lived RelayState rather than the
session, because the identity provider posts back cross-site and browsers
don't send the SameSite=Lax session cookie on that POST.
"""
from pathlib import Path
from urllib.parse import urlsplit

from flask import current_app, flash, redirect, request, session, url_for
from flask_login import login_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select

from ..extensions import db
from ..models import User, utcnow

RELAY_MAX_AGE = 10 * 60   # seconds a person has to finish signing in
EMAIL_ATTRS = ("email", "Email", "mail",
               "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress")
NAME_ATTRS = ("name", "displayName", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")


def saml_enabled(app=None):
    cfg = (app or current_app).config
    return bool(cfg.get("SAML_IDP_METADATA_URL") or cfg.get("SAML_IDP_METADATA_FILE"))


# --- Settings -----------------------------------------------------------------

def _idp_settings():
    """Parse the identity provider's metadata once and keep it."""
    cache = current_app.extensions.setdefault("merchant_saml", {})
    if "idp" not in cache:
        from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser as Parser

        cfg = current_app.config
        if cfg.get("SAML_IDP_METADATA_FILE"):
            xml = Path(cfg["SAML_IDP_METADATA_FILE"]).read_text(encoding="utf-8")
            cache["idp"] = Parser.parse(xml)
        else:
            cache["idp"] = Parser.parse_remote(cfg["SAML_IDP_METADATA_URL"], timeout=10)
    return cache["idp"]


def _base_url():
    return current_app.config.get("SAML_SP_BASE_URL") or request.host_url.rstrip("/")


def sp_entity_id():
    return f"{_base_url()}/saml/metadata"


def acs_url():
    return f"{_base_url()}/login/saml/acs"


def _settings(include_idp=True):
    from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser as Parser
    from onelogin.saml2.settings import OneLogin_Saml2_Settings

    data = {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": sp_entity_id(),
            "assertionConsumerService": {
                "url": acs_url(),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified",
        },
        "security": {
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "requestedAuthnContext": False,
            "rejectDeprecatedAlgorithm": True,
        },
    }
    if include_idp:
        data = Parser.merge_settings(data, _idp_settings())
    return OneLogin_Saml2_Settings(data, sp_validation_only=not include_idp)


def _request_data():
    parts = urlsplit(_base_url())
    https = parts.scheme == "https"
    return {
        "https": "on" if https else "off",
        "http_host": parts.hostname,
        "server_port": parts.port or (443 if https else 80),
        "script_name": request.path,
        "get_data": request.args.copy(),
        "post_data": request.form.copy(),
    }


def _auth():
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    return OneLogin_Saml2_Auth(_request_data(), old_settings=_settings())


def _relay_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="merchant-saml-relay")


def _safe_next(target):
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


# --- Views --------------------------------------------------------------------

def metadata():
    """Merchant's SAML details, for the identity provider's setup screen."""
    settings = _settings(include_idp=False)
    xml = settings.get_sp_metadata()
    errors = settings.validate_metadata(xml)
    if errors:
        current_app.logger.error("SAML metadata problems: %s", errors)
    return current_app.response_class(xml, mimetype="application/samlmetadata+xml")


def start_login():
    """Send the browser to the identity provider."""
    try:
        auth = _auth()
    except Exception as exc:  # bad or unreachable metadata
        return _fail("Single sign-on isn't working right now. Contact an administrator.", repr(exc))
    # Build the request first so we know its id, then sign that id into RelayState.
    from onelogin.saml2.authn_request import OneLogin_Saml2_Authn_Request
    from onelogin.saml2.utils import OneLogin_Saml2_Utils

    authn = OneLogin_Saml2_Authn_Request(auth.get_settings())
    relay = _relay_serializer().dumps({"rid": authn.get_id(), "next": _safe_next(request.args.get("next"))})
    params = {"SAMLRequest": authn.get_request(), "RelayState": relay}
    return redirect(OneLogin_Saml2_Utils.redirect(auth.get_sso_url(), params, True))


def _fail(message, log_detail=None):
    if log_detail:
        current_app.logger.warning("SAML sign-in failed: %s", log_detail)
    flash(message, "error")
    return redirect(url_for("auth.login"))


def _first(attrs, names):
    for name in names:
        values = attrs.get(name)
        if values:
            return str(values[0]).strip()
    return ""


def finish_login():
    """Handle the identity provider's POST back (the Assertion Consumer Service)."""
    try:
        relay = _relay_serializer().loads(request.form.get("RelayState", ""), max_age=RELAY_MAX_AGE)
    except SignatureExpired:
        return _fail("Your sign-in took too long. Please try again.")
    except BadSignature:
        return _fail("Please start single sign-on from Merchant's sign-in page.", "missing or forged RelayState")

    try:
        auth = _auth()
        auth.process_response(request_id=relay.get("rid"))
    except Exception as exc:
        return _fail("Single sign-on couldn't be verified. Please try again.", repr(exc))

    errors = auth.get_errors()
    if errors or not auth.is_authenticated():
        return _fail("Single sign-on couldn't be verified. Please try again.",
                     f"{errors} {auth.get_last_error_reason()}")

    name_id = (auth.get_nameid() or "").strip()
    attrs = auth.get_attributes()
    email = (_first(attrs, EMAIL_ATTRS) or (name_id if "@" in name_id else "")).lower()
    if not name_id:
        return _fail("The sign-in didn't include an account id. Contact an administrator.", "missing NameID")

    user = db.session.scalar(select(User).where(User.saml_name_id == name_id))
    if user is None and email:
        user = db.session.scalar(select(User).where(func.lower(User.email) == email))
        if user is not None and user.saml_name_id and user.saml_name_id != name_id:
            return _fail(
                "This email is linked to a different single sign-on account. Ask an administrator to reset it.",
                f"NameID mismatch for {email}",
            )

    if user is None or not user.is_active:
        shown = email or "Your account"
        return _fail(f"{shown} isn't set up in Merchant yet. Ask an administrator to add you.",
                     f"no active user for {email or name_id}")

    user.saml_name_id = name_id
    user.last_login_at = utcnow()
    user.failed_login_count = 0
    user.locked_until = None
    db.session.commit()
    login_user(user)
    session["auth_method"] = "saml"
    return redirect(relay.get("next") or url_for("main.index"))
