import os
from pathlib import Path
from flask import Flask, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per hour"])

def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    base = Path(app.root_path).parent
    instance = Path(app.instance_path)
    instance.mkdir(parents=True, exist_ok=True)
    upload_dir = Path(os.getenv("UPLOAD_DIR", str(base / "private_uploads")))
    if not upload_dir.is_absolute():
        upload_dir = (base / upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    db_url = os.getenv("DATABASE_URL", f"sqlite:///{instance / 'mrisho_gambo.db'}")
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
        # Keep relative SQLite paths anchored to the project root.
        relative = db_url[len("sqlite:///"):]
        if not relative.startswith("/"):
            db_url = "sqlite:///" + str((base / relative).resolve())
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_DIR=str(upload_dir),
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH_MB", "8")) * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
        REMEMBER_COOKIE_HTTPONLY=True,
        WTF_CSRF_TIME_LIMIT=3600,
        SCHOOL_NAME=os.getenv("SCHOOL_NAME", "Mrisho Gambo Secondary School"),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"
    login_manager.login_message_category = "warning"
    csrf.init_app(app)
    limiter.init_app(app)

    from . import models
    from .routes import main
    app.register_blueprint(main)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    with app.app_context():
        db.create_all()
        from .models import User, AcademicYear, SystemSetting
        # Bootstrap admin is created once only. Change password immediately after first login.
        username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
        if password and not User.query.filter_by(username=username).first():
            user = User(username=username, full_name="System Administrator", role="admin", active=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        if not AcademicYear.query.first():
            db.session.add(AcademicYear(name="2027", is_open=True))
            db.session.commit()
        for key, value in [("registration_open", "1"), ("school_name", app.config["SCHOOL_NAME"]),
                           ("required_docs", "joining_letter,academic_record"), ("fee_tracking_enabled", "1")]:
            if not SystemSetting.query.filter_by(key=key).first():
                db.session.add(SystemSetting(key=key, value=value))
        db.session.commit()
    return app
