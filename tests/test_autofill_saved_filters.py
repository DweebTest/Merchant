from sqlalchemy import select

from app.extensions import db
from app.models import Cluster, OpportunityType, SavedFilter

from .conftest import login, make_user
from .test_entries import add_entry, ids


# --- Organization auto-fill -------------------------------------------------

def test_org_defaults_from_latest_entry(admin_client, app):
    add_entry(admin_client, entry_date="2026-09-01", organization="Acme", clusters=ids(Cluster, "Energy"),
              contact_name="Old Contact")
    add_entry(admin_client, entry_date="2026-10-01", organization="Acme",
              clusters=ids(Cluster, "Trades", "Technology"),
              opportunity_types=ids(OpportunityType, "Grant opportunity"),
              contact_name="Pat Lee", contact_email="pat@acme.example", college_area="Business",
              link_url="https://acme.example")
    # An older entry date added later must not win.
    add_entry(admin_client, entry_date="2026-08-01", organization="Acme", clusters=ids(Cluster, "Tourism"))

    data = admin_client.get("/entries/org-defaults?name=  acme ").get_json()
    assert data["found"] and data["has_entry"] and data["organization"] == "Acme"
    assert sorted(data["clusters"]) == sorted(int(i) for i in ids(Cluster, "Trades", "Technology"))
    assert data["opportunity_types"] == [int(i) for i in ids(OpportunityType, "Grant opportunity")]
    assert data["contact"] == {"name": "Pat Lee", "title": "", "email": "pat@acme.example", "phone": ""}
    assert data["college_area"] == "Business" and data["link_url"] == "https://acme.example"
    assert data["last_entry_label"] == "Oct 1, 2026"


def test_org_defaults_unknown_and_blank(admin_client):
    assert admin_client.get("/entries/org-defaults?name=Nobody").get_json() == {"found": False}
    assert admin_client.get("/entries/org-defaults").get_json() == {"found": False}


def test_org_defaults_skips_retired_values(admin_client, app):
    add_entry(admin_client, organization="Acme", clusters=ids(Cluster, "Energy", "Trades"))
    energy = db.session.scalar(select(Cluster).where(Cluster.name == "Energy"))
    energy.is_active = False
    db.session.commit()
    data = admin_client.get("/entries/org-defaults?name=Acme").get_json()
    assert data["clusters"] == [int(i) for i in ids(Cluster, "Trades")]


def test_org_defaults_requires_login(client):
    assert client.get("/entries/org-defaults?name=Acme").status_code == 302


def test_new_form_has_autofill_hooks_edit_form_does_not(admin_client, app):
    new = admin_client.get("/entries/new").data
    assert b"data-prefill-url" in new and b"entry-form.js" in new and b'class="lockable"' in new
    add_entry(admin_client)
    edit = admin_client.get("/entries/1/edit").data
    assert b"data-prefill-url" not in edit and b"entry-form.js" not in edit


# --- Saved filters ----------------------------------------------------------

def save(client, name, query, shared=False):
    data = {"name": name, "query": query}
    if shared:
        data["shared"] = "1"
    return client.post("/entries/saved-filters", data=data)


def test_save_and_list_filter(admin_client, app):
    energy = ids(Cluster, "Energy")[0]
    resp = save(admin_client, "Open energy", f"cluster={energy}&status=open&page=3&evil=1")
    assert resp.status_code == 302
    saved = db.session.scalars(select(SavedFilter)).one()
    assert saved.query == f"cluster={energy}&status=open"   # page and unknown keys dropped
    page = admin_client.get("/entries/").data
    assert b"Open energy" in page


def test_same_name_updates(admin_client, app):
    save(admin_client, "Mine", "status=open")
    save(admin_client, "mine", "status=done", shared=True)
    rows = db.session.scalars(select(SavedFilter)).all()
    assert len(rows) == 1 and rows[0].query == "status=done" and rows[0].is_shared


def test_empty_name_or_query_rejected(admin_client, app):
    save(admin_client, "", "status=open")
    save(admin_client, "Nothing", "page=2")
    assert db.session.query(SavedFilter).count() == 0


def test_private_vs_shared_visibility(client, app):
    make_user("a@example.com", "password-aaaa-1")
    make_user("b@example.com", "password-bbbb-1")
    login(client, "a@example.com", "password-aaaa-1")
    save(client, "A private", "status=open")
    save(client, "A shared", "status=done", shared=True)
    client.post("/logout")

    login(client, "b@example.com", "password-bbbb-1")
    page = client.get("/entries/").data
    assert b"A shared" in page and b"A private" not in page
    shared = db.session.scalar(select(SavedFilter).where(SavedFilter.name == "A shared"))
    # B can use it but not delete it.
    assert client.post(f"/entries/saved-filters/{shared.id}/delete").status_code == 403


def test_owner_deletes(admin_client, app):
    save(admin_client, "Temp", "status=open")
    f = db.session.scalars(select(SavedFilter)).one()
    admin_client.post(f"/entries/saved-filters/{f.id}/delete")
    assert db.session.query(SavedFilter).count() == 0


def test_save_form_only_when_filtered(admin_client):
    assert b"Save this filter" not in admin_client.get("/entries/").data
    assert b"Save this filter" in admin_client.get(f"/entries/?status={_open_id()}").data


def _open_id():
    from app.models import FollowUpStatus
    return db.session.scalar(select(FollowUpStatus.id).where(FollowUpStatus.name == "Open"))
