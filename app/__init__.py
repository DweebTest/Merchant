import os

from flask import Flask, redirect, render_template, request, url_for
from flask_login import current_user

from .config import Config
from .extensions import csrf, db, login_manager, migrate


def create_app(config_class=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class or Config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env and fill it in.")

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (register models with SQLAlchemy)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .entries import bp as entries_bp
    from .main import bp as main_bp
    from .reports import bp as reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(entries_bp, url_prefix="/entries")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(main_bp)

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def friendly_error(error):
        messages = {
            403: "You don't have permission to do that.",
            404: "That page doesn't exist, or the entry was deleted.",
            413: f"That upload is too large. The limit is {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB in total.",
        }
        return render_template("error.html", code=error.code, message=messages[error.code]), error.code

    @app.before_request
    def force_password_change():
        """Users given a temporary password must set their own before going on."""
        if (
            current_user.is_authenticated
            and current_user.must_change_password
            and request.endpoint not in {"auth.change_password", "auth.logout", "static"}
        ):
            return redirect(url_for("auth.change_password"))

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    # Portable date formats (strftime's %-d doesn't work on Windows).
    @app.template_filter("shortdate")
    def shortdate(d):
        return f"{d:%b} {d.day}, {d.year}" if d else ""

    @app.template_filter("longdate")
    def longdate(d):
        return f"{d:%A}, {d:%B} {d.day}, {d.year}" if d else ""

    from .cli import register_cli
    from .demo import register_demo_cli
    register_cli(app)
    register_demo_cli(app)

    return app
