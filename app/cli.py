"""Command-line helpers: `flask seed` and `flask create-admin`."""
import getpass

import click
from sqlalchemy import select

from .extensions import db
from .models import Cluster, OpportunityType, User

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


def seed_lookups():
    """Add the default clusters and opportunity types. Safe to run repeatedly."""
    added = 0
    for model, names in ((Cluster, DEFAULT_CLUSTERS), (OpportunityType, DEFAULT_OPPORTUNITY_TYPES)):
        existing = set(db.session.scalars(select(model.name)))
        for order, name in enumerate(names, start=1):
            if name not in existing:
                db.session.add(model(name=name, sort_order=order * 10))
                added += 1
    db.session.commit()
    return added


def register_cli(app):
    @app.cli.command("seed")
    def seed():
        """Load the default clusters and opportunity types."""
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
        db.session.commit()
        click.echo(f"Administrator ready: {email}")
