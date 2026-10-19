# CLINEXA · Pirates of Web

A patient-and-clinician consultation workflow prototype. Patients share a fictional concern with a care department; approved doctors review it and write notes that the patient can read. This is a software demonstration, not a clinical system or automated medical adviser.

## What works

- Responsive landing page with separate patient and clinician portals.
- Registration, hashed passwords, role-based sign-in and logout.
- Administrator approval for doctor accounts through a Flask CLI command.
- Patient case creation, status tracking and finalized review notes.
- Doctor department queue, search/status filters and one-time review finalization.
- CSRF checks for every POST, server-side validation and escaped user content.
- Optional fictional demo workspaces, separated per browser session.
- SQLite storage initialized automatically; no external database server required.

## Run locally

Requires Python 3.10 or later. From the repository root:

```sh
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python src/app.py
```

Open http://127.0.0.1:5000. The templates remain in `src/`; Flask is configured to find them there. Persistent data is stored in `src/instance/clinexa.sqlite3` by default. This new SQLite store does not import any earlier MySQL records.

For a local fictional demo, set the variable before starting:

```powershell
$env:ENABLE_DEMO = "1"
python src/app.py
```

Open the patient demo, submit a fictional case, log out, then open the doctor demo in the same browser. Both demo identities share that browser's workspace. Other visitors cannot see its cases. Clearing browser cookies loses access to that workspace; demo records remain in the local database until the operator removes the disposable database. Demo access is disabled by default.

## Approve a doctor

Register through the doctor portal, verify the identity outside this application, then run:

```sh
python -m flask --app src/app.py approve-doctor doctor@example.com
```

This command is an operator tool, not an in-app public approval endpoint. Do not approve unverified people for real clinical use.

## Configuration

See `.env.example` for names; set variables in your shell or host configuration. The application does not automatically load `.env` files.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Persistent random signing secret; without one, a random secret is generated at startup and sessions reset on restart. Use a stable secret across production workers. |
| `DATABASE_PATH` | Optional SQLite file path in a writable directory. |
| `ENABLE_DEMO` | `1` enables the fictional demo entry buttons; default off. |
| `COOKIE_SECURE` | Set to `1` when served over HTTPS. |
| `PORT` | Local development port; default `5000`. |

Never commit secrets, databases or patient information. This Flask backend requires a Python host; static GitHub Pages/Netlify Drop hosting alone cannot run it. The built-in server is for local development.

## Checks

```sh
python -m unittest discover -s tests -v
node --check src/static/app.js
```

Integration tests use temporary databases and cover portal rendering, account approval, the full submission/review flow, patient and department boundaries, duplicate reviews, demo isolation, input validation, CSRF, password hashing and HTML escaping.

## Structure

```text
src/app.py        Flask app factory, routes, SQLite schema and approval CLI
src/*.html       Shared Jinja templates and portal pages
src/static/      Responsive styles and small interface enhancements
tests/           Isolated integration tests
requirements.txt Python dependencies
```

## Boundaries

Use fictional data only. There is no AI diagnosis, appointment booking, emergency monitoring, report upload or external medical integration. All approved non-demo doctors in the same department can view that department's non-demo cases; this is not per-patient assignment. A real deployment needs assignment/consent controls, audit trails, rate limiting, verified contact recovery, encryption and retention policies, operational monitoring, appropriate legal review and clinical oversight. External Google Fonts are optional presentation assets; system fonts remain available if offline.

Built by **Pirates of Web**.
