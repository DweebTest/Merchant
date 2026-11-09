"""Test fixtures.

By default tests use an in-memory SQLite database so they run anywhere.
To run them against MySQL instead:
    TEST_DATABASE_URL=mysql+pymysql://user:pass@localhost/merchant_test pytest
"""
import pytest

from app import create_app
from app.cli import seed_lookups
from app.config import TestConfig
from app.extensions import db as _db
from app.models import User


@pytest.fixture()
def app(tmp_path):
    class Cfg(TestConfig):
        UPLOAD_FOLDER = str(tmp_path / "uploads")

    app = create_app(Cfg)
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        seed_lookups()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(email="user@example.com", password="correct-horse-1", admin=False, **kw):
    user = User(email=email, display_name=kw.pop("name", email.split("@")[0]), is_admin=admin, **kw)
    user.set_password(password)
    _db.session.add(user)
    _db.session.commit()
    return user


def login(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture()
def admin(app):
    return make_user("admin@example.com", "admin-password-1", admin=True, name="Admin")


@pytest.fixture()
def admin_client(client, admin):
    login(client, "admin@example.com", "admin-password-1")
    return client
