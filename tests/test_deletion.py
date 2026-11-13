"""Deleting users, groups and list values for good."""
from sqlalchemy import select

from app.extensions import db
from app.models import Cluster, Entry, FollowUpStatus, Group, Priority, User

from .conftest import make_user
from .test_entries import add_entry, ids


def _get(model, name):
    return db.session.scalar(select(model).where(model.name == name))


def _status(name):
    return str(_get(FollowUpStatus, name).id)


def _entries_by(user, client, status="Open", n=1):
    for _ in range(n):
        add_entry(client, status_id=_status(status))
    rows = db.session.scalars(select(Entry).order_by(Entry.id.desc()).limit(n)).all()
    for e in rows:
        e.created_by_id = e.owner_id = user.id
        e.created_by_name = user.display_name
    db.session.commit()
    return rows


def test_user_with_open_follow_ups_cannot_be_deleted(admin_client):
    pat = make_user("pat@example.com", "pat-password-123", name="Pat Lee")
    _entries_by(pat, admin_client, "Open")
    resp = admin_client.post(f"/admin/users/{pat.id}/delete")
    assert resp.status_code == 302 and db.session.get(User, pat.id) is not None
    assert b"still looks after 1 open follow-up" in admin_client.get(f"/admin/users/{pat.id}").data


def test_deleting_a_user_keeps_their_name_on_entries(admin_client):
    pat = make_user("pat@example.com", "pat-password-123", name="Pat Lee")
    (entry,) = _entries_by(pat, admin_client, "Done")
    resp = admin_client.post(f"/admin/users/{pat.id}/delete")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/admin/users")
    db.session.expire_all()
    assert db.session.scalar(select(User).where(User.email == "pat@example.com")) is None
    entry = db.session.get(Entry, entry.id)
    assert entry.created_by_id is None and entry.owner_id is None and entry.author_name == "Pat Lee"
    page = admin_client.get(f"/entries/{entry.id}").data.decode()
    assert "added by Pat Lee (former user)" in page and "Nobody" in page
    assert "Pat Lee (former user)" in admin_client.get("/entries/").data.decode()
    # Reopening a finished entry with nobody looking after it: it can be taken over.
    admin_client.post(f"/entries/{entry.id}/status", data={"status": _status("Open")})
    assert b"Reassign" in admin_client.get(f"/entries/{entry.id}").data
    assert admin_client.get("/reports/followups").status_code == 200


def test_cannot_delete_yourself(admin_client, admin):
    admin_client.post(f"/admin/users/{admin.id}/delete")
    assert db.session.get(User, admin.id) is not None


def test_inactive_users_hidden_by_default(admin_client):
    make_user("gone@example.com", "gone-password-1", name="Gone Person", is_active_flag=False)
    assert b"Gone Person" not in admin_client.get("/admin/users").data
    assert b"1 inactive person is hidden" in admin_client.get("/admin/users").data
    assert b"Gone Person" in admin_client.get("/admin/users?show=all").data


def test_inactive_group_not_offered_but_kept(admin_client):
    admin_client.post("/admin/groups/new", data={"name": "Old team", "is_active": ""})
    group = _get(Group, "Old team")
    assert not group.is_active
    admin_client.get("/admin/groups")  # clears the "Saved group" flash
    assert b"Old team" not in admin_client.get("/admin/users/new").data
    admin_client.post(f"/admin/groups/{group.id}/delete")
    assert _get(Group, "Old team") is None


def test_cluster_on_finished_entries_can_be_deleted(admin_client):
    add_entry(admin_client, clusters=ids(Cluster, "Trades", "Energy"), status_id=_status("Done"))
    trades = _get(Cluster, "Trades")
    admin_client.post(f"/admin/lists/clusters/{trades.id}/delete")
    assert _get(Cluster, "Trades") is None
    entry = db.session.scalar(select(Entry))
    db.session.refresh(entry)
    assert [c.name for c in entry.clusters] == ["Energy"]


def test_cluster_on_open_entry_cannot_be_deleted(admin_client):
    add_entry(admin_client, clusters=ids(Cluster, "Trades"), status_id=_status("Open"))
    trades = _get(Cluster, "Trades")
    admin_client.post(f"/admin/lists/clusters/{trades.id}/delete")
    assert _get(Cluster, "Trades") is not None


def test_deleting_priority_moves_finished_entries_to_default(admin_client):
    add_entry(admin_client, priority_id=str(_get(Priority, "Low").id), status_id=_status("Done"))
    low = _get(Priority, "Low")
    admin_client.post(f"/admin/lists/priorities/{low.id}/delete")
    assert _get(Priority, "Low") is None
    entry = db.session.scalar(select(Entry))
    db.session.refresh(entry)
    assert entry.priority.name == "Normal"


def test_deleting_closed_status_moves_entries_to_another_closed_one(admin_client):
    add_entry(admin_client, status_id=_status("No action needed"))
    na = _get(FollowUpStatus, "No action needed")
    admin_client.post(f"/admin/lists/statuses/{na.id}/delete")
    assert _get(FollowUpStatus, "No action needed") is None
    entry = db.session.scalar(select(Entry))
    db.session.refresh(entry)
    assert entry.status.name == "Done"
