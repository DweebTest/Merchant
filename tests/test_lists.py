"""The admin Lists page: clusters, opportunity types, priorities and statuses."""
from sqlalchemy import select

from app.extensions import db
from app.models import Cluster, Entry, FollowUpStatus, Priority
from app.reports.data import followups_report

from .conftest import login, make_user
from .test_entries import add_entry, ids


def _get(model, name):
    return db.session.scalar(select(model).where(model.name == name))


def save(client, kind, item_id=None, **data):
    url = f"/admin/lists/{kind}/{item_id}" if item_id else f"/admin/lists/{kind}/new"
    data.setdefault("sort_order", "50")
    data.setdefault("is_active", "y")
    return client.post(url, data=data)


def test_lists_page_is_admin_only(app, client):
    make_user("pat@example.com", "correct-horse-1")
    login(client, "pat@example.com", "correct-horse-1")
    assert client.get("/admin/lists").status_code == 403
    assert client.get("/admin/lists/priorities").status_code == 403
    assert client.post("/admin/lists/statuses/new", data={"name": "Sneaky"}).status_code == 403


def test_lists_overview_shows_all_four(admin_client):
    html = admin_client.get("/admin/lists").data.decode()
    for label in ("Economic clusters", "Opportunity types", "Priorities", "Follow-up statuses"):
        assert label in html
    assert "No action needed" in html and "Lists" in admin_client.get("/").data.decode()


def test_new_default_priority_replaces_old_and_is_preselected(admin_client):
    resp = save(admin_client, "priorities", name="Urgent", is_high="y", is_default="y", sort_order="5")
    assert resp.status_code == 302
    assert _get(Priority, "Urgent").is_default and not _get(Priority, "Normal").is_default
    form = admin_client.get("/entries/new").data.decode()
    assert f'<option selected value="{_get(Priority, "Urgent").id}">Urgent</option>' in form


def test_renaming_changes_existing_entries(admin_client):
    add_entry(admin_client, status_id=ids(FollowUpStatus, "Open")[0])
    status = _get(FollowUpStatus, "Open")
    save(admin_client, "statuses", status.id, name="Waiting on us", is_open="y", is_default="y", colour="amber")
    entry = db.session.scalar(select(Entry))
    assert b"Waiting on us" in admin_client.get(f"/entries/{entry.id}").data


def test_delete_unused_value(admin_client):
    save(admin_client, "statuses", name="Parked", colour="grey")
    parked = _get(FollowUpStatus, "Parked")
    resp = admin_client.post(f"/admin/lists/statuses/{parked.id}/delete")
    assert resp.status_code == 302 and _get(FollowUpStatus, "Parked") is None
    tourism = _get(Cluster, "Tourism")
    admin_client.post(f"/admin/lists/clusters/{tourism.id}/delete")
    assert _get(Cluster, "Tourism") is None


def test_used_value_cannot_be_deleted_but_can_be_retired(admin_client):
    add_entry(admin_client, status_id=ids(FollowUpStatus, "In progress")[0])
    in_progress = _get(FollowUpStatus, "In progress")
    admin_client.post(f"/admin/lists/statuses/{in_progress.id}/delete")
    assert _get(FollowUpStatus, "In progress") is not None
    assert b"once those open follow-ups are marked done" in admin_client.get(f"/admin/lists/statuses/{in_progress.id}").data

    save(admin_client, "statuses", in_progress.id, name="In progress", is_open="y", colour="blue", is_active="")
    db.session.refresh(in_progress)
    assert not in_progress.is_active
    # Gone from the new-entry form, still offered when editing the entry that uses it.
    assert b">In progress<" not in admin_client.get("/entries/new").data
    entry = db.session.scalar(select(Entry))
    assert b">In progress<" in admin_client.get(f"/entries/{entry.id}/edit").data


def test_default_cannot_be_deleted_or_retired(admin_client):
    normal = _get(Priority, "Normal")
    admin_client.post(f"/admin/lists/priorities/{normal.id}/delete")
    assert _get(Priority, "Normal") is not None
    save(admin_client, "priorities", normal.id, name="Normal", is_default="y", is_active="")
    db.session.refresh(normal)
    assert normal.is_active and normal.is_default


def test_duplicate_names_refused(admin_client):
    resp = save(admin_client, "priorities", name="  high ")
    assert resp.status_code == 200 and b"already on the list" in resp.data


def test_new_entry_without_choice_gets_defaults(app, admin):
    from datetime import date
    from app.models import Organization
    e = Entry(entry_date=date.today(), description="x", organization=Organization(name="Org"), created_by_id=admin.id)
    db.session.add(e)
    db.session.commit()
    assert e.priority.name == "Normal" and e.status.name == "Open"


def test_meanings_drive_home_page_and_reports(admin_client):
    # A new open status and a new high priority count like the built-in ones.
    save(admin_client, "statuses", name="Waiting on partner", is_open="y", colour="blue")
    save(admin_client, "priorities", name="Critical", is_high="y", sort_order="1")
    add_entry(admin_client, organization="Wind Co", status_id=ids(FollowUpStatus, "Waiting on partner")[0],
              priority_id=ids(Priority, "Critical")[0])
    add_entry(admin_client, organization="Done Co", status_id=ids(FollowUpStatus, "Done")[0])
    home = admin_client.get("/").data.decode()
    assert '<span class="num">1</span><span>open follow-ups</span>' in home
    assert '<span class="num">1</span><span>high priority, open</span>' in home
    report = followups_report(None, None, [])
    assert dict(report.summary)["All open follow-ups"] == 1
    assert dict(report.summary)["Other high priority"] == 1
