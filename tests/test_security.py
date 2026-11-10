"""Security fixes from the pre-cloud review."""
import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import User
from app.urls import safe_next

from .conftest import login, make_user


def fresh():
    from flask import g
    g.pop("_login_user", None)


def get(client, url):
    """GET as a separate request would see it. The tests share one app context,
    so drop Flask-Login's per-request user cache first."""
    from flask import g
    g.pop("_login_user", None)
    return client.get(url)


@pytest.mark.parametrize("target", [
    "https://evil.example/", "//evil.example/", "/\\evil.example", "\\\\evil.example",
    "/\tevil", "/\r\nSet-Cookie:x", "javascript:alert(1)", "evil.example", "",
])
def test_safe_next_rejects_offsite_and_tricky_targets(target):
    assert safe_next(target) is None


@pytest.mark.parametrize("target", ["/", "/entries/?q=energy&cluster=2", "/reports/recent"])
def test_safe_next_keeps_local_paths(target):
    assert safe_next(target) == target


def test_backslash_next_is_not_followed_after_login(app, client):
    make_user("pat@example.com", "correct-horse-1")
    resp = client.post("/login?next=/%5Cevil.example", data={"email": "pat@example.com", "password": "correct-horse-1"})
    assert resp.headers["Location"] == "/"


def test_deactivating_someone_signs_them_out_immediately(app, client):
    user = make_user("pat@example.com", "correct-horse-1")
    login(client, "pat@example.com", "correct-horse-1")
    assert get(client, "/").status_code == 200
    user.is_active_flag = False
    db.session.commit()
    assert get(client, "/").status_code == 302


def test_admin_deactivation_ends_sessions_and_remember_cookie(app, admin_client):
    other = app.test_client()
    make_user("pat@example.com", "correct-horse-1")
    fresh()
    other.post("/login", data={"email": "pat@example.com", "password": "correct-horse-1", "remember": "y"})
    assert get(other, "/").status_code == 200
    user = db.session.scalar(select(User).where(User.email == "pat@example.com"))
    fresh()
    admin_client.post(f"/admin/users/{user.id}", data={
        "email": user.email, "display_name": "Pat", "auth_provider": "local",
    })  # "is_active" unticked
    assert get(other, "/").status_code == 302
    # Re-activating doesn't revive the old session or "keep me signed in" cookie.
    user = db.session.get(User, user.id)
    user.is_active_flag = True
    db.session.commit()
    assert get(other, "/").status_code == 302


def test_password_reset_by_admin_signs_out_old_sessions(app, admin_client):
    other = app.test_client()
    user = make_user("pat@example.com", "correct-horse-1")
    fresh()
    login(other, "pat@example.com", "correct-horse-1")
    fresh()
    admin_client.post(f"/admin/users/{user.id}", data={
        "email": user.email, "display_name": "Pat", "auth_provider": "local", "is_active": "y",
        "password": "brand-new-temp-1",
    })
    assert get(other, "/").status_code == 302


def test_changing_own_password_keeps_this_browser_but_ends_others(app, client):
    make_user("pat@example.com", "correct-horse-1")
    elsewhere = app.test_client()
    login(elsewhere, "pat@example.com", "correct-horse-1")
    login(client, "pat@example.com", "correct-horse-1")
    resp = client.post("/account/password", data={
        "current_password": "correct-horse-1", "new_password": "even-better-horse-2", "confirm": "even-better-horse-2",
    })
    assert resp.status_code == 302
    assert get(client, "/").status_code == 200
    assert get(elsewhere, "/").status_code == 302


def test_old_style_session_ids_are_rejected(app, client):
    user = make_user("pat@example.com", "correct-horse-1")
    with client.session_transaction() as s:
        s["_user_id"] = str(user.id)       # no token, as issued before this change
        s["_fresh"] = True
    assert get(client, "/").status_code == 302


def test_security_headers(app, client):
    make_user("pat@example.com", "correct-horse-1")
    login(client, "pat@example.com", "correct-horse-1")
    resp = client.get("/")
    csp = resp.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Cache-Control"] == "no-store"
    assert "Strict-Transport-Security" not in resp.headers   # only on HTTPS setups
    app.config["SESSION_COOKIE_SECURE"] = True
    assert "max-age=31536000" in client.get("/login").headers["Strict-Transport-Security"]


def test_no_inline_scripts_in_pages(app, admin_client):
    for url in ["/", "/entries/", "/entries/new", "/reports/", "/reports/recent", "/admin/users", "/admin/groups"]:
        html = admin_client.get(url).data.decode()
        assert "<script>" not in html and " onsubmit=" not in html and " onchange=" not in html, url
