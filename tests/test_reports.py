import re
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import Cluster, Entry, FollowUpStatus, OpportunityType, Organization, Priority
from app.reports.data import build_report, followups_report
from app.reports.pdf import render_pdf

TODAY = date.today()


def _cluster(name):
    return db.session.scalar(select(Cluster).where(Cluster.name == name))


def _type(name):
    return db.session.scalar(select(OpportunityType).where(OpportunityType.name == name))


def _named(model, name):
    return db.session.scalar(select(model).where(model.name == name))


def _entry(user, org, days_ago, clusters, types, **kw):
    if "priority" in kw:
        kw["priority"] = _named(Priority, kw["priority"])
    if "status" in kw:
        kw["status"] = _named(FollowUpStatus, kw["status"])
    organization = db.session.scalar(select(Organization).where(Organization.name == org)) or Organization(name=org)
    e = Entry(
        entry_date=TODAY - timedelta(days=days_ago),
        description=kw.pop("description", f"Notes about {org}"),
        organization=organization,
        created_by_id=user.id,
        clusters=[_cluster(c) for c in clusters],
        opportunity_types=[_type(t) for t in types],
        **kw,
    )
    db.session.add(e)
    db.session.commit()
    return e


@pytest.fixture()
def sample(app, admin):
    _entry(admin, "Prairie Wind", 5, ["Energy", "Trades"], ["Workforce/training need", "Partnership opportunity"],
           priority="High", next_step="Meet Continuing Ed")
    _entry(admin, "Prairie Wind", 12, ["Energy"], ["Partnership opportunity"], status="Done")
    _entry(admin, "Health Trust", 8, ["Health Care"], ["Potential donor", "Grant opportunity"],
           follow_up_date=TODAY - timedelta(days=2))
    _entry(admin, "SkyMap", 20, ["Technology", "Agriculture"], ["Applied research opportunity"],
           follow_up_date=TODAY + timedelta(days=5))
    _entry(admin, "Old Co", 70, ["Energy"], ["Industry intelligence"])          # previous period for trends
    _entry(admin, "Ancient Co", 400, ["Tourism"], ["Potential sponsor"])      # outside every default range
    return admin


def _rows(report, heading):
    return next(s for s in report.sections if s.heading == heading).rows


def test_recent(sample):
    r = build_report("recent", TODAY - timedelta(days=29), TODAY, [])
    assert dict(r.summary)["Entries"] == 4
    assert dict(r.summary)["Organizations"] == 3
    clusters = dict((row[0], row[1]) for row in _rows(r, "Entries by economic cluster"))
    assert clusters["Energy"] == 2 and clusters["Agriculture"] == 1
    assert [row[1] for row in _rows(r, "All entries")] == ["Prairie Wind", "Health Trust", "Prairie Wind", "SkyMap"]


def test_recent_cluster_filter(sample):
    r = build_report("recent", TODAY - timedelta(days=29), TODAY, [_cluster("Health Care").id])
    assert [row[1] for row in _rows(r, "All entries")] == ["Health Trust"]
    assert "Health Care" in r.filters


def test_trends_compares_with_previous_period(sample):
    r = build_report("trends", TODAY - timedelta(days=59), TODAY, [])
    energy = next(row for row in _rows(r, "Activity by economic cluster") if row[0] == "Energy")
    assert energy[1:] == [2, 1, "+100%"]
    health = next(row for row in _rows(r, "Activity by economic cluster") if row[0] == "Health Care")
    assert health[1:] == [1, 0, "new"]
    assert _rows(r, "Organizations mentioned more than once")[0][0] == "Prairie Wind"
    assert any(s.heading == "Entries per month by cluster" for s in r.sections)


def test_funding_uses_report_groups(sample):
    r = build_report("funding", TODAY - timedelta(days=89), TODAY, [])
    assert [row[1] for row in _rows(r, "Open funding leads")] == ["Health Trust"]
    assert "Potential donor" in _rows(r, "Open funding leads")[0][2]

    # An admin can move a type into the funding report.
    _type("Workforce/training need").report_group = "funding"
    db.session.commit()
    r = build_report("funding", TODAY - timedelta(days=89), TODAY, [])
    assert [row[1] for row in _rows(r, "Open funding leads")] == ["Prairie Wind", "Health Trust"]  # high priority first


def test_partnership_groups_by_org(sample):
    r = build_report("partnership", TODAY - timedelta(days=89), TODAY, [])
    by_org = {row[0]: row for row in _rows(r, "Leads by organization")}
    assert set(by_org) == {"Prairie Wind", "SkyMap"}
    assert by_org["Prairie Wind"][1] == 2 and by_org["Prairie Wind"][6] == "1 open"


def test_followups(sample):
    r = followups_report(None, None, [], today=TODAY)
    assert [row[1] for row in _rows(r, "Overdue")] == ["Health Trust"]
    assert [row[1] for row in _rows(r, "Due in the next 14 days")] == ["SkyMap"]
    assert [row[1] for row in _rows(r, "Other high-priority follow-ups")] == ["Prairie Wind"]


@pytest.mark.parametrize("key", ["recent", "trends", "funding", "partnership", "followups"])
def test_pdf_and_page_render(sample, admin_client, key):
    page = admin_client.get(f"/reports/{key}")
    assert page.status_code == 200
    pdf = admin_client.get(f"/reports/{key}.pdf?range=365")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF")
    assert "attachment" in pdf.headers["Content-Disposition"]


@pytest.mark.parametrize("key", ["recent", "trends", "funding", "partnership", "followups"])
def test_empty_reports_render(app, admin_client, key):
    assert admin_client.get(f"/reports/{key}").status_code == 200
    assert admin_client.get(f"/reports/{key}.pdf").data.startswith(b"%PDF")


def test_long_text_and_many_rows_paginate(app, admin):
    for i in range(60):
        _entry(admin, f"Org {i}", i % 25, ["Energy"], ["Grant opportunity"], description="Long note. " * 80)
    r = build_report("funding", TODAY - timedelta(days=89), TODAY, [])
    data = render_pdf(r)
    pages = len(re.findall(rb"/Type /Page[^s]", data))
    assert pages >= 3


def test_bad_params_ignored(sample, admin_client):
    assert admin_client.get("/reports/recent?from=bad&to=2026-13-01&cluster=x&range=7").status_code == 200
    assert admin_client.get("/reports/nope").status_code == 404


def test_reports_require_login(client):
    assert client.get("/reports/recent.pdf").status_code == 302


def test_admin_sets_report_group(admin_client, app):
    t = _type("Engagement event")
    resp = admin_client.post(f"/admin/lists/types/{t.id}", data={
        "name": "Engagement event", "sort_order": "70", "is_active": "y", "report_group": "partnership",
    })
    assert resp.status_code == 302
    db.session.refresh(t)
    assert t.report_group == "partnership"
    # Editing a cluster doesn't trip over the types-only field.
    c = _cluster("Energy")
    assert admin_client.post(f"/admin/lists/clusters/{c.id}", data={"name": "Energy", "sort_order": "20",
                                                                    "is_active": "y"}).status_code == 302
