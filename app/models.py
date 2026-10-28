from datetime import datetime, timezone
from flask_login import UserMixin
from flask_bcrypt import Bcrypt
from . import db, login_manager

bcrypt = Bcrypt()

def now_utc():
    return datetime.now(timezone.utc)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(160), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="admissions")
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)
    last_login = db.Column(db.DateTime(timezone=True))
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

class AcademicYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(12), unique=True, nullable=False)
    is_open = db.Column(db.Boolean, default=False, nullable=False)
    registration_start = db.Column(db.Date)
    registration_end = db.Column(db.Date)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    registration_ref = db.Column(db.String(30), unique=True, nullable=False, index=True)
    admission_number = db.Column(db.String(40), unique=True, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    middle_name = db.Column(db.String(80))
    surname = db.Column(db.String(80), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    nationality = db.Column(db.String(80), default="Tanzanian")
    primary_school = db.Column(db.String(180), nullable=False)
    selection_number = db.Column(db.String(80))
    student_type = db.Column(db.String(20), nullable=False)
    home_address = db.Column(db.Text)
    boarding_notes = db.Column(db.String(300))
    dietary_needs = db.Column(db.String(300))
    medical_notes = db.Column(db.Text)
    guardian_name = db.Column(db.String(160), nullable=False)
    guardian_relationship = db.Column(db.String(40), nullable=False)
    guardian_phone = db.Column(db.String(30), nullable=False)
    guardian_alt_phone = db.Column(db.String(30))
    guardian_email = db.Column(db.String(160))
    emergency_name = db.Column(db.String(160))
    emergency_phone = db.Column(db.String(30))
    status = db.Column(db.String(50), default="Submitted", nullable=False, index=True)
    fee_status = db.Column(db.String(30), default="Not assessed", nullable=False)
    amount_due = db.Column(db.Numeric(12, 2), default=0)
    amount_paid = db.Column(db.Numeric(12, 2), default=0)
    payment_reference = db.Column(db.String(120))
    source = db.Column(db.String(30), default="Online")
    declaration_version = db.Column(db.String(30), default="v1")
    parent_acknowledged = db.Column(db.Boolean, default=False)
    rules_acknowledged = db.Column(db.Boolean, default=False)
    privacy_acknowledged = db.Column(db.Boolean, default=False)
    student_ack_name = db.Column(db.String(160))
    signature_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    arrival_at = db.Column(db.DateTime(timezone=True))
    arrival_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    approved_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    approved_at = db.Column(db.DateTime(timezone=True))
    academic_year = db.relationship("AcademicYear")
    documents = db.relationship("StudentDocument", backref="student", cascade="all, delete-orphan")
    payments = db.relationship("FeePayment", backref="student", cascade="all, delete-orphan")
    def full_name(self):
        return " ".join(x for x in [self.first_name, self.middle_name, self.surname] if x)

class StudentDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), unique=True, nullable=False)
    mime_type = db.Column(db.String(100))
    size_bytes = db.Column(db.Integer)
    status = db.Column(db.String(30), default="Pending review", nullable=False)
    review_note = db.Column(db.String(500))
    uploaded_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    reviewed_at = db.Column(db.DateTime(timezone=True))

class FeePayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_date = db.Column(db.Date)
    payment_reference = db.Column(db.String(120))
    notes = db.Column(db.String(300))
    verified = db.Column(db.Boolean, default=False, nullable=False)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)

class Declaration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    party = db.Column(db.String(30), nullable=False)
    method = db.Column(db.String(30), nullable=False)
    declaration_version = db.Column(db.String(30), nullable=False)
    declaration_text = db.Column(db.Text, nullable=False)
    acknowledged_name = db.Column(db.String(160))
    signature_path = db.Column(db.String(255))
    acknowledged_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    actor_label = db.Column(db.String(160))
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(80))
    entity_id = db.Column(db.String(80))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False, index=True)

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
