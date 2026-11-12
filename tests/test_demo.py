from sqlalchemy import func, select

from app.demo import clear_demo, load_demo
from app.extensions import db
from app.models import Contact, Entry, Group, Organization, User

from .conftest import login, make_user


def count(model, demo=None):
    q = select(func.count(model.id))
    if demo is not None:
        q = q.where(model.is_demo.is_(demo))
    return db.session.scalar(q)


def test_load_creates_flagged_data(app):
    counts = load_demo(entries=50)
    assert counts["entries"] == 50 == count(Entry, demo=True)
    assert count(Organization, demo=True) > 10
    assert count(User, demo=True) == 6
    assert all(e.clusters and e.opportunity_types for e in db.session.scalars(select(Entry)))


def test_demo_people_are_past_users_who_cannot_sign_in(app, client):
    load_demo(entries=40)
    people = db.session.scalars(select(User).where(User.is_demo.is_(True))).all()
    assert people and all(not u.is_active and u.password_hash is None for u in people)
    for password in ("Demo-pass-2026", "", "password"):
        assert login(client, "alex.morgan@demo.example.com", password).status_code != 302


def test_old_demo_logins_are_switched_off_on_load(app, client):
    old = make_user("alex.morgan@demo.example.com", "Demo-pass-2026", is_demo=True)
    load_demo(entries=5)
    db.session.refresh(old)
    assert not old.is_active and old.password_hash is None
    assert login(client, "alex.morgan@demo.example.com", "Demo-pass-2026").status_code != 302


def test_past_users_leave_open_follow_ups(app, admin_client):
    counts = load_demo(entries=60)
    assert counts["open"] >= 20
    entry = db.session.scalar(select(Entry).where(Entry.is_demo.is_(True)).limit(1))
    assert b"(former user)" in admin_client.get(f"/entries/{entry.id}").data
    assert b"(former user)" in admin_client.get("/entries/").data


def test_load_is_repeatable(app):
    load_demo(entries=30, seed=1)
    first = [(e.organization.name, e.entry_date) for e in db.session.scalars(select(Entry).order_by(Entry.id))]
    clear_demo()
    load_demo(entries=30, seed=1)
    second = [(e.organization.name, e.entry_date) for e in db.session.scalars(select(Entry).order_by(Entry.id))]
    assert first == second


def test_clear_removes_only_demo_data(app, admin_client, admin):
    real_org = Organization(name="Real Partner Inc")
    db.session.add(Entry(entry_date=db.func.current_date(), description="Real note", organization=real_org,
                         created_by_id=admin.id))
    real_group = Group(name="Real Team")
    db.session.add(real_group)
    db.session.commit()

    load_demo(entries=40)
    counts = clear_demo()
    assert counts["entries"] == 40
    for model in (Entry, Organization, Contact, User, Group):
        assert count(model, demo=True) == 0, model
    assert count(Entry) == 1 and count(Organization) == 1
    assert db.session.scalar(select(Group).where(Group.name == "Real Team"))
    assert db.session.get(User, admin.id)


def test_clear_keeps_demo_rows_that_real_data_uses(app, admin):
    load_demo(entries=10)
    demo_org = db.session.scalar(select(Organization).where(Organization.name == "Prairie Wind Energy"))
    db.session.add(Entry(entry_date=db.func.current_date(), description="Real follow-up", organization=demo_org,
                         created_by_id=admin.id))
    db.session.commit()
    counts = clear_demo()
    assert counts["kept"] >= 1
    assert db.session.scalar(select(Organization).where(Organization.name == "Prairie Wind Energy"))
    assert count(Entry) == 1


def test_existing_real_org_is_reused_not_flagged(app):
    db.session.add(Organization(name="TechNorth Accelerator"))
    db.session.commit()
    load_demo(entries=20)
    org = db.session.scalar(select(Organization).where(Organization.name == "TechNorth Accelerator"))
    assert not org.is_demo
    clear_demo()
    assert db.session.scalar(select(Organization).where(Organization.name == "TechNorth Accelerator"))


def test_cli_load_and_clear(app):
    make_user("admin@example.com", "admin-password-1", admin=True)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["demo-data", "load", "--entries", "15"])
    assert result.exit_code == 0 and "Added 15 entries" in result.output
    again = runner.invoke(args=["demo-data", "load"])
    assert "follow-ups are still open" in result.output and "password" not in result.output.lower()
    assert again.exit_code != 0 and "already loaded" in again.output
    cleared = runner.invoke(args=["demo-data", "clear", "--yes"])
    assert cleared.exit_code == 0 and "Removed 15 entries" in cleared.output
    assert count(Entry) == 0
