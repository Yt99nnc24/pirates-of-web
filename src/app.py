"""CLINEXA: a fictional-data consultation workflow prototype."""
import hmac
import os
import secrets
import sqlite3
from datetime import timedelta
from functools import wraps
from pathlib import Path

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

DEPARTMENTS = ("General medicine", "Ayurveda", "Homeopathy", "Dental care", "Physiotherapy")


def create_app(test_config=None):
    app = Flask(__name__, template_folder=".", static_folder="static")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get("DATABASE_PATH", str(Path(app.instance_path) / "clinexa.sqlite3")),
        ENABLE_DEMO=os.environ.get("ENABLE_DEMO") == "1",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    def db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_error):
        conn = g.pop("db", None)
        if conn:
            conn.close()

    with app.app_context():
        db().executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, role TEXT NOT NULL CHECK(role IN ('patient','doctor')),
                name TEXT NOT NULL, email TEXT NOT NULL, password_hash TEXT NOT NULL,
                department TEXT NOT NULL DEFAULT '', specialization TEXT NOT NULL DEFAULT '',
                verified INTEGER NOT NULL DEFAULT 0, is_demo INTEGER NOT NULL DEFAULT 0,
                UNIQUE(role,email)
            );
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES users(id),
                department TEXT NOT NULL, symptoms TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','reviewed')),
                notes TEXT NOT NULL DEFAULT '', reviewed_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TEXT
            );
        """)

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    @app.context_processor
    def context():
        return dict(csrf_token=csrf_token, departments=DEPARTMENTS,
                    demo_enabled=app.config["ENABLE_DEMO"], current_user=g.get("user"))

    @app.before_request
    def protect_request():
        g.user = None
        if session.get("user_id"):
            g.user = db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if request.method == "POST":
            supplied = request.form.get("csrf_token", "")
            expected = session.get("csrf", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                abort(400, description="Your form session expired. Refresh the page and try again.")
        else:
            csrf_token()

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    def require_role(role):
        def decorate(view):
            @wraps(view)
            def guarded(*args, **kwargs):
                if not g.user:
                    return redirect(url_for(role + "_login"))
                if g.user["role"] != role:
                    abort(403)
                if role == "doctor" and not g.user["verified"]:
                    session.clear()
                    return redirect(url_for("doctor_login"))
                return view(*args, **kwargs)
            return guarded
        return decorate

    @app.route("/")
    def home():
        return render_template("index.html")

    def handle_auth(role):
        error = None
        action = request.form.get("action", "login") if request.method == "POST" else request.args.get("action", "login")
        if action not in ("login", "signup"):
            abort(400)
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if len(email) > 254 or "@" not in email or len(password) > 128:
                error = "Enter a valid email and a password of at most 128 characters."
            elif action == "signup":
                name = request.form.get("name", "").strip()
                department = request.form.get("department", "") if role == "doctor" else ""
                specialization = request.form.get("specialization", "").strip() if role == "doctor" else ""
                if not 2 <= len(name) <= 80 or not 8 <= len(password) <= 128:
                    error = "Enter a name (2–80 characters) and a password (8–128 characters)."
                elif role == "doctor" and (department not in DEPARTMENTS or not 2 <= len(specialization) <= 100):
                    error = "Choose a department and enter a specialization (2–100 characters)."
                else:
                    try:
                        db().execute("INSERT INTO users (role,name,email,password_hash,department,specialization) VALUES (?,?,?,?,?,?)",
                                     (role,name,email,generate_password_hash(password),department,specialization))
                        db().commit()
                        flash("Account created. " + ("An administrator must approve your doctor account before sign-in." if role == "doctor" else "You can sign in now."), "success")
                        return redirect(url_for(role + "_login"))
                    except sqlite3.IntegrityError:
                        db().rollback()
                        error = "This email is already registered for this portal. Try signing in."
            else:
                user = db().execute("SELECT * FROM users WHERE role=? AND email=? AND is_demo=0", (role,email)).fetchone()
                if not user or not check_password_hash(user["password_hash"], password):
                    error = "Email or password is incorrect."
                elif role == "doctor" and not user["verified"]:
                    error = "Your doctor account is awaiting administrator approval."
                else:
                    session.clear()
                    session["user_id"] = user["id"]
                    session.permanent = True
                    return redirect(url_for(role + "_dashboard"))
        return render_template(role + "login.html", role=role, action=action, error=error)

    @app.route("/patient-login", methods=["GET", "POST"])
    def patient_login():
        return handle_auth("patient")

    @app.route("/doctor-login", methods=["GET", "POST"])
    def doctor_login():
        return handle_auth("doctor")

    @app.route("/patient")
    @require_role("patient")
    def patient_dashboard():
        cases = db().execute("SELECT * FROM cases WHERE patient_id=? ORDER BY id DESC", (g.user["id"],)).fetchall()
        return render_template("patient.html", cases=cases)

    @app.route("/cases", methods=["POST"])
    @require_role("patient")
    def create_case():
        symptoms = request.form.get("symptoms", "").strip()
        department = request.form.get("department", "")
        if department not in DEPARTMENTS or not 10 <= len(symptoms) <= 3000:
            flash("Choose a department and describe the concern in 10–3,000 characters.", "error")
        else:
            db().execute("INSERT INTO cases (patient_id,department,symptoms) VALUES (?,?,?)", (g.user["id"],department,symptoms))
            db().commit()
            flash("Case submitted. You can follow its review status below.", "success")
        return redirect(url_for("patient_dashboard"))

    @app.route("/doctor")
    @require_role("doctor")
    def doctor_dashboard():
        cases = db().execute("""SELECT cases.*, users.name AS patient_name FROM cases
            JOIN users ON cases.patient_id=users.id
            WHERE cases.department=? AND users.is_demo=? AND (?=0 OR users.email=?) ORDER BY cases.id DESC""",
            (g.user["department"],g.user["is_demo"],g.user["is_demo"],g.user["email"])).fetchall()
        return render_template("doctor.html", cases=cases)

    @app.route("/cases/<int:case_id>/review", methods=["POST"])
    @require_role("doctor")
    def review_case(case_id):
        case = db().execute("SELECT cases.*, users.is_demo, users.email FROM cases JOIN users ON cases.patient_id=users.id WHERE cases.id=?", (case_id,)).fetchone()
        if not case:
            abort(404)
        if case["department"] != g.user["department"] or case["is_demo"] != g.user["is_demo"]:
            abort(403)
        if g.user["is_demo"] and case["email"] != g.user["email"]:
            abort(403)
        notes = request.form.get("notes", "").strip()
        if case["status"] != "pending":
            flash("This case has already been reviewed.", "error")
        elif not 5 <= len(notes) <= 3000:
            flash("Review notes must contain 5–3,000 characters.", "error")
        else:
            result = db().execute("UPDATE cases SET status='reviewed',notes=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'", (notes,g.user["id"],case_id))
            db().commit()
            flash("Review saved." if result.rowcount else "This case has already been reviewed.", "success")
        return redirect(url_for("doctor_dashboard"))

    @app.route("/demo/<role>", methods=["POST"])
    def demo(role):
        if not app.config["ENABLE_DEMO"] or role not in ("patient", "doctor"):
            abort(404)
        # Each browser gets a separate fictional workspace; no cross-visitor demo records.
        token = session.get("demo_workspace") or secrets.token_hex(12)
        user = db().execute("SELECT * FROM users WHERE role=? AND email=?", (role, token + "@demo.invalid")).fetchone()
        if not user:
            cursor = db().execute("INSERT INTO users (role,name,email,password_hash,department,specialization,verified,is_demo) VALUES (?,?,?,?,?,?,1,1)",
                                 (role,"Alex Morgan" if role == "patient" else "Sam Taylor",token+"@demo.invalid",generate_password_hash(secrets.token_urlsafe(32)),DEPARTMENTS[0],"General practice"))
            user_id = cursor.lastrowid
            if role == "patient":
                db().execute("INSERT INTO cases (patient_id,department,symptoms) VALUES (?,?,?)", (user_id,DEPARTMENTS[0],"Fictional example: I would like to discuss my recent sleep routine at a consultation."))
            db().commit()
        else:
            user_id = user["id"]
        session.clear()
        session.update(user_id=user_id,demo_workspace=token)
        return redirect(url_for(role+"_dashboard"))

    @app.route("/logout", methods=["POST"])
    def logout():
        token = session.get("demo_workspace")
        session.clear()
        if token:
            session["demo_workspace"] = token
        return redirect(url_for("home"))

    @app.cli.command("approve-doctor")
    @click.argument("email")
    def approve_doctor(email):
        """Approve a registered doctor after out-of-band verification."""
        result = db().execute("UPDATE users SET verified=1 WHERE role='doctor' AND email=? AND is_demo=0", (email.strip().lower(),))
        db().commit()
        if not result.rowcount:
            raise click.ClickException("No registered doctor found for this email.")
        click.echo("Doctor account approved.")

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error_page(error):
        return render_template("error.html", error=error), error.code

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
