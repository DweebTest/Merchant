"""Database models for Merchant.

Step 1 creates every table the app needs, so later steps add screens rather
than reshaping the database:

* users, groups, permissions: who can sign in and, later, who can do what
* clusters, opportunity_types: admin-editable lookup lists
* organizations, contacts, entries, attachments: the knowledge base itself
"""
import secrets
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import event, select
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- Association tables -----------------------------------------------------

user_groups = db.Table(
    "user_groups",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    db.Column("group_id", db.Integer, db.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)

group_permissions = db.Table(
    "group_permissions",
    db.Column("group_id", db.Integer, db.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

entry_clusters = db.Table(
    "entry_clusters",
    db.Column("entry_id", db.Integer, db.ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True),
    db.Column("cluster_id", db.Integer, db.ForeignKey("clusters.id", ondelete="RESTRICT"), primary_key=True),
)

entry_opportunity_types = db.Table(
    "entry_opportunity_types",
    db.Column("entry_id", db.Integer, db.ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True),
    db.Column("opportunity_type_id", db.Integer, db.ForeignKey("opportunity_types.id", ondelete="RESTRICT"), primary_key=True),
)


# --- People and access ------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    display_name = db.Column(db.String(120), nullable=False)
    # Null for users who only sign in through single sign-on.
    password_hash = db.Column(db.String(255))
    # "local": Merchant password (and single sign-on, if set up). "sso": single sign-on only.
    auth_provider = db.Column(db.String(20), nullable=False, default="local")
    # Permanent Microsoft Entra object id, set at first Microsoft sign-in.
    external_id = db.Column(db.String(64), unique=True)
    # SAML NameID from the identity provider (e.g. AWS IAM Identity Center), set at first SAML sign-in.
    saml_name_id = db.Column(db.String(255), unique=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    # Part of the sign-in cookie. Changing it signs the person out everywhere
    # (done on password change, deactivation, email or sign-in method change).
    session_token = db.Column(db.String(32), nullable=False, default=lambda: secrets.token_hex(16))
    is_active_flag = db.Column("is_active", db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # Marks sample data loaded by `flask demo-data load`, so it can be removed cleanly.
    is_demo = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false(), index=True)

    groups = db.relationship("Group", secondary=user_groups, back_populates="members", order_by="Group.name")

    # Flask-Login uses this to refuse deactivated accounts.
    @property
    def is_active(self):
        return bool(self.is_active_flag)

    def get_id(self):
        # Flask-Login stores this in the session and "keep me signed in" cookie.
        return f"{self.id}:{self.session_token}"

    def end_sessions(self):
        """Sign this person out of every browser and device."""
        self.session_token = secrets.token_hex(16)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.end_sessions()

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    def is_locked(self, now=None):
        return self.locked_until is not None and self.locked_until > (now or utcnow())

    def has_permission(self, code):
        """Admins can do everything; others get what their groups grant.

        Nothing enforces permissions yet. This is the hook for when you decide
        to restrict functions to certain groups.
        """
        if self.is_admin:
            return True
        return any(p.code == code for g in self.groups for p in g.permissions)

    def __repr__(self):
        return f"<User {self.email}>"


class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255))
    # Inactive groups are hidden when choosing someone's groups, but kept.
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # Marks sample data loaded by `flask demo-data load`, so it can be removed cleanly.
    is_demo = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false(), index=True)

    members = db.relationship("User", secondary=user_groups, back_populates="groups", order_by="User.display_name")
    permissions = db.relationship("Permission", secondary=group_permissions, back_populates="groups")


class Permission(db.Model):
    """A named capability, such as "reports.run". Empty until permissions are needed."""
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True)
    description = db.Column(db.String(255))

    groups = db.relationship("Group", secondary=group_permissions, back_populates="permissions")


# --- Lookup lists -----------------------------------------------------------

class LookupMixin:
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    # Retire a value instead of deleting it, so old entries keep their tags.
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Cluster(LookupMixin, db.Model):
    __tablename__ = "clusters"


class OpportunityType(LookupMixin, db.Model):
    __tablename__ = "opportunity_types"

    REPORT_GROUPS = {"funding": "Potential funding opportunities", "partnership": "Partnership leads"}

    # Which report this type feeds, if any: "funding", "partnership" or None.
    report_group = db.Column(db.String(20), index=True)


class Priority(LookupMixin, db.Model):
    """How urgent an entry is. Higher up the list (lower sort order) is more urgent."""
    __tablename__ = "priorities"

    # Counts as "high priority" on the home page and in the priority follow-ups report.
    is_high = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # Picked for new entries.
    is_default = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())


class FollowUpStatus(LookupMixin, db.Model):
    """Where an entry's follow-up stands."""
    __tablename__ = "follow_up_statuses"

    COLOURS = {"amber": "Amber", "blue": "Blue", "green": "Green", "grey": "Grey"}

    # Still needs someone to act: counts as an open follow-up.
    is_open = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    is_default = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    colour = db.Column(db.String(10), nullable=False, default="grey", server_default="grey")


def default_choice(model):
    """The value new entries start with: the one marked default, else the first active one."""
    return (db.session.scalar(select(model).where(model.is_default.is_(True), model.is_active.is_(True)))
            or db.session.scalar(select(model).where(model.is_active.is_(True))
                                 .order_by(model.sort_order, model.name).limit(1)))


# --- Knowledge base ---------------------------------------------------------

class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    website = db.Column(db.String(500))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # Marks sample data loaded by `flask demo-data load`, so it can be removed cleanly.
    is_demo = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false(), index=True)

    contacts = db.relationship("Contact", back_populates="organization", order_by="Contact.name")
    entries = db.relationship("Entry", back_populates="organization")


class Contact(db.Model):
    __tablename__ = "contacts"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    name = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(200))
    email = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # Marks sample data loaded by `flask demo-data load`, so it can be removed cleanly.
    is_demo = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false(), index=True)

    organization = db.relationship("Organization", back_populates="contacts")


class Entry(db.Model):
    __tablename__ = "entries"

    id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.Date, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    contact_id = db.Column(db.Integer, db.ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    next_step = db.Column(db.Text)
    college_area = db.Column(db.String(150))  # optional, free text
    link_url = db.Column(db.String(1000))
    status_id = db.Column(db.Integer, db.ForeignKey("follow_up_statuses.id", ondelete="RESTRICT"), nullable=False, index=True)
    priority_id = db.Column(db.Integer, db.ForeignKey("priorities.id", ondelete="RESTRICT"), nullable=False, index=True)
    follow_up_date = db.Column(db.Date, index=True)
    # Who added it. The name is kept too, so it still shows after their account is deleted.
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_by_name = db.Column(db.String(200), nullable=False, default="", server_default="")
    # Who looks after this entry now: edits it and follows it up. Starts as
    # whoever added it; can be reassigned, for example when someone leaves.
    # Empty once that person's account is deleted (only allowed when the entry is done).
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    # Marks sample data loaded by `flask demo-data load`, so it can be removed cleanly.
    is_demo = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false(), index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    organization = db.relationship("Organization", back_populates="entries")
    contact = db.relationship("Contact")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    owner = db.relationship("User", foreign_keys=[owner_id])
    clusters = db.relationship("Cluster", secondary=entry_clusters, order_by="Cluster.sort_order")
    opportunity_types = db.relationship("OpportunityType", secondary=entry_opportunity_types, order_by="OpportunityType.sort_order")
    attachments = db.relationship("Attachment", back_populates="entry", cascade="all, delete-orphan")
    status = db.relationship("FollowUpStatus", lazy="joined")
    priority = db.relationship("Priority", lazy="joined")

    @property
    def author_name(self):
        return self.created_by.display_name if self.created_by else (self.created_by_name or "Unknown")

    @property
    def author_gone(self):
        """True when whoever added it has left (deactivated or deleted)."""
        return self.created_by is None or not self.created_by.is_active

    @property
    def owner_gone(self):
        return self.owner is None or not self.owner.is_active

    __table_args__ = (
        # Keyword search across the text fields (MySQL FULLTEXT; ignored elsewhere).
        db.Index("ft_entries_text", "description", "next_step", mysql_prefix="FULLTEXT"),
    )


class Attachment(db.Model):
    """Metadata for an uploaded file. The file itself sits in UPLOAD_FOLDER."""
    __tablename__ = "attachments"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True)
    content_type = db.Column(db.String(150))
    size_bytes = db.Column(db.BigInteger, nullable=False, default=0)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    entry = db.relationship("Entry", back_populates="attachments")
    uploaded_by = db.relationship("User")


class SavedFilter(db.Model):
    """A named knowledge base search, kept for one person or shared with everyone."""
    __tablename__ = "saved_filters"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    # The knowledge base query string, e.g. "cluster=3&status=open&range=30".
    query = db.Column(db.String(2000), nullable=False, default="")
    is_shared = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")


@event.listens_for(Entry, "before_insert")
def _entry_defaults(mapper, connection, entry):
    """Fill in the author's name, owner, status and priority when none was given."""
    author_id = entry.created_by.id if entry.created_by is not None else entry.created_by_id
    if author_id is not None and not entry.created_by_name:
        u = User.__table__
        entry.created_by_name = connection.execute(
            select(u.c.display_name).where(u.c.id == author_id)).scalar() or ""
    if entry.owner_id is None and entry.owner is None and author_id is not None:
        entry.owner_id = author_id
    for col, model in (("status_id", FollowUpStatus), ("priority_id", Priority)):
        if getattr(entry, col) is None:
            rel = entry.status if col == "status_id" else entry.priority
            if rel is not None:
                setattr(entry, col, rel.id)
                continue
            t = model.__table__
            row = connection.execute(
                select(t.c.id).where(t.c.is_active.is_(True))
                .order_by(t.c.is_default.desc(), t.c.sort_order, t.c.name).limit(1)
            ).first()
            if row:
                setattr(entry, col, row[0])
