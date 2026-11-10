"""Command-line helpers: `flask seed` and `flask create-admin`."""
import getpass

import click
from sqlalchemy import select

from .extensions import db
from .models import Cluster, FollowUpStatus, OpportunityType, Priority, User

DEFAULT_CLUSTERS = [
    "Agriculture",
    "Energy",
    "Health Care",
    "Aero/Defence",
    "Transportation & Logistics",
    "Technology",
    "Tourism",
    "Trades",
    "Non-profits",
    "Governments",
]

DEFAULT_OPPORTUNITY_TYPES = [
    "Potential donor",
    "Potential sponsor",
    "Grant opportunity",
    "Partnership opportunity",
    "Workforce/training need",
    "Industry intelligence",
    "Engagement event",
    "Government relations opportunity",
    "Applied research opportunity",
]

# Which opportunity types feed the funding and partnership reports by default.
# Admins can change this on the Opportunity types page.
DEFAULT_REPORT_GROUPS = {
    "Potential donor": "funding",
    "Potential sponsor": "funding",
    "Grant opportunity": "funding",
    "Partnership opportunity": "partnership",
    "Applied research opportunity": "partnership",
}


# name, flags. Order is the list order.
DEFAULT_PRIORITIES = [
    ("High", {"is_high": True}),
    ("Normal", {"is_default": True}),
    ("Low", {}),
]
DEFAULT_STATUSES = [
    ("Open", {"is_open": True, "is_default": True, "colour": "amber"}),
    ("In progress", {"is_open": True, "colour": "blue"}),
    ("Done", {"is_open": False, "colour": "green"}),
    ("No action needed", {"is_open": False, "colour": "grey"}),
]


def seed_lookups():
    """Add the default lists. Safe to run repeatedly: existing values are left alone.
    Priorities and statuses are only added to an empty list, so ones an
    administrator deleted don't come back."""
    added = 0
    for model, names in ((Cluster, DEFAULT_CLUSTERS), (OpportunityType, DEFAULT_OPPORTUNITY_TYPES)):
        existing = set(db.session.scalars(select(model.name)))
        for order, name in enumerate(names, start=1):
            if name not in existing:
                item = model(name=name, sort_order=order * 10)
                if model is OpportunityType:
                    item.report_group = DEFAULT_REPORT_GROUPS.get(name)
                db.session.add(item)
                added += 1
    for model, rows in ((Priority, DEFAULT_PRIORITIES), (FollowUpStatus, DEFAULT_STATUSES)):
        if db.session.scalar(select(model.id).limit(1)) is None:
            for order, (name, flags) in enumerate(rows, start=1):
                db.session.add(model(name=name, sort_order=order * 10, **flags))
                added += 1
    db.session.commit()
    return added


def register_cli(app):
    @app.cli.command("seed")
    def seed():
        """Load the default lists (clusters, opportunity types, priorities, statuses)."""
        added = seed_lookups()
        click.echo(f"Seed complete: {added} new lookup values.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Display name")
    @click.option("--password", default=None, help="Omit to be prompted securely.")
    def create_admin(email, name, password):
        """Create (or promote) an administrator with a local password."""
        email = email.strip().lower()
        if password is None:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Repeat password: "):
                raise click.ClickException("Passwords do not match.")
        if len(password) < app.config["MIN_PASSWORD_LENGTH"]:
            raise click.ClickException(
                f"Password must be at least {app.config['MIN_PASSWORD_LENGTH']} characters."
            )
        user = db.session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name=name)
            db.session.add(user)
        user.display_name = name
        user.is_admin = True
        user.is_active_flag = True
        user.set_password(password)
        # Also clears a lockout, so this doubles as "I'm locked out" recovery.
        user.auth_provider = "local"
        user.must_change_password = False
        user.failed_login_count = 0
        user.locked_until = None
        db.session.commit()
        click.echo(f"Administrator ready: {email}")
