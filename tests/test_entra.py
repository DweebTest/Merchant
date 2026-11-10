"""Microsoft sign-in, tested against a fake MSAL client (no network)."""
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from app.auth import entra
from app.extensions import db
from app.models import User

from .conftest import login, make_user

TENANT = "11111111-2222-3333-4444-555555555555"
OTHER_TENANT = "99999999-2222-3333-4444-555555555555"


class FakeMsal:
    """Stands in for msal.ConfidentialClientApplication."""
    result = {}
    last_init = {}

    def __init__(self, client_id, authority, client_credential):
        FakeMsal.last_init = {"client_id": client_id, "authority": authority, "secret": client_credential}

    def initiate_auth_code_flow(self, scopes, redirect_uri, prompt=None):
        return {"state": "abc", "nonce": "n", "redirect_uri": redirect_uri,
                "auth_uri": f"https://login.example/authorize?state=abc&redirect_uri={redirect_uri}"}

    def acquire_token_by_auth_code_flow(self, flow, args):
        if args.get("state") != flow["state"]:
            raise ValueError("state mismatch")
        return FakeMsal.result


@pytest.fixture()
def entra_app(app, monkeypatch):
    app.config.update(ENTRA_TENANT_ID=TENANT, ENTRA_CLIENT_ID="client-id", ENTRA_CLIENT_SECRET="secret")
    monkeypatch.setattr(entra.msal, "ConfidentialClientApplication", FakeMsal)
    FakeMsal.result = {}
    return app


def claims(oid="oid-1", email="pat@college.example", tid=TENANT, **extra):
    return {"id_token_claims": {"oid": oid, "tid": tid, "preferred_username": email, **extra}}


def sign_in(client, result, state="abc", next_url=None):
    FakeMsal.result = result
    start = client.get("/login/microsoft" + (f"?next={next_url}" if next_url else ""))
    assert start.status_code == 302 and start.headers["Location"].startswith("https://login.example/")
    return client.get(f"/login/microsoft/callback?code=xyz&state={state}")


def test_button_only_when_configured(app, client):
    assert b"Sign in with Microsoft" not in client.get("/login").data
    assert client.get("/login/microsoft").status_code == 404
    app.config.update(ENTRA_TENANT_ID=TENANT, ENTRA_CLIENT_ID="c", ENTRA_CLIENT_SECRET="s")
    assert b"Sign in with Microsoft" in client.get("/login").data


def test_redirect_uri_and_authority(entra_app, client):
    client.get("/login/microsoft")
    assert FakeMsal.last_init["authority"] == f"https://login.microsoftonline.com/{TENANT}"
    with client.session_transaction() as s:
        assert s["entra_flow"]["redirect_uri"] == "http://localhost/login/microsoft/callback"


def test_admin_added_user_signs_in_and_is_linked(entra_app, client):
    make_user("pat@college.example", "unused-password-1", auth_provider="entra").password_hash = None
    db.session.commit()
    resp = sign_in(client, claims(), next_url="/reports/")
    assert resp.status_code == 302 and resp.headers["Location"] == "/reports/"
    assert client.get("/").status_code == 200
    user = db.session.scalar(select(User))
    assert user.external_id == "oid-1" and user.last_login_at


def test_unknown_person_is_refused(entra_app, client):
    resp = sign_in(client, claims(email="stranger@college.example"))
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")
    page = client.get("/login").data
    assert b"stranger@college.example isn&#39;t set up in Merchant" in page
    assert client.get("/").status_code == 302
    assert db.session.query(User).count() == 0   # no automatic accounts


def test_inactive_user_refused(entra_app, client):
    make_user("pat@college.example", "x-password-123", is_active_flag=False)
    sign_in(client, claims())
    assert client.get("/").status_code == 302


def test_wrong_tenant_refused(entra_app, client):
    make_user("pat@college.example", "x-password-123")
    sign_in(client, claims(tid=OTHER_TENANT))
    assert client.get("/").status_code == 302


def test_forged_state_refused(entra_app, client):
    make_user("pat@college.example", "x-password-123")
    sign_in(client, claims(), state="forged")
    assert client.get("/").status_code == 302
    assert b"couldn&#39;t be verified" in client.get("/login").data


def test_callback_without_flow_refused(entra_app, client):
    resp = client.get("/login/microsoft/callback?code=x&state=abc")
    assert resp.status_code == 302 and client.get("/").status_code == 302


def test_microsoft_error_shown(entra_app, client):
    sign_in(client, {"error": "access_denied", "error_description": "User cancelled"})
    assert b"cancelled" in client.get("/login").data


def test_linked_account_matched_by_object_id_after_email_change(entra_app, client):
    make_user("pat@college.example", "x-password-123", external_id="oid-1")
    sign_in(client, claims(email="patricia@college.example"))
    assert client.get("/").status_code == 200


def test_email_taken_over_by_different_account_refused(entra_app, client):
    make_user("pat@college.example", "x-password-123", external_id="oid-original")
    sign_in(client, claims(oid="oid-someone-else"))
    assert client.get("/").status_code == 302
    assert b"different Microsoft account" in client.get("/login").data


def test_microsoft_sign_in_skips_forced_password_change(entra_app, client):
    make_user("pat@college.example", "temp-password-1", must_change_password=True)
    sign_in(client, claims())
    assert client.get("/").status_code == 200


def test_open_redirect_blocked(entra_app, client):
    make_user("pat@college.example", "x-password-123")
    resp = sign_in(client, claims(), next_url="https://evil.example/")
    assert resp.headers["Location"] == "/"


def test_local_login_can_be_turned_off(entra_app, client):
    make_user("pat@college.example", "x-password-123")
    entra_app.config["LOCAL_LOGIN_ENABLED"] = False
    page = client.get("/login").data
    assert b"Sign in with Microsoft" in page and b'name="password"' not in page
    assert login(client, "pat@college.example", "x-password-123").status_code == 404


def test_microsoft_only_user_cannot_use_password(entra_app, client):
    make_user("pat@college.example", "x-password-123", auth_provider="entra")
    assert login(client, "pat@college.example", "x-password-123").status_code == 401


def test_admin_creates_microsoft_only_user(admin_client, app):
    resp = admin_client.post("/admin/users/new", data={
        "email": "new@college.example", "display_name": "New", "auth_provider": "entra", "is_active": "y",
    })
    assert resp.status_code == 302
    user = db.session.scalar(select(User).where(User.email == "new@college.example"))
    assert user.auth_provider == "entra" and user.password_hash is None and not user.must_change_password


def test_switching_to_password_needs_one(admin_client, app):
    user = make_user("ms@college.example", "x-password-123", auth_provider="entra")
    user.password_hash = None
    db.session.commit()
    resp = admin_client.post(f"/admin/users/{user.id}", data={
        "email": user.email, "display_name": "MS", "auth_provider": "local", "is_active": "y",
    })
    assert resp.status_code == 200 and b"temporary password" in resp.data


def test_changing_email_unlinks_microsoft(admin_client, app):
    user = make_user("old@college.example", "x-password-123", external_id="oid-9")
    admin_client.post(f"/admin/users/{user.id}", data={
        "email": "new@college.example", "display_name": "Person", "auth_provider": "local", "is_active": "y",
    })
    db.session.refresh(user)
    assert user.email == "new@college.example" and user.external_id is None


def test_proxy_fix_uses_forwarded_https(app):
    from app import create_app
    from app.config import TestConfig

    class Cfg(TestConfig):
        TRUSTED_PROXIES = 1
        ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET = TENANT, "c", "s"
        UPLOAD_FOLDER = app.config["UPLOAD_FOLDER"]

    proxied = create_app(Cfg)
    client = proxied.test_client()
    import app.auth.entra as e
    original = e.msal.ConfidentialClientApplication
    e.msal.ConfidentialClientApplication = FakeMsal
    try:
        resp = client.get("/login/microsoft", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.college.example"})
    finally:
        e.msal.ConfidentialClientApplication = original
    redirect_uri = parse_qs(urlsplit(resp.headers["Location"]).query)["redirect_uri"][0]
    assert redirect_uri == "https://crm.college.example/login/microsoft/callback"
