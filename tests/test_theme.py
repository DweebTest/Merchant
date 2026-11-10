"""Looks: built-in Orbit and Classic, plus personal themes from themes-local."""
from .conftest import login, make_user


def signed_in(client):
    make_user("pat@example.com", "correct-horse-1")
    login(client, "pat@example.com", "correct-horse-1")


def test_orbit_is_the_default(app, client):
    signed_in(client)
    page = client.get("/").data
    assert b"css/themes/orbit.css" in page and b'class="theme-orbit"' in page
    assert b">Orbit<" in page and b">Classic<" in page


def test_switch_to_classic_and_back(app, client):
    signed_in(client)
    resp = client.get("/theme/classic?next=/entries/")
    assert resp.status_code == 302 and resp.headers["Location"] == "/entries/"
    page = client.get("/").data
    assert b"orbit.css" not in page and b'class="theme-classic"' in page
    client.get("/theme/orbit")
    assert b"orbit.css" in client.get("/").data


def test_unknown_theme_and_offsite_next_ignored(app, client):
    resp = client.get("/theme/neon?next=https://evil.example/")
    assert resp.headers["Location"] == "/" and "theme=" not in resp.headers.get("Set-Cookie", "")
    assert b"orbit.css" in client.get("/login").data


def test_site_default_can_be_classic(app, client):
    app.config["DEFAULT_THEME"] = "classic"
    assert b"orbit.css" not in client.get("/login").data


def test_personal_theme_from_local_folder(app, client, tmp_path):
    (tmp_path / "themes-local").mkdir()
    (tmp_path / "themes-local" / "my-theme.css").write_text("body{}")
    (tmp_path / "themes-local" / "bad name!.css").write_text("body{}")
    app.static_folder = str(tmp_path)
    signed_in(client)
    page = client.get("/").data
    assert b">My Theme<" in page and b"bad name" not in page
    client.get("/theme/my-theme")
    page = client.get("/").data
    assert b"themes-local/my-theme.css" in page and b'class="theme-my-theme"' in page


def test_current_page_marked_in_menu(app, client):
    signed_in(client)
    page = client.get("/reports/").data.decode()
    assert 'class="active" aria-current="page">Reports' in page
