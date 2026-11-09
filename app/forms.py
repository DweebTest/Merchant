from flask import current_app
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    EmailField,
    IntegerField,
    PasswordField,
    SelectMultipleField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError
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
    submit = SubmitField("Save")


class ConfirmForm(FlaskForm):
    """Empty form used for CSRF-protected POST buttons."""
    submit = SubmitField("Confirm")
