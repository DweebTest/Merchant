"""Application configuration.

Every setting comes from environment variables (or a .env file), so the same
code runs with the database on this machine or on a separate server. To move
MySQL to another host, change DB_HOST (or DATABASE_URL); nothing else changes.
"""
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Load .env before the settings below are read.
load_dotenv()


def _bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_database_url():
    """DATABASE_URL wins if set; otherwise build one from the DB_* parts."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    user = quote_plus(os.environ.get("DB_USER", "merchant"))
    password = quote_plus(os.environ.get("DB_PASSWORD", ""))
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "3306")
    name = os.environ.get("DB_NAME", "merchant")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    SQLALCHEMY_DATABASE_URI = build_database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {
        # Drop dead connections cleanly when MySQL is on another server.
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Attachments live in a folder on the database server. On a single machine
    # this is a local folder; when split, mount the share at this path.
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(os.getcwd(), "instance", "uploads")
    )
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024

    # Login hardening
    MAX_FAILED_LOGINS = int(os.environ.get("MAX_FAILED_LOGINS", "5"))
    LOCKOUT_MINUTES = int(os.environ.get("LOCKOUT_MINUTES", "15"))
    MIN_PASSWORD_LENGTH = int(os.environ.get("MIN_PASSWORD_LENGTH", "10"))

    # Cookies: set SESSION_COOKIE_SECURE=true once the site is served over HTTPS.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True

    # Authentication methods. Entra SSO arrives in step 4; local login stays
    # available so you can test, and can be switched off later.
    LOCAL_LOGIN_ENABLED = _bool("LOCAL_LOGIN_ENABLED", True)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
