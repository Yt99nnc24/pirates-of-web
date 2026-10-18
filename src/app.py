
import os
import mysql.connector
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request,
    redirect, url_for, session, abort
)
from werkzeug.security import (
    generate_password_hash, check_password_hash
)
from dotenv import load_dotenv
from db import get_db
from flask import render_template

@app.route("/doctor")
def doctor_dashboard():
    # Use your existing authentication and data-fetching logic here.
    # These are examples of the variables your template requires.
    return render_template(
        "doctor.html",
        name=doctor.name,
        role=doctor.role,
        profile=profile,
        cases=cases
    )
load_dotenv()

def get_db():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("Simhar5358"),
        database=os.getenv("MYSQL_DATABASE", "sahayaj_ai")
    )


app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

CONFIG = {
    "patient": {
        "table": "patients",
        "template": "patientlogin.html",
        "dashboard": "patient_dashboard"
    },
    "doctor": {
        "table": "doctors",
        "template": "doctorlogin.html",
        "dashboard": "doctor_dashboard"
    }
}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/patient-login", methods=["GET", "POST"])
def patient_login():
    return handle_auth("patient")


@app.route("/doctor-login", methods=["GET", "POST"])
def doctor_login():
    return handle_auth("doctor")


def handle_auth(role):
    config = CONFIG[role]
    error = None

    if request.method == "POST":
        action = request.form.get("action", "login")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if action == "signup":
            name = request.form.get("name", "").strip()

            if not name or not email or len(password) < 8:
                error = "Enter valid details and a password of at least 8 characters."
            else:
                conn = get_db()
                cursor = conn.cursor()

                try:
                    if role == "patient":
                        cursor.execute(
                            """INSERT INTO patients
                               (name, email, password_hash)
                               VALUES (%s, %s, %s)""",
                            (name, email, generate_password_hash(password))
                        )
                    else:
                        department = request.form.get("department", "").strip()
                        specialization = request.form.get("specialization", "").strip()

                        if not department or not specialization:
                            error = "Department and specialization are required."
                        else:
                            cursor.execute(
                                """INSERT INTO doctors
                                   (name, email, department,
                                    specialization, password_hash)
                                   VALUES (%s, %s, %s, %s, %s)""",
                                (
                                    name, email, department,
                                    specialization,
                                    generate_password_hash(password)
                                )
                            )

                    if not error:
                        conn.commit()
                        return redirect(
                            url_for(
                                "doctor_login" if role == "doctor"
                                else "patient_login"
                            )
                        )

                except Exception:
                    conn.rollback()
                    error = "Registration failed. Email may already exist."
                finally:
                    cursor.close()
                    conn.close()

        elif action == "login":
            conn = get_db()
            cursor = conn.cursor(dictionary=True)

            try:
                cursor.execute(
                    f"""SELECT * FROM {config['table']}
                        WHERE email = %s""",
                    (email,)
                )
                user = cursor.fetchone()
            finally:
                cursor.close()
                conn.close()

            if user and check_password_hash(
                user["password_hash"], password
            ):
                if role == "doctor" and not user["is_verified"]:
                    error = "Doctor account is awaiting verification."
                else:
                    session.clear()
                    session["user_id"] = user["id"]
                    session["role"] = role
                    session["name"] = user["name"]

                    return redirect(url_for(config["dashboard"]))
            else:
                error = "Invalid email or password."
        else:
            abort(400)

    return render_template(config["template"], error=error)


@app.route("/patient")
def patient_dashboard():
    if session.get("role") != "patient":
        return redirect(url_for("patient_login"))
    return render_template("patient.html")


@app.route("/doctor")
def doctor_dashboard():
    if session.get("role") != "doctor":
        return redirect(url_for("doctor_login"))
    return render_template("doctor.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
