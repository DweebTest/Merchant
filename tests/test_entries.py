import io
import os
from datetime import date, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import Attachment, Cluster, Contact, Entry, OpportunityType, Organization

from .conftest import login, make_user


def ids(model, *names):
    return [str(i) for i in db.session.scalars(select(model.id).where(model.name.in_(names)))]


def entry_data(**overrides):
    data = {
        "entry_date": "2026-11-01",
        "description": "Met with the plant manager about a welding apprenticeship pilot.",
        "organization": "Acme Manufacturing",
        "clusters": ids(Cluster, "Trades"),
        "opportunity_types": ids(OpportunityType, "Workforce/training need", "Partnership opportunity"),
        "next_step": "Send a proposal for a 12-week cohort.",
        "priority": "high",
        "follow_up_status": "open",
        "follow_up_date": "",
        "link_url": "",
    }
    data.update(overrides)
    return data


def add_entry(client, **overrides):
    return client.post("/entries/new", data=entry_data(**overrides), content_type="multipart/form-data")


def test_create_entry_with_contact_and_new_org(admin_client, app):
    resp = add_entry(admin_client, contact_name="Pat Lee", contact_email="pat@acme.example", contact_title="Plant manager")
    assert resp.status_code == 302
    entry = db.session.scalars(select(Entry)).one()
    assert entry.organization.name == "Acme Manufacturing"
    assert entry.contact.name == "Pat Lee" and entry.contact.organization_id == entry.organization_id
    assert [c.name for c in entry.clusters] == ["Trades"]
    assert len(entry.opportunity_types) == 2
    assert entry.priority == "high"

    page = admin_client.get(f"/entries/{entry.id}")
    assert b"Acme Manufacturing" in page.data and b"pat@acme.example" in page.data


def test_existing_organization_and_contact_reused(admin_client, app):
    add_entry(admin_client, contact_name="Pat Lee")
    add_entry(admin_client, organization="  acme   manufacturing ", contact_name="pat lee", contact_phone="555-0100")
    assert db.session.query(Organization).count() == 1
    assert db.session.query(Contact).count() == 1
    assert db.session.scalars(select(Contact)).one().phone == "555-0100"


def test_required_fields(admin_client, app):
    resp = add_entry(admin_client, description="", organization="", clusters=[], opportunity_types=[])
    assert resp.status_code == 200
    assert resp.data.count(b"Pick at least one.") == 2
    assert db.session.query(Entry).count() == 0


def test_javascript_link_rejected(admin_client, app):
    resp = add_entry(admin_client, link_url="javascript:alert(1)")
    assert resp.status_code == 200
    assert db.session.query(Entry).count() == 0


def test_attachment_upload_download_and_delete(admin_client, app):
    resp = add_entry(admin_client, attachments=[
        (io.BytesIO(b"%PDF-1.4 test"), "Proposal draft.pdf"),
        (io.BytesIO(b"<script>"), "evil.html"),
    ])
    assert resp.status_code == 302
    entry = db.session.scalars(select(Entry)).one()
    assert [a.original_filename for a in entry.attachments] == ["Proposal_draft.pdf"]
    att = entry.attachments[0]
    path = os.path.join(app.config["UPLOAD_FOLDER"], att.stored_filename)
    assert os.path.exists(path)

    dl = admin_client.get(f"/entries/attachments/{att.id}")
    assert dl.status_code == 200 and dl.data == b"%PDF-1.4 test"
    assert "attachment" in dl.headers["Content-Disposition"]

    admin_client.post(f"/entries/{entry.id}/delete")
    assert db.session.query(Attachment).count() == 0
    assert not os.path.exists(path)


def test_only_creator_or_admin_can_edit(client, app):
    author = make_user("author@example.com", "author-password-1")
    make_user("other@example.com", "other-password-1")
    login(client, "author@example.com", "author-password-1")
    add_entry(client)
    entry = db.session.scalars(select(Entry)).one()
    assert entry.created_by_id == author.id
    client.post("/logout")

    login(client, "other@example.com", "other-password-1")
    assert client.get(f"/entries/{entry.id}").status_code == 200
    assert client.get(f"/entries/{entry.id}/edit").status_code == 403
    assert client.post(f"/entries/{entry.id}/delete").status_code == 403
    # ...but anyone can update the follow-up status.
    client.post(f"/entries/{entry.id}/status", data={"status": "done"})
    db.session.refresh(entry)
    assert entry.follow_up_status == "done"


def test_edit_entry(admin_client, app):
    add_entry(admin_client)
    entry = db.session.scalars(select(Entry)).one()
    form = admin_client.get(f"/entries/{entry.id}/edit")
    assert b"Acme Manufacturing" in form.data
    resp = admin_client.post(
        f"/entries/{entry.id}/edit",
        data=entry_data(description="Updated text", clusters=ids(Cluster, "Energy", "Technology")),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    db.session.refresh(entry)
    assert entry.description == "Updated text"
    assert sorted(c.name for c in entry.clusters) == ["Energy", "Technology"]


def _seed_search_data(client):
    add_entry(client, entry_date="2026-10-01", description="Wind farm expansion needs technicians",
              organization="Prairie Power", clusters=ids(Cluster, "Energy"),
              opportunity_types=ids(OpportunityType, "Workforce/training need"), priority="normal")
    add_entry(client, entry_date="2026-11-05", description="Foundation interested in nursing scholarships",
              organization="Health Trust", clusters=ids(Cluster, "Health Care"),
              opportunity_types=ids(OpportunityType, "Potential donor"), contact_name="Dana Wu")
    add_entry(client, entry_date="2026-11-07", description="Drone mapping research collaboration",
              organization="SkyTech", clusters=ids(Cluster, "Technology", "Agriculture"),
              opportunity_types=ids(OpportunityType, "Applied research opportunity"), follow_up_status="done")


def _orgs(resp):
    return [name for name in ("Prairie Power", "Health Trust", "SkyTech") if name.encode() in resp.data]


def test_search_and_filters(admin_client, app):
    _seed_search_data(admin_client)
    c = admin_client

    assert _orgs(c.get("/entries/")) == ["Prairie Power", "Health Trust", "SkyTech"]
    assert _orgs(c.get("/entries/?q=nursing")) == ["Health Trust"]
    assert _orgs(c.get("/entries/?q=dana")) == ["Health Trust"]          # contact name
    assert _orgs(c.get("/entries/?q=skytech")) == ["SkyTech"]             # organization name
    assert _orgs(c.get("/entries/?q=wind+technicians")) == ["Prairie Power"]  # all words must match
    assert _orgs(c.get("/entries/?q=100%25")) == []                       # LIKE wildcards are literal

    energy, agri = ids(Cluster, "Energy")[0], ids(Cluster, "Agriculture")[0]
    assert _orgs(c.get(f"/entries/?cluster={energy}")) == ["Prairie Power"]
    assert _orgs(c.get(f"/entries/?cluster={energy}&cluster={agri}")) == ["Prairie Power", "SkyTech"]

    donor = ids(OpportunityType, "Potential donor")[0]
    assert _orgs(c.get(f"/entries/?type={donor}")) == ["Health Trust"]

    assert _orgs(c.get("/entries/?from=2026-11-01&to=2026-11-06")) == ["Health Trust"]
    assert _orgs(c.get("/entries/?status=done")) == ["SkyTech"]
    assert _orgs(c.get("/entries/?priority=high")) == ["Health Trust", "SkyTech"]


def test_bad_filter_values_are_ignored(admin_client, app):
    _seed_search_data(admin_client)
    resp = admin_client.get("/entries/?cluster=abc&from=notadate&status=bogus&sort=nope&page=999")
    assert resp.status_code == 200


def test_date_preset(admin_client, app):
    add_entry(admin_client, entry_date=(date.today() - timedelta(days=3)).isoformat(), organization="Recent Co")
    add_entry(admin_client, entry_date=(date.today() - timedelta(days=60)).isoformat(), organization="Older Co")
    resp = admin_client.get("/entries/?range=7")
    assert b"Recent Co" in resp.data and b"Older Co" not in resp.data


def test_home_shows_recent_and_due(admin_client, app):
    add_entry(admin_client, organization="Due Co", follow_up_date=(date.today() - timedelta(days=1)).isoformat())
    resp = admin_client.get("/")
    assert b"Recent submissions" in resp.data
    assert b"Follow-ups due" in resp.data and b"Due Co" in resp.data


def test_pagination(admin_client, app):
    for i in range(27):
        add_entry(admin_client, organization=f"Org {i:02d}")
    first = admin_client.get("/entries/")
    assert b"Page 1 of 2" in first.data
    second = admin_client.get("/entries/?page=2")
    assert second.status_code == 200 and b"Page 2 of 2" in second.data


def test_retired_cluster_hidden_from_new_form(admin_client, app):
    trades = db.session.scalar(select(Cluster).where(Cluster.name == "Trades"))
    trades.is_active = False
    db.session.commit()
    assert b">Trades<" not in admin_client.get("/entries/new").data
