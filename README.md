# Mrisho Gambo Secondary School — Form One Registration System

This is a full-stack starter implementation using Flask, SQLite, SQLAlchemy and server-side staff authentication. It is a stronger development baseline than the earlier browser-only prototype, but it still requires security review, testing and school approval before live use.

## Included
- Online Form One registration, staff-assisted registration via database/admin workflow
- English/Kiswahili interface
- Student, guardian, emergency contact and boarding/day fields
- Private document upload storage (PDF/JPG/PNG)
- Parent signature capture and declaration records
- Registration reference and status lookup
- Staff login, roles and role-protected routes
- Arrival confirmation, registration statuses and admission reference fields
- Document verification
- Fee status tracking and payment entries pending verification
- CSV exports and reports
- Staff user management
- Academic year and registration settings
- Audit events, CSRF protection, login rate limits, basic security headers
- Private document download routes and health endpoint

## Requirements
Python 3.10+ recommended.

## Local setup (Windows PowerShell)
1. Extract this ZIP.
2. Open PowerShell in the project folder.
3. Create a virtual environment:
   `py -m venv .venv`
4. Activate it:
   `.\.venv\Scripts\Activate.ps1`
5. Install dependencies:
   `pip install -r requirements.txt`
6. Copy `.env.example` to `.env`.
7. Edit `.env` and set a unique long `SECRET_KEY` and a strong `BOOTSTRAP_ADMIN_PASSWORD` (12+ characters).
8. Run:
   `python run.py`
9. Open `http://127.0.0.1:5000`.

Default academic year is 2027. The first admin account is created only if the environment variables specify a password and the account does not already exist. Use your configured `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD`.

## Deployment notes
- Use a production WSGI server such as Gunicorn behind a managed HTTPS reverse proxy.
- Set `COOKIE_SECURE=1` when deployed behind HTTPS.
- Use a strong secret key and unique administrator password. Never commit `.env`.
- Configure a persistent database and private upload volume. For multiple app instances, use PostgreSQL rather than SQLite.
- Keep uploaded files outside the public web root and ensure backups include both the database and private uploads.
- Configure reverse-proxy trusted IP handling carefully before relying on forwarded IP headers.
- Add email/SMS provider credentials only after selecting an approved provider.
- Run dependency and application security reviews and test restoration before launch.

## Important limitations / decisions still required
1. The public status lookup uses a registration reference; for production, add a second verification factor (for example a one-time code to the verified guardian phone) to reduce enumeration risk.
2. Signature capture records a drawn signature image. The school must approve declaration text, signature policy and evidence retention.
3. Document upload checks extensions and size but production should add antivirus/malware scanning and stricter file-content validation.
4. Role boundaries need a formal review, particularly teacher access and sensitive welfare fields.
5. Add password reset, MFA for privileged users, account lockout policy, session management review, and optional staff password changes before launch.
6. Add a proper migration workflow (Flask-Migrate) before production schema changes.
7. The system does not send SMS/email notifications yet.
8. No payment gateway is included; fee tracking is records-only as requested.
9. There is no automatic retention purge; school must approve a retention schedule and implement a controlled process.
10. Verify Tanzanian data-protection obligations and applicable education-sector/government reporting rules before collecting real children's data.

## Production checklist
- [ ] School approves official form fields, joining documents, fee policy and declarations
- [ ] Privacy notice and data-retention schedule approved
- [ ] Hosting, domain and data-location decisions approved
- [ ] HTTPS and secure cookies enabled
- [ ] Strong secrets and unique admin credentials set
- [ ] Staff roles tested with negative access tests
- [ ] Private uploads tested and malware scanning configured
- [ ] Backups and restore drill verified
- [ ] Error monitoring and incident response assigned
- [ ] Parent/guardian status lookup protected against enumeration
- [ ] Acceptance tests passed and school signs off
