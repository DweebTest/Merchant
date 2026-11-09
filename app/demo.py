"""Realistic sample data for demos and testing.

    flask demo-data load     add about 120 entries across the last 12 months
    flask demo-data clear    remove everything `load` added, and nothing else

Everything added is flagged is_demo, so `clear` never touches real data.
Dates are relative to today, so the reports always look current.
"""
import random
from datetime import date, timedelta

import click
from sqlalchemy import func, select

from .extensions import db
from .models import Attachment, Cluster, Contact, Entry, Group, OpportunityType, Organization, User

DEMO_PASSWORD = "Demo-pass-2026"
DEMO_EMAIL_DOMAIN = "demo.example.com"

GROUPS = {
    "Advancement": "Fundraising, donors and sponsorships",
    "Community Relations": "Community partners and engagement",
    "Continuing Education": "Workforce and customized training",
    "Applied Research": "Research partnerships with industry",
    "Leadership": "Executive team",
}

USERS = [
    ("Alex Morgan", "alex.morgan", "Advancement"),
    ("Priya Shah", "priya.shah", "Community Relations"),
    ("Jordan Lee", "jordan.lee", "Continuing Education"),
    ("Sam Okafor", "sam.okafor", "Applied Research"),
    ("Taylor Brooks", "taylor.brooks", "Leadership"),
    ("Chris Dubois", "chris.dubois", "Continuing Education"),
]

# Organization -> (clusters, website, contacts, weight). Weight makes some
# organizations come up more often, so "mentioned more than once" has content.
ORGS = {
    "Prairie Wind Energy": (["Energy", "Trades"], "https://example.com/prairiewind",
                            [("Maria Santos", "HR Director"), ("Ken Ito", "Operations Manager")], 3),
    "Solaris Grid Co-op": (["Energy"], "", [("Ben Carter", "General Manager")], 2),
    "Northern Health Foundation": (["Health Care", "Non-profits"], "https://example.com/nhf",
                                   [("Dana Wu", "Executive Director")], 3),
    "Riverside Regional Hospital": (["Health Care"], "", [("Dr. Lena Park", "Chief Nursing Officer")], 2),
    "Aero Precision Ltd": (["Aero/Defence", "Trades"], "", [("Mark Fischer", "Plant Manager")], 2),
    "Regional Airport Authority": (["Aero/Defence", "Transportation & Logistics"], "",
                                   [("Grace Liu", "VP Operations")], 1),
    "Summit Logistics": (["Transportation & Logistics"], "", [("Omar Haddad", "Talent Lead")], 2),
    "CrossRail Freight": (["Transportation & Logistics"], "", [("Ella Novak", "Training Coordinator")], 1),
    "TechNorth Accelerator": (["Technology"], "https://example.com/technorth",
                              [("Ravi Menon", "Program Director")], 3),
    "SkyMap Drones": (["Technology", "Agriculture"], "", [("Hannah Cole", "CEO")], 2),
    "ByteForge Software": (["Technology"], "", [("Luis Ortega", "CTO")], 2),
    "Valley Growers Co-op": (["Agriculture"], "", [("Peter Janssen", "Board Chair")], 2),
    "Green Acres Agri-Food": (["Agriculture"], "", [("Nadia Rahman", "Innovation Manager")], 1),
    "Lakeside Tourism Board": (["Tourism"], "", [("Chloe Martin", "Executive Director")], 2),
    "Northern Lights Resort": (["Tourism"], "", [("Ian McLeod", "General Manager")], 1),
    "BuildRight Trades Union": (["Trades"], "", [("Frank Kowalski", "Training Director")], 2),
    "Metro Electrical Contractors": (["Trades", "Energy"], "", [("Aisha Bello", "Owner")], 1),
    "United Way of the Valley": (["Non-profits"], "", [("Rosa Alvarez", "Community Impact Lead")], 1),
    "Community Food Bank": (["Non-profits"], "", [("Tom Reid", "Volunteer Coordinator")], 1),
    "City of Riverton": (["Governments"], "", [("Councillor Jean Roy", "Economic Development Chair")], 2),
    "Provincial Ministry of Labour": (["Governments"], "", [("Sarah Bennett", "Program Officer")], 2),
    "Regional Economic Development Office": (["Governments"], "",
                                             [("Kofi Mensah", "Business Retention Officer")], 2),
}

# Opportunity type -> (description templates, next steps). {org} is filled in.
NOTES = {
    "Potential donor": (
        ["{org}'s board chair mentioned they are setting up a scholarship fund and asked how named awards work.",
         "At the gala, {org} signalled interest in a multi-year gift toward the new skills centre.",
         "{org} is reviewing its community giving priorities for next year and the college came up."],
        ["Advancement to send the named-award options.", "Arrange a campus tour for the board chair.",
         "Prepare a short case for support."]),
    "Potential sponsor": (
        ["{org} asked about sponsoring the spring industry showcase and having a booth.",
         "{org} wants visibility with students and offered to sponsor the hackathon prizes.",
         "Marketing lead at {org} is looking for sponsorships that reach graduates."],
        ["Send the sponsorship package.", "Confirm sponsorship levels and deadlines.",
         "Connect them with Student Services."]),
    "Grant opportunity": (
        ["{org} shared that a new intake for the skills development grant opens next quarter.",
         "{org} is looking for a post-secondary partner for a federal innovation grant application.",
         "Heard from {org} about a rural workforce fund with a short application window."],
        ["Grants office to review eligibility.", "Request the program guidelines.",
         "Set up a call to scope a joint application."]),
    "Partnership opportunity": (
        ["{org} wants a formal partnership for co-op placements and guest instructors.",
         "{org} proposed sharing equipment and lab space for training.",
         "Talked with {org} about an articulation agreement and joint marketing."],
        ["Draft a memorandum of understanding.", "Meet with the dean to discuss fit.",
         "Invite them to the program advisory committee."]),
    "Workforce/training need": (
        ["{org} needs 30 to 40 new technicians in the next two years and has no local pipeline.",
         "{org} says supervisors need leadership training; they would pay for a custom cohort.",
         "{org} is struggling to hire certified staff and asked about fast-track options."],
        ["Continuing Education to scope a custom cohort.", "Send the corporate training catalogue.",
         "Book a needs-assessment meeting."]),
    "Industry intelligence": (
        ["{org} expects major expansion next year and is lobbying for infrastructure funding.",
         "According to {org}, automation is changing which entry-level roles they hire for.",
         "{org} mentioned supply-chain delays are pushing them to source and train locally."],
        ["Share with program heads.", "Raise at the next leadership meeting.", ""]),
    "Engagement event": (
        ["Met {org} at the chamber breakfast; they want to stay connected with the college.",
         "{org} invited the college to speak at their annual member forum.",
         "Hosted {org} for a campus tour of the trades building."],
        ["Add to the newsletter list.", "Confirm a speaker for the forum.", "Send a thank-you note."]),
    "Government relations opportunity": (
        ["{org} is consulting on a regional workforce strategy and wants post-secondary input.",
         "{org} flagged an upcoming funding announcement relevant to the college's capital plan.",
         "Staff at {org} asked for data on graduate employment in the region."],
        ["Leadership to submit a response to the consultation.", "Brief the president.",
         "Institutional research to pull graduate outcomes."]),
    "Applied research opportunity": (
        ["{org} has a production problem and asked whether faculty could help test solutions.",
         "{org} is interested in a student research project on data analysis for their operations.",
         "{org} wants to pilot new technology and needs a neutral research partner."],
        ["Introduce to the Applied Research office.", "Check fit with an engage-type grant.",
         "Set up a scoping call with faculty."]),
}

# Types that fit each cluster best, so combinations look plausible.
CLUSTER_TYPES = {
    "Energy": ["Workforce/training need", "Partnership opportunity", "Industry intelligence",
               "Applied research opportunity", "Potential sponsor"],
    "Health Care": ["Potential donor", "Grant opportunity", "Workforce/training need", "Partnership opportunity"],
    "Aero/Defence": ["Workforce/training need", "Applied research opportunity", "Partnership opportunity"],
    "Transportation & Logistics": ["Workforce/training need", "Industry intelligence", "Partnership opportunity"],
    "Technology": ["Applied research opportunity", "Partnership opportunity", "Potential sponsor",
                   "Grant opportunity", "Industry intelligence"],
    "Agriculture": ["Applied research opportunity", "Grant opportunity", "Industry intelligence"],
    "Tourism": ["Engagement event", "Potential sponsor", "Workforce/training need"],
    "Trades": ["Workforce/training need", "Partnership opportunity", "Potential sponsor"],
    "Non-profits": ["Potential donor", "Engagement event", "Grant opportunity"],
    "Governments": ["Government relations opportunity", "Grant opportunity", "Industry intelligence"],
}

# Clusters that come up more often recently, so the trends report has a story.
RISING = {"Energy", "Technology", "Health Care"}


def demo_present():
    return db.session.scalar(select(func.count(Entry.id)).where(Entry.is_demo.is_(True))) > 0


def load_demo(entries=120, seed=2026, today=None):
    """Add the demo data. Returns a dict of counts."""
    today = today or date.today()
    rng = random.Random(seed)
    clusters = {c.name: c for c in db.session.scalars(select(Cluster))}
    types = {t.name: t for t in db.session.scalars(select(OpportunityType))}
    if not clusters or not types:
        raise click.ClickException("Run `flask seed` first to load clusters and opportunity types.")

    counts = {"users": 0, "groups": 0, "organizations": 0, "contacts": 0, "entries": 0}

    groups = {}
    for name, description in GROUPS.items():
        group = db.session.scalar(select(Group).where(Group.name == name))
        if group is None:
            group = Group(name=name, description=description, is_demo=True)
            db.session.add(group)
            counts["groups"] += 1
        groups[name] = group

    users = []
    for display_name, handle, group_name in USERS:
        email = f"{handle}@{DEMO_EMAIL_DOMAIN}"
        user = db.session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name=display_name, is_demo=True)
            user.set_password(DEMO_PASSWORD)
            db.session.add(user)
            counts["users"] += 1
        if groups[group_name] not in user.groups:
            user.groups.append(groups[group_name])
        users.append(user)

    orgs = {}
    for name, (org_clusters, website, contacts, _weight) in ORGS.items():
        org = db.session.scalar(select(Organization).where(func.lower(Organization.name) == name.lower()))
        if org is None:
            org = Organization(name=name, website=website or None, is_demo=True)
            db.session.add(org)
            counts["organizations"] += 1
        people = []
        for contact_name, title in contacts:
            contact = next((c for c in org.contacts if c.name.lower() == contact_name.lower()), None)
            if contact is None:
                slug = contact_name.lower().replace("dr. ", "").replace("councillor ", "").replace(" ", ".")
                contact = Contact(name=contact_name, title=title, organization=org, is_demo=True,
                                  email=f"{slug}@example.com", phone=f"555-01{rng.randint(10, 99)}")
                db.session.add(contact)
                counts["contacts"] += 1
            people.append(contact)
        orgs[name] = (org, org_clusters, people)
    db.session.flush()

    names = list(ORGS)
    weights = [ORGS[n][3] for n in names]
    for _ in range(entries):
        org_name = rng.choices(names, weights)[0]
        org, org_clusters, people = orgs[org_name]
        # Rising clusters lean recent; the rest spread across the year.
        if RISING & set(org_clusters):
            days_ago = int(rng.triangular(0, 365, 0))
        else:
            days_ago = int(rng.uniform(0, 365))
        entry_date = today - timedelta(days=days_ago)

        choices = sorted({t for c in org_clusters for t in CLUSTER_TYPES.get(c, [])})
        picked = rng.sample(choices, k=min(len(choices), rng.choice([1, 1, 2])))
        main_type = picked[0]
        templates, steps = NOTES[main_type]
        description = rng.choice(templates).format(org=org_name)
        next_step = rng.choice(steps) or None

        # Older items are mostly closed; recent ones mostly open.
        if days_ago > 120:
            status = rng.choices(["done", "no_action", "open", "in_progress"], [8, 3, 1, 1])[0]
        else:
            status = rng.choices(["open", "in_progress", "done", "no_action"], [5, 3, 2, 1])[0]
        priority = rng.choices(["high", "normal", "low"], [2, 5, 2])[0]
        follow_up = None
        if status in ("open", "in_progress") and rng.random() < 0.7:
            if days_ago > 45:
                # Long-running items: a follow-up around now, a few overdue.
                follow_up = today + timedelta(days=rng.randint(-14, 30))
            else:
                follow_up = entry_date + timedelta(days=rng.randint(7, 45))

        entry = Entry(
            is_demo=True,
            entry_date=entry_date,
            description=description,
            organization=org,
            contact=rng.choice(people) if people and rng.random() < 0.7 else None,
            next_step=next_step,
            college_area=rng.choice([None, None, "Business", "Health Sciences", "Trades & Technology",
                                     "Continuing Education"]),
            link_url=ORGS[org_name][1] or None,
            follow_up_status=status,
            priority=priority,
            follow_up_date=follow_up,
            created_by=rng.choice(users),
            clusters=[clusters[c] for c in org_clusters if c in clusters],
            opportunity_types=[types[t] for t in picked if t in types],
        )
        db.session.add(entry)
        counts["entries"] += 1

    db.session.commit()
    return counts


def clear_demo():
    """Remove demo rows. Anything real that points at a demo row keeps it."""
    counts = {"entries": 0, "contacts": 0, "organizations": 0, "groups": 0, "users": 0, "kept": 0}

    for entry in db.session.scalars(select(Entry).where(Entry.is_demo.is_(True))):
        db.session.delete(entry)
        counts["entries"] += 1
    db.session.flush()

    for contact in db.session.scalars(select(Contact).where(Contact.is_demo.is_(True))):
        in_use = db.session.scalar(select(func.count(Entry.id)).where(Entry.contact_id == contact.id))
        if in_use:
            counts["kept"] += 1
        else:
            db.session.delete(contact)
            counts["contacts"] += 1
    db.session.flush()

    for org in db.session.scalars(select(Organization).where(Organization.is_demo.is_(True))):
        in_use = db.session.scalar(select(func.count(Entry.id)).where(Entry.organization_id == org.id))
        has_contacts = db.session.scalar(select(func.count(Contact.id)).where(Contact.organization_id == org.id))
        if in_use or has_contacts:
            counts["kept"] += 1
        else:
            db.session.delete(org)
            counts["organizations"] += 1
    db.session.flush()

    for user in db.session.scalars(select(User).where(User.is_demo.is_(True))):
        in_use = db.session.scalar(select(func.count(Entry.id)).where(Entry.created_by_id == user.id))
        uploads = db.session.scalar(select(func.count(Attachment.id)).where(Attachment.uploaded_by_id == user.id))
        if in_use or uploads:
            counts["kept"] += 1
        else:
            db.session.delete(user)
            counts["users"] += 1

    for group in db.session.scalars(select(Group).where(Group.is_demo.is_(True))):
        real_members = [u for u in group.members if not u.is_demo]
        if real_members:
            counts["kept"] += 1
        else:
            db.session.delete(group)
            counts["groups"] += 1

    db.session.commit()
    return counts


def register_demo_cli(app):
    @app.cli.group("demo-data")
    def demo_data():
        """Load or remove sample data for demos."""

    @demo_data.command("load")
    @click.option("--entries", default=120, show_default=True, help="How many sample entries to add.")
    def load(entries):
        """Add realistic sample organizations, people and entries."""
        if demo_present():
            raise click.ClickException("Demo data is already loaded. Run `flask demo-data clear` first.")
        counts = load_demo(entries=entries)
        click.echo(
            f"Added {counts['entries']} entries, {counts['organizations']} organizations, "
            f"{counts['contacts']} contacts, {counts['users']} users and {counts['groups']} groups."
        )
        click.echo(f"Demo users sign in as e.g. alex.morgan@{DEMO_EMAIL_DOMAIN} with password {DEMO_PASSWORD}")

    @demo_data.command("clear")
    @click.confirmation_option(prompt="Remove all demo data? Your own data is not touched.")
    def clear():
        """Remove everything `load` added. Real data is never touched."""
        counts = clear_demo()
        click.echo(
            f"Removed {counts['entries']} entries, {counts['organizations']} organizations, "
            f"{counts['contacts']} contacts, {counts['users']} users and {counts['groups']} groups."
        )
        if counts["kept"]:
            click.echo(f"Kept {counts['kept']} demo records because your own entries or people use them.")
