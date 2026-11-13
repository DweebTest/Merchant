from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import MultipleFileField
from wtforms import (
    BooleanField,
    DateField,
    EmailField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, URL, ValidationError
from wtforms.widgets import CheckboxInput, ListWidget


class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


def password_length(form, field):
    minimum = current_app.config["MIN_PASSWORD_LENGTH"]
    if field.data and len(field.data) < minimum:
        raise ValidationError(f"Use at least {minimum} characters.")


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), password_length])
    confirm = PasswordField(
        "Repeat new password", validators=[DataRequired(), EqualTo("new_password", "Passwords do not match.")]
    )
    submit = SubmitField("Change password")


class UserForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    display_name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    password = PasswordField(
        "Temporary password",
        validators=[Optional(), password_length],
        description="They'll be asked to choose their own at first sign-in.",
    )
    auth_provider = SelectField(
        "Sign-in method",
        choices=[("local", "Merchant password (and single sign-on, if it's set up)"),
                 ("sso", "Single sign-on only (Microsoft or AWS, no password)")],
        default="local",
        description="Single sign-on matches people by this email address the first time.",
    )
    is_admin = BooleanField("Administrator")
    is_active = BooleanField("Active", default=True)
    groups = MultiCheckboxField("Groups", coerce=int)
    submit = SubmitField("Save")


class GroupForm(FlaskForm):
    name = StringField("Group name", validators=[DataRequired(), Length(max=100)])
    description = StringField("Description", validators=[Optional(), Length(max=255)])
    members = MultiCheckboxField("Members", coerce=int)
    submit = SubmitField("Save")


class LookupForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=100)])
    sort_order = IntegerField("Sort order", default=0, validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    # Only shown for opportunity types.
    report_group = SelectField(
        "Include in report",
        choices=[("", "Neither"), ("funding", "Potential funding opportunities"), ("partnership", "Partnership leads")],
        default="",
        description="Entries with this type appear in the chosen report.",
    )
    # Only shown for priorities.
    is_high = BooleanField("Counts as high priority",
                           description="Shown on the home page and in the Priority follow-ups report.")
    # Only shown for follow-up statuses.
    is_open = BooleanField("Still needs follow-up",
                           description="Entries with this status count as open follow-ups. Untick for statuses like Done.")
    colour = SelectField("Tag colour", choices=[("amber", "Amber"), ("blue", "Blue"), ("green", "Green"), ("grey", "Grey")],
                         default="grey")
    # Priorities and statuses.
    is_default = BooleanField("Default for new entries")
    submit = SubmitField("Save")


class ConfirmForm(FlaskForm):
    """Empty form used for CSRF-protected POST buttons."""
    submit = SubmitField("Confirm")


def at_least_one(form, field):
    if not field.data:
        raise ValidationError("Pick at least one.")


class EntryForm(FlaskForm):
    entry_date = DateField("Date", validators=[DataRequired()])
    description = TextAreaField(
        "Brief description",
        validators=[DataRequired(), Length(max=10000)],
        description="What did you learn or hear? Who said it, and why does it matter?",
    )
    organization = StringField("Organization", validators=[DataRequired(), Length(max=255)])
    contact_name = StringField("Contact name", validators=[Optional(), Length(max=200)])
    contact_title = StringField("Contact title", validators=[Optional(), Length(max=200)])
    contact_email = EmailField("Contact email", validators=[Optional(), Email(), Length(max=255)])
    contact_phone = StringField("Contact phone", validators=[Optional(), Length(max=50)])
    clusters = MultiCheckboxField("Economic clusters", coerce=int, validators=[at_least_one])
    opportunity_types = MultiCheckboxField("Opportunity types", coerce=int, validators=[at_least_one])
    next_step = TextAreaField("Suggested next step", validators=[Optional(), Length(max=5000)])
    college_area = StringField("Area impacted", validators=[Optional(), Length(max=150)])
    # Choices come from the admin-editable lists (set in the view).
    priority_id = SelectField("Priority", coerce=int, validate_choice=True)
    status_id = SelectField("Follow-up status", coerce=int, validate_choice=True)
    follow_up_date = DateField("Follow up by", validators=[Optional()])
    link_url = StringField(
        "Link", validators=[Optional(), URL(require_tld=False, message="Enter a full web address starting with http:// or https://"), Length(max=1000)]
    )
    attachments = MultipleFileField("Attach files")
    submit = SubmitField("Save entry")
