"""Reassigning who looks after an entry."""
from sqlalchemy import select

from app.extensions import db
from app.models import Entry, User

from .conftest import login, make_user
from .test_entries import add_entry


def _entry():
    return db.session.scalar(select(Entry))


def _switch(client, email, password):
    from flask import g
    client.post("/logout")
    g.pop("_login_user", None)
    login(client, email, password)


def test_new_entry_is_looked_after_by_its_author(admin_client, admin):
    add_entry(admin_client)
    e = _entry()
    assert e.owner_id == e.created_by_id == admin.id


def test_owner_hands_entry_to_someone_who_can_then_edit(app, client):
    make_user("ann@example.com", "ann-password-1", name="Ann")
    bob = make_user("bob@example.com", "bob-password-1", name="Bob")
    login(client, "ann@example.com", "ann-password-1")
    add_entry(client)
    e = _entry()
    resp = client.post(f"/entries/{e.id}/owner", data={"owner": bob.id})
    assert resp.status_code == 302
    db.session.refresh(e)
    assert e.owner_id == bob.id and e.created_by.display_name == "Ann"

    _switch(client, "bob@example.com", "bob-password-1")
    assert client.get(f"/entries/{e.id}/edit").status_code == 200
    assert "Acme Manufacturing" in client.get("/entries/?mine=1").data.decode()


def test_others_cannot_reassign_an_active_owners_entry(app, client):
    make_user("ann@example.com", "ann-password-1", name="Ann")
    make_user("cat@example.com", "cat-password-1", name="Cat")
    login(client, "ann@example.com", "ann-password-1")
    add_entry(client)
    e = _entry()
    _switch(client, "cat@example.com", "cat-password-1")
    cat = db.session.scalar(select(User).where(User.email == "cat@example.com"))
    assert b"Take this over" not in client.get(f"/entries/{e.id}").data
    assert client.post(f"/entries/{e.id}/owner", data={"owner": cat.id}).status_code == 403


def test_anyone_can_take_over_a_former_users_entry(app, client):
    ann = make_user("ann@example.com", "ann-password-1", name="Ann")
    make_user("cat@example.com", "cat-password-1", name="Cat")
    login(client, "ann@example.com", "ann-password-1")
    add_entry(client)
    e = _entry()
    ann.is_active_flag = False
    db.session.commit()
    _switch(client, "cat@example.com", "cat-password-1")
    cat = db.session.scalar(select(User).where(User.email == "cat@example.com"))
    page = client.get(f"/entries/{e.id}").data.decode()
    assert "Take this over" in page and "former user" in page
    # ...but only to themselves.
    other = make_user("dan@example.com", "dan-password-1")
    assert client.post(f"/entries/{e.id}/owner", data={"owner": other.id}).status_code == 403
    client.post(f"/entries/{e.id}/owner", data={"owner": cat.id})
    db.session.refresh(e)
    assert e.owner_id == cat.id
    assert client.get(f"/entries/{e.id}/edit").status_code == 200


def test_admin_moves_a_leavers_open_entries(app, admin_client, admin):
    from app.models import FollowUpStatus
    leaver = make_user("leaver@example.com", "leaver-password-1", name="Leaver")
    keeper = make_user("keeper@example.com", "keeper-password-1", name="Keeper")
    open_id = db.session.scalar(select(FollowUpStatus.id).where(FollowUpStatus.name == "Open"))
    done_id = db.session.scalar(select(FollowUpStatus.id).where(FollowUpStatus.name == "Done"))
    for status_id in (open_id, open_id, done_id):
        add_entry(admin_client, status_id=str(status_id))
    for e in db.session.scalars(select(Entry)):
        e.owner_id = leaver.id
    db.session.commit()

    page = admin_client.get(f"/admin/users/{leaver.id}").data.decode()
    assert "looks after 3 entries" in page and "2 with open follow-ups" in page
    admin_client.post(f"/admin/users/{leaver.id}/reassign", data={"owner": keeper.id, "only_open": "1"})
    owners = sorted(e.owner_id for e in db.session.scalars(select(Entry)))
    assert owners == sorted([keeper.id, keeper.id, leaver.id])
    admin_client.post(f"/admin/users/{leaver.id}/reassign", data={"owner": keeper.id})
    assert all(e.owner_id == keeper.id for e in db.session.scalars(select(Entry)))


def test_bulk_reassign_is_admin_only(app, client):
    a = make_user("a@example.com", "a-password-123")
    b = make_user("b@example.com", "b-password-123")
    login(client, "a@example.com", "a-password-123")
    assert client.post(f"/admin/users/{b.id}/reassign", data={"owner": a.id}).status_code == 403
