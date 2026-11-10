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

    # Email-and-password sign-in. Turn off once everyone uses Microsoft sign-in.
    LOCAL_LOGIN_ENABLED = _bool("LOCAL_LOGIN_ENABLED", True)

    # Microsoft Entra ID sign-in. Shown on the sign-in page once all three are set.
    ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID", "").strip()
    ENTRA_CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID", "").strip()
    ENTRA_CLIENT_SECRET = os.environ.get("ENTRA_CLIENT_SECRET", "").strip()
    # Optional: the exact redirect URI registered in Entra. Defaults to
    # <this site>/login/microsoft/callback.
    ENTRA_REDIRECT_URI = os.environ.get("ENTRA_REDIRECT_URI", "").strip()
    ENTRA_AUTHORITY_HOST = os.environ.get("ENTRA_AUTHORITY_HOST", "https://login.microsoftonline.com").rstrip("/")

    # SAML 2.0 single sign-on (AWS IAM Identity Center, or any SAML identity
    # provider). Turned on by giving the identity provider's metadata, either as
    # a URL or as a downloaded XML file. See docs/aws-lab.md.
    SAML_IDP_METADATA_URL = os.environ.get("SAML_IDP_METADATA_URL", "").strip()
    SAML_IDP_METADATA_FILE = os.environ.get("SAML_IDP_METADATA_FILE", "").strip()
    # Text on the sign-in button.
    SAML_BUTTON_LABEL = os.environ.get("SAML_BUTTON_LABEL", "Sign in with AWS").strip() or "Sign in with AWS"
    # Optional: Merchant's public address, e.g. https://merchant.example.edu, if
    # it can't be worked out from requests. Used for the SAML entity id and
    # reply (ACS) address.
    SAML_SP_BASE_URL = os.environ.get("SAML_SP_BASE_URL", "").strip().rstrip("/")

    # Set to 1 when Merchant runs behind a reverse proxy (IIS, nginx, a load
    # balancer) that handles HTTPS, so links and redirects use https://.
    TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES", "0"))

    # Look of the site for anyone who hasn't picked one: "orbit" or "classic"
    # (or the name of a theme in app/static/themes-local/).
    DEFAULT_THEME = os.environ.get("DEFAULT_THEME", "orbit").strip().lower()


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
