"""Space-age and classic looks."""
from .conftest import login, make_user


def test_space_age_is_the_default(app, client):
    make_user("pat@example.com", "correct-horse-1")
    login(client, "pat@example.com", "correct-horse-1")
    page = client.get("/").data
    assert b"css/spaceage.css" in page and b"sa-frame" in page and b"Classic look" in page


def test_switch_to_classic_and_back(app, client):
    make_user("pat@example.com", "correct-horse-1")
    login(client, "pat@example.com", "correct-horse-1")
    resp = client.get("/theme/classic?next=/entries/")
    assert resp.status_code == 302 and resp.headers["Location"] == "/entries/"
    page = client.get("/").data
    assert b"spaceage.css" not in page and b'class="topbar"' in page and b"Space-age look" in page
    client.get("/theme/spaceage")
    assert b"spaceage.css" in client.get("/").data


def test_unknown_theme_and_offsite_next_ignored(app, client):
    resp = client.get("/theme/neon?next=https://evil.example/")
    assert resp.headers["Location"] == "/"
    assert b"spaceage.css" in client.get("/login").data


def test_site_default_can_be_classic(app, client):
    app.config["DEFAULT_THEME"] = "classic"
    assert b"spaceage.css" not in client.get("/login").data


def test_current_page_marked_in_menu(app, client):
    make_user("pat@example.com", "correct-horse-1")
    login(client, "pat@example.com", "correct-horse-1")
    page = client.get("/reports/").data.decode()
    assert 'class="sa-pill active" aria-current="page">Reports' in page
