from app.extensions import db
from app.models import Cluster, Group, Permission, User

from .conftest import login, make_user


def test_admin_creates_user_with_groups(admin_client, app):
    group = Group(name="Advancement")
    db.session.add(group)
    db.session.commit()

    resp = admin_client.post("/admin/users/new", data={
        "email": "New.Person@Example.com", "display_name": "New Person",
        "password": "temp-password-1", "is_active": "y", "groups": [str(group.id)],
    })
    assert resp.status_code == 302
    user = db.session.query(User).filter_by(email="new.person@example.com").one()
    assert user.must_change_password
    assert [g.name for g in user.groups] == ["Advancement"]
    assert not user.is_admin


def test_new_user_needs_password(admin_client, app):
    resp = admin_client.post("/admin/users/new", data={
        "email": "x@example.com", "display_name": "X", "is_active": "y",
    })
    assert resp.status_code == 200
    assert b"temporary password" in resp.data


def test_duplicate_email_rejected(admin_client, app):
    resp = admin_client.post("/admin/users/new", data={
        "email": "admin@example.com", "display_name": "Dup", "password": "temp-password-1", "is_active": "y",
    })
    assert b"already has this email" in resp.data


def test_cannot_remove_last_admin(admin_client, admin, app):
    resp = admin_client.post(f"/admin/users/{admin.id}", data={
        "email": "admin@example.com", "display_name": "Admin", "is_active": "y",
    }, follow_redirects=True)
    assert b"at least one active administrator" in resp.data
    assert db.session.get(User, admin.id).is_admin


def test_reset_password_unlocks_and_forces_change(admin_client, app):
    user = make_user(failed_login_count=3)
    admin_client.post(f"/admin/users/{user.id}", data={
        "email": user.email, "display_name": user.display_name, "is_active": "y", "password": "reset-password-9",
    })
    db.session.refresh(user)
    assert user.check_password("reset-password-9")
    assert user.must_change_password and user.failed_login_count == 0


def test_group_crud(admin_client, app):
    member = make_user()
    resp = admin_client.post("/admin/groups/new", data={
        "name": "Applied Research", "description": "Research office", "members": [str(member.id)],
    })
    assert resp.status_code == 302
    group = db.session.query(Group).filter_by(name="Applied Research").one()
    assert [u.email for u in group.members] == [member.email]

    # Duplicate names are refused.
    resp = admin_client.post("/admin/groups/new", data={"name": "Applied Research"})
    assert b"already exists" in resp.data

    admin_client.post(f"/admin/groups/{group.id}/delete", data={})
    assert db.session.query(Group).count() == 0
    assert db.session.get(User, member.id) is not None  # members keep their accounts


def test_group_permissions_ready_for_later(app):
    user = make_user()
    group = Group(name="Leadership")
    perm = Permission(code="reports.run", description="Run reports")
    group.permissions.append(perm)
    user.groups.append(group)
    db.session.commit()
    assert user.has_permission("reports.run")
    assert not user.has_permission("entries.delete")


def test_lookup_lists_seeded_and_editable(admin_client, app):
    resp = admin_client.get("/admin/lists/clusters")
    assert b"Agriculture" in resp.data and b"Governments" in resp.data
    assert b"Grant opportunity" in admin_client.get("/admin/lists/types").data

    resp = admin_client.post("/admin/lists/clusters/new", data={"name": "Mining", "sort_order": "200", "is_active": "y"})
    assert resp.status_code == 302
    mining = db.session.query(Cluster).filter_by(name="Mining").one()

    admin_client.post(f"/admin/lists/clusters/{mining.id}", data={"name": "Mining", "sort_order": "200"})
    db.session.refresh(mining)
    assert not mining.is_active


def test_unknown_list_is_404(admin_client):
    assert admin_client.get("/admin/lists/bogus").status_code == 404


def test_admin_pages_render(admin_client):
    for path in ["/admin/users", "/admin/users/new", "/admin/groups", "/admin/groups/new",
                 "/admin/lists/types/new", "/account/password", "/"]:
        assert admin_client.get(path).status_code == 200, path


def test_csrf_enforced_outside_tests(app):
    """Forms reject posts without a CSRF token when protection is on."""
    app.config["WTF_CSRF_ENABLED"] = True
    make_user()
    client = app.test_client()
    resp = login(client, "user@example.com", "correct-horse-1")
    assert resp.status_code in (200, 400)
    assert client.get("/").status_code == 302
