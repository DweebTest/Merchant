"""Gather the numbers and rows for each report.

Each builder returns a Report: a title, a few headline figures and a list of
sections (tables, optionally with a bar chart). The same Report feeds the
on-screen page and the PDF, so the two always match.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Cluster, Entry, OpportunityType, entry_clusters, entry_opportunity_types

STATUS_LABELS = {"open": "Open", "in_progress": "In progress", "done": "Done", "no_action": "No action"}
PRIORITY_LABELS = {"high": "High", "normal": "Normal", "low": "Low"}
OPEN_STATUSES = ("open", "in_progress")


@dataclass
class Section:
    heading: str
    columns: list
    rows: list
    intro: str = ""
    empty_text: str = "Nothing to show for this period."
    # Relative column widths for the PDF (they're scaled to the page).
    widths: list = None
    # Optional bar chart: list of (label, value).
    chart: list = None
    chart_title: str = ""


@dataclass
class Report:
    key: str
    title: str
    period: str
    filters: str
    summary: list = field(default_factory=list)  # list of (label, value)
    sections: list = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class ReportSpec:
    key: str
    title: str
    description: str
    default_days: int
    uses_period: bool = True


SPECS = {
    s.key: s
    for s in [
        ReportSpec("recent", "Recent opportunities",
                   "Everything entered in a period, newest first, with a count by cluster.", 30),
        ReportSpec("trends", "Emerging sector trends",
                   "Which clusters, opportunity types and organizations are coming up more or less "
                   "often than in the period before.", 180),
        ReportSpec("funding", "Potential funding opportunities",
                   "Potential donors, sponsors and grants (or whichever types an admin marks as funding).", 90),
        ReportSpec("partnership", "Partnership leads",
                   "Partnership and applied research leads, grouped by organization.", 90),
        ReportSpec("followups", "Priority follow-ups",
                   "Open follow-ups that are overdue, due in the next two weeks, or marked high priority. "
                   "Always shows the current state, so the date range doesn't apply.", 0, uses_period=False),
    ]
}


# --- Shared helpers ---------------------------------------------------------

def _fmt(d):
    return f"{d:%b} {d.day}, {d.year}" if d else ""


def _short(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _names(items):
    return ", ".join(i.name for i in items)


def _cluster_filter(cluster_ids):
    if not cluster_ids:
        return []
    return [exists().where(and_(entry_clusters.c.entry_id == Entry.id, entry_clusters.c.cluster_id.in_(cluster_ids)))]


def _type_group_filter(group):
    type_ids = select(OpportunityType.id).where(OpportunityType.report_group == group)
    return exists().where(and_(
        entry_opportunity_types.c.entry_id == Entry.id,
        entry_opportunity_types.c.opportunity_type_id.in_(type_ids),
    ))


def _entries(*conditions, order=None):
    query = (
        select(Entry)
        .where(*conditions)
        .options(
            selectinload(Entry.organization),
            selectinload(Entry.contact),
            selectinload(Entry.clusters),
            selectinload(Entry.opportunity_types),
            selectinload(Entry.created_by),
        )
        .order_by(*(order or (Entry.entry_date.desc(), Entry.id.desc())))
    )
    return db.session.scalars(query).all()


def _in_period(date_from, date_to):
    return [Entry.entry_date >= date_from, Entry.entry_date <= date_to]


def _period_text(date_from, date_to):
    return f"{_fmt(date_from)} to {_fmt(date_to)}"


def _filters_text(cluster_ids):
    if not cluster_ids:
        return "All economic clusters"
    names = db.session.scalars(select(Cluster.name).where(Cluster.id.in_(cluster_ids)).order_by(Cluster.sort_order))
    return "Clusters: " + ", ".join(names)


def _contact_text(e):
    if not e.contact:
        return ""
    parts = [e.contact.name]
    if e.contact.email:
        parts.append(e.contact.email)
    elif e.contact.phone:
        parts.append(e.contact.phone)
    return "\n".join(parts)


def _change(now, before):
    if before == 0:
        return "new" if now else "—"
    pct = round((now - before) * 100 / before)
    return f"{pct:+d}%"


# --- Reports ----------------------------------------------------------------

def recent_report(date_from, date_to, cluster_ids):
    entries = _entries(*_in_period(date_from, date_to), *_cluster_filter(cluster_ids))
    report = Report("recent", SPECS["recent"].title, _period_text(date_from, date_to), _filters_text(cluster_ids))
    report.summary = [
        ("Entries", len(entries)),
        ("Organizations", len({e.organization_id for e in entries})),
        ("Contributors", len({e.created_by_id for e in entries})),
        ("Open follow-ups", sum(e.follow_up_status in OPEN_STATUSES for e in entries)),
    ]

    by_cluster = Counter(c.name for e in entries for c in e.clusters)
    report.sections.append(Section(
        "Entries by economic cluster",
        ["Cluster", "Entries"],
        [[name, count] for name, count in by_cluster.most_common()],
        intro="An entry tagged with two clusters counts in both.",
        widths=[3, 1],
        chart=by_cluster.most_common(),
        chart_title="Entries by cluster",
    ))
    report.sections.append(Section(
        "All entries",
        ["Date", "Organization", "Clusters / types", "Description", "Suggested next step", "Status"],
        [[
            _fmt(e.entry_date),
            e.organization.name,
            _names(e.clusters) + "\n" + _names(e.opportunity_types),
            _short(e.description, 400),
            _short(e.next_step, 200),
            STATUS_LABELS.get(e.follow_up_status, e.follow_up_status),
        ] for e in entries],
        widths=[1.1, 1.6, 1.8, 3.6, 2.2, 0.9],
    ))
    return report


def trends_report(date_from, date_to, cluster_ids):
    length = (date_to - date_from).days + 1
    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=length - 1)
    current = _entries(*_in_period(date_from, date_to), *_cluster_filter(cluster_ids))
    previous = _entries(*_in_period(prev_from, prev_to), *_cluster_filter(cluster_ids))

    report = Report("trends", SPECS["trends"].title, _period_text(date_from, date_to), _filters_text(cluster_ids))
    report.summary = [
        ("Entries this period", len(current)),
        ("Previous period", len(previous)),
        ("Change", _change(len(current), len(previous))),
    ]
    compare_note = f"Compared with the previous {length} days ({_period_text(prev_from, prev_to)})."

    def compare(counter_now, counter_before):
        names = set(counter_now) | set(counter_before)
        rows = sorted(names, key=lambda n: (-counter_now[n], -(counter_now[n] - counter_before[n]), n))
        return [[n, counter_now[n], counter_before[n], _change(counter_now[n], counter_before[n])] for n in rows]

    clusters_now = Counter(c.name for e in current for c in e.clusters)
    clusters_before = Counter(c.name for e in previous for c in e.clusters)
    report.sections.append(Section(
        "Activity by economic cluster",
        ["Cluster", "This period", "Previous period", "Change"],
        compare(clusters_now, clusters_before),
        intro=compare_note,
        widths=[3, 1.2, 1.2, 1],
        chart=clusters_now.most_common(),
        chart_title="Entries this period",
    ))

    # Month-by-month counts for each cluster.
    months = []
    cursor = date(date_from.year, date_from.month, 1)
    while cursor <= date_to:
        months.append(cursor)
        cursor = date(cursor.year + cursor.month // 12, cursor.month % 12 + 1, 1)
    if len(months) <= 12:
        monthly = defaultdict(Counter)
        for e in current:
            key = date(e.entry_date.year, e.entry_date.month, 1)
            for c in e.clusters:
                monthly[c.name][key] += 1
        rows = [[name] + [monthly[name][m] for m in months]
                for name, _ in clusters_now.most_common()]
        report.sections.append(Section(
            "Entries per month by cluster",
            ["Cluster"] + [f"{m:%b %Y}" for m in months],
            rows,
            widths=[2.5] + [1] * len(months),
        ))

    types_now = Counter(t.name for e in current for t in e.opportunity_types)
    types_before = Counter(t.name for e in previous for t in e.opportunity_types)
    report.sections.append(Section(
        "Opportunity types",
        ["Opportunity type", "This period", "Previous period", "Change"],
        compare(types_now, types_before),
        widths=[3, 1.2, 1.2, 1],
    ))

    orgs_now = Counter(e.organization.name for e in current)
    orgs_before = Counter(e.organization.name for e in previous)
    top_orgs = [r for r in compare(orgs_now, orgs_before) if r[1] >= 2][:15]
    report.sections.append(Section(
        "Organizations mentioned more than once",
        ["Organization", "This period", "Previous period", "Change"],
        top_orgs,
        intro="Organizations that came up in two or more entries this period.",
        empty_text="No organization came up more than once this period.",
        widths=[3, 1.2, 1.2, 1],
    ))
    return report


def _grouped_type_names(entry, group):
    return ", ".join(t.name for t in entry.opportunity_types if t.report_group == group)


def funding_report(date_from, date_to, cluster_ids):
    entries = _entries(
        *_in_period(date_from, date_to), *_cluster_filter(cluster_ids), _type_group_filter("funding"),
    )
    report = Report("funding", SPECS["funding"].title, _period_text(date_from, date_to), _filters_text(cluster_ids))
    by_type = Counter(t.name for e in entries for t in e.opportunity_types if t.report_group == "funding")
    open_entries = [e for e in entries if e.follow_up_status in OPEN_STATUSES]
    report.summary = [("Funding leads", len(entries)), ("Still open", len(open_entries))] + list(by_type.most_common())

    def rows(items):
        return [[
            _fmt(e.entry_date),
            e.organization.name,
            _grouped_type_names(e, "funding"),
            _short(e.description, 350),
            _short(e.next_step, 200),
            _contact_text(e),
            f"{STATUS_LABELS.get(e.follow_up_status)}\n{PRIORITY_LABELS.get(e.priority)} priority"
            + (f"\nby {_fmt(e.follow_up_date)}" if e.follow_up_date else ""),
        ] for e in items]

    columns = ["Date", "Organization", "Type", "Description", "Next step", "Contact", "Follow-up"]
    widths = [1.1, 1.6, 1.3, 3.2, 2.0, 1.6, 1.2]
    priority_order = {"high": 0, "normal": 1, "low": 2}
    open_entries.sort(key=lambda e: (priority_order.get(e.priority, 1), e.follow_up_date or date.max))
    report.sections.append(Section(
        "Open funding leads", columns, rows(open_entries), widths=widths,
        intro="High priority first, then by follow-up date.",
        empty_text="No open funding leads in this period.",
    ))
    closed = [e for e in entries if e.follow_up_status not in OPEN_STATUSES]
    if closed:
        report.sections.append(Section("Closed or no action needed", columns, rows(closed), widths=widths))
    return report


def partnership_report(date_from, date_to, cluster_ids):
    entries = _entries(
        *_in_period(date_from, date_to), *_cluster_filter(cluster_ids), _type_group_filter("partnership"),
    )
    report = Report("partnership", SPECS["partnership"].title, _period_text(date_from, date_to),
                    _filters_text(cluster_ids))

    by_org = defaultdict(list)
    for e in entries:
        by_org[e.organization.name].append(e)
    report.summary = [
        ("Partnership leads", len(entries)),
        ("Organizations", len(by_org)),
        ("Still open", sum(e.follow_up_status in OPEN_STATUSES for e in entries)),
    ]

    org_rows = []
    for name, items in sorted(by_org.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())):
        latest = max(items, key=lambda e: (e.entry_date, e.id))
        clusters = sorted({c.name for e in items for c in e.clusters})
        contacts = sorted({e.contact.name for e in items if e.contact})
        open_count = sum(e.follow_up_status in OPEN_STATUSES for e in items)
        org_rows.append([
            name, len(items), _fmt(latest.entry_date), ", ".join(clusters), ", ".join(contacts),
            _short(latest.next_step, 220), f"{open_count} open" if open_count else "None open",
        ])
    report.sections.append(Section(
        "Leads by organization",
        ["Organization", "Leads", "Latest", "Clusters", "Contacts", "Latest next step", "Follow-up"],
        org_rows,
        widths=[1.8, 0.7, 1.1, 1.8, 1.5, 3.0, 1.0],
        empty_text="No partnership leads in this period.",
    ))
    report.sections.append(Section(
        "All partnership entries",
        ["Date", "Organization", "Type", "Description", "Next step", "Status"],
        [[
            _fmt(e.entry_date), e.organization.name, _grouped_type_names(e, "partnership"),
            _short(e.description, 350), _short(e.next_step, 200),
            STATUS_LABELS.get(e.follow_up_status),
        ] for e in sorted(entries, key=lambda e: (e.organization.name.lower(), e.entry_date))],
        widths=[1.1, 1.7, 1.5, 3.6, 2.2, 1.0],
        empty_text="No partnership leads in this period.",
    ))
    return report


def followups_report(date_from, date_to, cluster_ids, today=None):
    today = today or date.today()
    soon = today + timedelta(days=14)
    entries = _entries(
        Entry.follow_up_status.in_(OPEN_STATUSES),
        *_cluster_filter(cluster_ids),
        order=(Entry.follow_up_date.is_(None), Entry.follow_up_date, Entry.entry_date.desc()),
    )
    overdue = [e for e in entries if e.follow_up_date and e.follow_up_date < today]
    due_soon = [e for e in entries if e.follow_up_date and today <= e.follow_up_date <= soon]
    high_other = [e for e in entries if e.priority == "high" and not (e.follow_up_date and e.follow_up_date <= soon)]

    report = Report("followups", SPECS["followups"].title, f"As of {_fmt(today)}", _filters_text(cluster_ids))
    report.summary = [
        ("Overdue", len(overdue)),
        ("Due in 14 days", len(due_soon)),
        ("Other high priority", len(high_other)),
        ("All open follow-ups", len(entries)),
    ]

    def rows(items):
        return [[
            _fmt(e.follow_up_date) or "No date",
            e.organization.name,
            _short(e.next_step, 260) or _short(e.description, 200),
            _names(e.opportunity_types),
            PRIORITY_LABELS.get(e.priority),
            STATUS_LABELS.get(e.follow_up_status),
            e.created_by.display_name,
        ] for e in items]

    columns = ["Follow up by", "Organization", "Next step", "Opportunity types", "Priority", "Status", "Added by"]
    widths = [1.1, 1.7, 3.6, 1.9, 0.8, 1.0, 1.3]
    report.sections.append(Section("Overdue", columns, rows(overdue), widths=widths,
                                   empty_text="Nothing overdue."))
    report.sections.append(Section("Due in the next 14 days", columns, rows(due_soon), widths=widths,
                                   empty_text="Nothing due in the next two weeks."))
    report.sections.append(Section("Other high-priority follow-ups", columns, rows(high_other), widths=widths,
                                   intro="High priority with no follow-up date, or one more than two weeks away.",
                                   empty_text="No other high-priority follow-ups."))
    return report


BUILDERS = {
    "recent": recent_report,
    "trends": trends_report,
    "funding": funding_report,
    "partnership": partnership_report,
    "followups": followups_report,
}


def build_report(key, date_from, date_to, cluster_ids):
    return BUILDERS[key](date_from, date_to, cluster_ids)
