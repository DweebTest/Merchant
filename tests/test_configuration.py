"""The Configuration page and admin-editable labels."""
from app.extensions import db
from app.models import Setting

from .conftest import login, make_user
from .test_entries import add_entry


def test_admin_sees_one_configuration_link(admin_client):
    home = admin_client.get("/").data.decode()
    assert ">Configuration<" in home and ">Users<" not in home and ">Lists<" not in home
    page = admin_client.get("/admin/").data.decode()
    for text in ("Users", "Groups", "Lists", "Labels", "Economic clusters", "Follow-up statuses"):
        assert text in page


def test_contributors_cannot_see_configuration(client):
    make_user("sam@example.com", "sam-password-123", name="Sam")
    login(client, "sam@example.com", "sam-password-123")
    assert ">Configuration<" not in client.get("/").data.decode()
    assert client.get("/admin/").status_code == 403
    assert client.get("/admin/labels").status_code == 403


def test_renamed_labels_show_everywhere(admin_client):
    resp = admin_client.post("/admin/labels", data={
        "cluster": "Department", "clusters": "Departments", "type": "Request type", "types": "Request types",
        "status": "Ticket state", "statuses": "", "priority": "", "priorities": "", "area": "Location"})
    assert resp.status_code == 302
    # Blank or unchanged boxes aren't stored.
    assert {s.key for s in db.session.query(Setting)} == {
        "label.cluster", "label.clusters", "label.type", "label.types", "label.status", "label.area"}

    form = admin_client.get("/entries/new").data.decode()
    assert "Departments" in form and "Request types" in form and "Location" in form and "Ticket state" in form
    assert "Economic clusters" not in form
    add_entry(admin_client)
    assert "<legend>Department</legend>" in admin_client.get("/entries/").data.decode()
    assert "Departments" in admin_client.get("/admin/").data.decode()
    assert "Add department" in admin_client.get("/admin/lists/clusters").data.decode()
    assert "Follow-up statuses" in admin_client.get("/admin/lists/statuses").data.decode()  # left at default
    reports = admin_client.get("/reports/").data.decode()
    assert "count by department" in reports
    trends = admin_client.get("/reports/trends").data.decode()
    assert "Activity by department" in trends and "economic cluster" not in trends.lower()
    assert admin_client.get("/reports/recent.pdf").status_code == 200

    admin_client.post("/admin/labels", data={"reset": "1"})
    assert db.session.query(Setting).count() == 0
    assert "Economic clusters" in admin_client.get("/entries/new").data.decode()


def test_acronym_label_keeps_its_capitals(admin_client):
    admin_client.post("/admin/labels", data={"cluster": "CRM area", "clusters": "CRM areas"})
    assert "count by CRM area" in admin_client.get("/reports/").data.decode()
