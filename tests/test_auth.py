from app.extensions import db
from app.models import User

from .conftest import login, make_user


def test_pages_require_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_success_and_logout(client, app):
    make_user()
    resp = login(client, "user@example.com", "correct-horse-1")
    assert resp.status_code == 302
    assert client.get("/").status_code == 200
    client.post("/logout")
    assert client.get("/").status_code == 302


def test_email_is_case_insensitive(client, app):
    make_user()
    assert login(client, "USER@Example.com", "correct-horse-1").status_code == 302


def test_wrong_password_rejected(client, app):
    make_user()
    resp = login(client, "user@example.com", "nope")
    assert resp.status_code == 401
    assert b"don&#39;t match" in resp.data


def test_inactive_user_cannot_sign_in(client, app):
    make_user(is_active_flag=False)
    assert login(client, "user@example.com", "correct-horse-1").status_code == 401


def test_lockout_after_repeated_failures(client, app):
    make_user()
    for _ in range(app.config["MAX_FAILED_LOGINS"]):
        login(client, "user@example.com", "wrong")
    # Even the right password is refused while locked.
    assert login(client, "user@example.com", "correct-horse-1").status_code == 429


def test_open_redirect_blocked(client, app):
    make_user()
    resp = client.post(
        "/login?next=https://evil.example/",
        data={"email": "user@example.com", "password": "correct-horse-1"},
    )
    assert resp.headers["Location"] == "/"


def test_temporary_password_forces_change(client, app):
    make_user(must_change_password=True)
    login(client, "user@example.com", "correct-horse-1")
    resp = client.get("/")
    assert resp.status_code == 302 and "/account/password" in resp.headers["Location"]

    resp = client.post(
        "/account/password",
        data={"current_password": "correct-horse-1", "new_password": "brand-new-pass-2", "confirm": "brand-new-pass-2"},
    )
    assert resp.status_code == 302
    assert client.get("/").status_code == 200
    user = db.session.query(User).filter_by(email="user@example.com").one()
    assert user.check_password("brand-new-pass-2")
    assert not user.must_change_password


def test_contributor_cannot_open_admin(client, app):
    make_user()
    login(client, "user@example.com", "correct-horse-1")
    assert client.get("/admin/users").status_code == 403


def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}
