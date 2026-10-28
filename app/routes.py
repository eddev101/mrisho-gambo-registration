import csv, io, os, re, secrets, uuid, base64
from datetime import datetime, date, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort, send_file, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import or_, func
from . import db, limiter
from .models import User, Student, StudentDocument, FeePayment, Declaration, AuditLog, AcademicYear, SystemSetting

main = Blueprint("main", __name__)
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
ROLES = {"admin", "head", "admissions", "finance", "teacher"}
STATUSES = ["Submitted", "Pending document verification", "Corrections required", "Approved for arrival", "Arrived — pending final checks", "Fully registered", "Withdrawn"]
FEE_STATUSES = ["Not assessed", "Not applicable", "Pending payment", "Partially paid", "Paid", "Exempt", "Pending verification"]
DECLARATIONS = {
 "parent": "I confirm that I am the parent/guardian or authorized person and that the information provided is accurate to the best of my knowledge.",
 "rules": "I acknowledge that the student and parent/guardian must read and follow the school's approved rules and joining instructions.",
 "privacy": "I acknowledge that I have read the privacy notice explaining how registration information is used and protected."
}
def setting(key, default=""):
    item = SystemSetting.query.filter_by(key=key).first()
    return item.value if item else default
def audit(action, entity_type=None, entity_id=None, details=None):
    log = AuditLog(actor_user_id=current_user.id if current_user.is_authenticated else None,
                   actor_label=current_user.full_name if current_user.is_authenticated else "Public registration",
                   action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id else None,
                   details=(details or "")[:2000], ip_address=request.headers.get("X-Forwarded-For", request.remote_addr))
    db.session.add(log)
def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.active or current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return deco
def parse_date(value):
    try: return date.fromisoformat(value)
    except (ValueError, TypeError): return None
def clean_phone(value):
    return re.sub(r"[\s().-]", "", (value or "").strip())
def valid_phone(value):
    digits = re.sub(r"\D", "", value or "")
    return 9 <= len(digits) <= 15
def new_ref(year):
    return f"MG-{year}-{secrets.token_hex(3).upper()}"
def save_signature(data_url, ref):
    if not data_url: return None
    match = re.fullmatch(r"data:image/png;base64,([A-Za-z0-9+/=]+)", data_url)
    if not match: return None
    try: raw = base64.b64decode(match.group(1), validate=True)
    except Exception: return None
    if len(raw) > 400_000: return None
    name = f"signature_{ref}_{uuid.uuid4().hex}.png"
    Path(current_app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    with open(Path(current_app.config["UPLOAD_DIR"]) / name, "wb") as f: f.write(raw)
    return name
def allowed_file(file):
    return bool(file and "." in file.filename and file.filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS)
def upload_docs(student):
    categories = {"joining_letter":"Joining/selection instructions", "academic_record":"Academic record", "proof_of_age":"Proof of age", "student_photo":"Student photograph", "other_document":"Other approved document"}
    for field, category in categories.items():
        file = request.files.get(field)
        if not file or not file.filename: continue
        if not allowed_file(file):
            raise ValueError(f"Unsupported file type for {category}. Use PDF, JPG or PNG.")
        file.stream.seek(0, os.SEEK_END); size=file.stream.tell(); file.stream.seek(0)
        if size > current_app.config["MAX_CONTENT_LENGTH"]:
            raise ValueError(f"{category} exceeds the upload limit.")
        stored = f"{uuid.uuid4().hex}.{file.filename.rsplit('.',1)[1].lower()}"
        path = Path(current_app.config["UPLOAD_DIR"]) / stored
        file.save(path)
        db.session.add(StudentDocument(student=student, category=category, original_name=secure_filename(file.filename)[:255],
                                       stored_name=stored, mime_type=file.mimetype, size_bytes=size))
def get_year(value):
    year = AcademicYear.query.filter_by(name=value).first()
    if not year or not year.is_open: return None
    return year
@main.context_processor
def inject_globals():
    return {"school_name": setting("school_name", current_app.config["SCHOOL_NAME"]), "csrf_token": __import__("flask_wtf.csrf").csrf.generate_csrf}
@main.route("/")
def index():
    years = AcademicYear.query.filter_by(is_open=True).order_by(AcademicYear.name.desc()).all()
    return render_template("index.html", years=years, registration_open=setting("registration_open","1")=="1", now_date=date.today().isoformat(), staff_assisted=(request.args.get("assisted")=="1" and current_user.is_authenticated and current_user.role in {"admin","head","admissions"}))
@main.route("/register", methods=["POST"])
@limiter.limit("10 per hour")
def register():
    if setting("registration_open","1") != "1":
        flash("Registration is currently closed. Please contact the school.", "warning"); return redirect(url_for("main.index"))
    year = get_year(request.form.get("academic_year",""))
    if not year:
        flash("Please select an open academic year.", "danger"); return redirect(url_for("main.index"))
    required = ["first_name","surname","dob","gender","primary_school","student_type","guardian_name","guardian_relationship","guardian_phone"]
    if any(not request.form.get(k,"").strip() for k in required):
        flash("Please complete all required fields.", "danger"); return redirect(url_for("main.index"))
    dob = parse_date(request.form.get("dob"))
    if not dob or dob > date.today():
        flash("Enter a valid date of birth.", "danger"); return redirect(url_for("main.index"))
    gender = request.form.get("gender")
    stype = request.form.get("student_type")
    if gender not in {"Male","Female"} or stype not in {"Day","Boarding"}:
        flash("Select a valid gender and student arrangement.", "danger"); return redirect(url_for("main.index"))
    phone = clean_phone(request.form.get("guardian_phone"))
    if not valid_phone(phone):
        flash("Enter a valid parent/guardian telephone number.", "danger"); return redirect(url_for("main.index"))
    if request.form.get("guardian_email") and "@" not in request.form.get("guardian_email"):
        flash("Enter a valid email address.", "danger"); return redirect(url_for("main.index"))
    if not all(request.form.get(k) == "yes" for k in ["parent_ack","rules_ack","privacy_ack"]):
        flash("Please complete all required acknowledgements.", "danger"); return redirect(url_for("main.index"))
    if not request.form.get("student_ack_name","").strip():
        flash("Enter the student's full name to acknowledge the school rules.", "danger"); return redirect(url_for("main.index"))
    ref = new_ref(year.name)
    while Student.query.filter_by(registration_ref=ref).first(): ref = new_ref(year.name)
    sig = save_signature(request.form.get("signature_data",""), ref)
    if not sig:
        flash("Please draw the parent/guardian signature before submitting.", "danger"); return redirect(url_for("main.index"))
    s = Student(registration_ref=ref, academic_year=year,
        first_name=request.form["first_name"].strip()[:80], middle_name=request.form.get("middle_name","").strip()[:80] or None,
        surname=request.form["surname"].strip()[:80], dob=dob, gender=gender,
        nationality=request.form.get("nationality","Tanzanian").strip()[:80], primary_school=request.form["primary_school"].strip()[:180],
        selection_number=request.form.get("selection_number","").strip()[:80] or None, student_type=stype,
        home_address=request.form.get("home_address","").strip()[:2000] or None,
        boarding_notes=request.form.get("boarding_notes","").strip()[:300] or None if stype=="Boarding" else None,
        dietary_needs=request.form.get("dietary_needs","").strip()[:300] or None if stype=="Boarding" else None,
        medical_notes=request.form.get("medical_notes","").strip()[:2000] or None,
        guardian_name=request.form["guardian_name"].strip()[:160], guardian_relationship=request.form["guardian_relationship"][:40],
        guardian_phone=phone[:30], guardian_alt_phone=clean_phone(request.form.get("guardian_alt_phone",""))[:30] or None,
        guardian_email=request.form.get("guardian_email","").strip()[:160] or None,
        emergency_name=request.form.get("emergency_name","").strip()[:160] or None,
        emergency_phone=clean_phone(request.form.get("emergency_phone",""))[:30] or None,
        status="Submitted", fee_status="Not assessed", source=("Staff-assisted" if current_user.is_authenticated and current_user.role in {"admin","head","admissions"} else "Online"), signature_path=sig,
        parent_acknowledged=True, rules_acknowledged=True, privacy_acknowledged=True,
        student_ack_name=request.form["student_ack_name"].strip()[:160])
    try:
        db.session.add(s); db.session.flush()
        upload_docs(s)
        for party, method, text in [
            ("parent_guardian","drawn_signature",DECLARATIONS["parent"]),
            ("student","typed_name",DECLARATIONS["rules"]),
            ("parent_guardian","checkbox",DECLARATIONS["privacy"])]:
            db.session.add(Declaration(student_id=s.id, party=party, method=method, declaration_version="v1",
                declaration_text=text, acknowledged_name=s.guardian_name if party=="parent_guardian" else s.student_ack_name,
                signature_path=sig if method=="drawn_signature" else None))
        audit("registration_submitted","student",s.id,f"Reference {ref}; source {s.source}")
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        if sig:
            try: os.remove(Path(current_app.config["UPLOAD_DIR"])/sig)
            except OSError: pass
        flash(str(exc), "danger"); return redirect(url_for("main.index"))
    except Exception:
        db.session.rollback()
        flash("Registration could not be saved. Please try again or contact the school.", "danger")
        current_app.logger.exception("Registration submission failed")
        return redirect(url_for("main.index"))
    return render_template("receipt.html", student=s)
@main.route("/status", methods=["GET","POST"])
@limiter.limit("20 per hour")
def status_lookup():
    student = None
    if request.method=="POST":
        ref=request.form.get("registration_ref","").strip().upper()
        student=Student.query.filter_by(registration_ref=ref).first()
        # Do not disclose medical/contact data in status lookup.
        if not student: flash("No matching registration was found. Check the reference or contact the school.", "warning")
    return render_template("status.html", student=student)
@main.route("/login", methods=["GET","POST"])
@limiter.limit("8 per minute")
def login():
    if current_user.is_authenticated: return redirect(url_for("main.dashboard"))
    if request.method=="POST":
        username=request.form.get("username","").strip()
        user=User.query.filter_by(username=username, active=True).first()
        if user and user.check_password(request.form.get("password","")):
            login_user(user, remember=False)
            user.last_login=datetime.now(timezone.utc)
            audit("login_success","user",user.id)
            db.session.commit()
            return redirect(request.args.get("next") or url_for("main.dashboard"))
        audit("login_failed","user",username,"Failed staff login")
        db.session.commit()
        flash("Invalid username or password.", "danger")
    return render_template("login.html")
@main.route("/logout", methods=["POST"])
@login_required
def logout():
    audit("logout","user",current_user.id)
    db.session.commit()
    logout_user()
    flash("You have signed out.", "success")
    return redirect(url_for("main.index"))
@main.route("/admin")
@role_required("admin","head","admissions","finance","teacher")
def dashboard():
    q=request.args.get("q","").strip()
    status=request.args.get("status","")
    stype=request.args.get("type","")
    year=request.args.get("year","")
    query=Student.query.join(AcademicYear)
    if q: query=query.filter(or_(Student.first_name.ilike(f"%{q}%"),Student.surname.ilike(f"%{q}%"),Student.registration_ref.ilike(f"%{q}%"),Student.admission_number.ilike(f"%{q}%")))
    if status in STATUSES: query=query.filter(Student.status==status)
    if stype in {"Day","Boarding"}: query=query.filter(Student.student_type==stype)
    if year: query=query.filter(AcademicYear.name==year)
    students=query.order_by(Student.created_at.desc()).limit(500).all()
    total=Student.query.count(); arrived=Student.query.filter(Student.arrival_at.isnot(None)).count()
    complete=Student.query.filter_by(status="Fully registered").count()
    pending=Student.query.filter(Student.status.in_(["Submitted","Pending document verification","Approved for arrival"])).count()
    years=AcademicYear.query.order_by(AcademicYear.name.desc()).all()
    return render_template("dashboard.html", students=students, total=total, arrived=arrived, complete=complete,
        pending=pending, years=years, statuses=STATUSES, fee_statuses=FEE_STATUSES, q=q, status=status, stype=stype, year=year)
@main.route("/admin/student/<int:student_id>")
@role_required("admin","head","admissions","finance","teacher")
def student_detail(student_id):
    s=db.get_or_404(Student,student_id)
    if current_user.role=="finance":
        # Finance view still shows basic record but not medical information/documents.
        documents=[]
    else: documents=s.documents
    payments=s.payments if current_user.role in {"admin","head","finance"} else []
    return render_template("student_detail.html", student=s, documents=documents, payments=payments, statuses=STATUSES, fee_statuses=FEE_STATUSES)
@main.route("/admin/student/<int:student_id>/status", methods=["POST"])
@role_required("admin","head","admissions")
def update_status(student_id):
    s=db.get_or_404(Student,student_id); new=request.form.get("status","")
    if new not in STATUSES: abort(400)
    if new=="Arrived — pending final checks" or new=="Fully registered":
        if not s.arrival_at:
            s.arrival_at=datetime.now(timezone.utc); s.arrival_by_id=current_user.id
    if new=="Fully registered":
        if not (s.parent_acknowledged and s.rules_acknowledged and s.privacy_acknowledged):
            flash("Required acknowledgements are missing.", "danger"); return redirect(url_for("main.student_detail",student_id=s.id))
        if any(d.status!="Verified" for d in s.documents):
            flash("All uploaded documents must be verified before final registration.", "danger"); return redirect(url_for("main.student_detail",student_id=s.id))
        s.approved_by_id=current_user.id; s.approved_at=datetime.now(timezone.utc)
    s.status=new
    audit("status_changed","student",s.id,f"Status set to {new}")
    db.session.commit(); flash("Registration status updated.", "success")
    return redirect(url_for("main.student_detail",student_id=s.id))
@main.route("/admin/student/<int:student_id>/arrival", methods=["POST"])
@role_required("admin","head","admissions")
def confirm_arrival(student_id):
    s=db.get_or_404(Student,student_id)
    if not s.arrival_at:
        s.arrival_at=datetime.now(timezone.utc); s.arrival_by_id=current_user.id
    s.status="Arrived — pending final checks"
    audit("arrival_confirmed","student",s.id,f"Reference {s.registration_ref}")
    db.session.commit(); flash("Physical arrival recorded.", "success")
    return redirect(url_for("main.student_detail",student_id=s.id))
@main.route("/admin/document/<int:doc_id>/review", methods=["POST"])
@role_required("admin","head","admissions")
def review_document(doc_id):
    d=db.get_or_404(StudentDocument,doc_id)
    status=request.form.get("status")
    if status not in {"Verified","Rejected","Pending review","Corrections required"}: abort(400)
    d.status=status; d.review_note=request.form.get("review_note","").strip()[:500] or None
    d.reviewed_by_id=current_user.id; d.reviewed_at=datetime.now(timezone.utc)
    audit("document_reviewed","document",d.id,f"{status}: {d.review_note or ''}")
    db.session.commit(); flash("Document review saved.", "success")
    return redirect(url_for("main.student_detail",student_id=d.student_id))
@main.route("/private-document/<int:doc_id>")
@role_required("admin","head","admissions")
def download_document(doc_id):
    d=db.get_or_404(StudentDocument,doc_id)
    path=Path(current_app.config["UPLOAD_DIR"])/d.stored_name
    if not path.is_file(): abort(404)
    audit("document_accessed","document",d.id,d.category); db.session.commit()
    return send_file(path, as_attachment=True, download_name=d.original_name, mimetype=d.mime_type or "application/octet-stream")
@main.route("/private-signature/<int:student_id>")
@role_required("admin","head","admissions")
def view_signature(student_id):
    s=db.get_or_404(Student,student_id)
    if not s.signature_path: abort(404)
    path=Path(current_app.config["UPLOAD_DIR"])/s.signature_path
    if not path.is_file(): abort(404)
    return send_file(path, mimetype="image/png", as_attachment=True, download_name=f"signature-{s.registration_ref}.png")
@main.route("/admin/student/<int:student_id>/admission-number", methods=["POST"])
@role_required("admin","head","admissions")
def update_admission_number(student_id):
    s=db.get_or_404(Student,student_id)
    number=request.form.get("admission_number","").strip()[:40] or None
    if number:
        existing=Student.query.filter(Student.admission_number==number, Student.id!=s.id).first()
        if existing:
            flash("That admission number is already assigned to another student.", "danger")
            return redirect(url_for("main.student_detail",student_id=s.id))
    old=s.admission_number; s.admission_number=number
    audit("admission_number_changed","student",s.id,f"Admission number changed from {old or 'unassigned'} to {number or 'unassigned'}")
    db.session.commit(); flash("Admission number saved.", "success")
    return redirect(url_for("main.student_detail",student_id=s.id))

@main.route("/admin/student/<int:student_id>/fee", methods=["POST"])
@role_required("admin","head","finance")
def update_fee(student_id):
    s=db.get_or_404(Student,student_id)
    status=request.form.get("fee_status","")
    if status not in FEE_STATUSES: abort(400)
    try:
        due=Decimal(request.form.get("amount_due","0")); paid=Decimal(request.form.get("amount_paid","0"))
        if due<0 or paid<0: raise InvalidOperation()
    except (InvalidOperation,ValueError):
        flash("Enter valid non-negative amounts.", "danger"); return redirect(url_for("main.student_detail",student_id=s.id))
    ref=request.form.get("payment_reference","").strip()[:120] or None
    s.amount_due=due; s.amount_paid=paid; s.payment_reference=ref; s.fee_status=status
    audit("fee_status_updated","student",s.id,f"Status {status}; due {due}; paid {paid}")
    db.session.commit(); flash("Fee status updated.", "success")
    return redirect(url_for("main.student_detail",student_id=s.id))
@main.route("/admin/student/<int:student_id>/payment", methods=["POST"])
@role_required("admin","head","finance")
def add_payment(student_id):
    s=db.get_or_404(Student,student_id)
    try:
        amount=Decimal(request.form.get("amount","0"))
        if amount<=0: raise InvalidOperation()
    except (InvalidOperation,ValueError):
        flash("Enter a valid positive payment amount.", "danger"); return redirect(url_for("main.student_detail",student_id=s.id))
    payment=FeePayment(student_id=s.id,amount=amount,payment_date=parse_date(request.form.get("payment_date","")),
        payment_reference=request.form.get("payment_reference","").strip()[:120] or None,
        notes=request.form.get("notes","").strip()[:300] or None,verified=False,recorded_by_id=current_user.id)
    db.session.add(payment); audit("payment_recorded","payment",s.id,f"Amount {amount}; awaiting verification")
    db.session.commit(); flash("Payment recorded as pending verification.", "success")
    return redirect(url_for("main.student_detail",student_id=s.id))
@main.route("/admin/payment/<int:payment_id>/verify", methods=["POST"])
@role_required("admin","head","finance")
def verify_payment(payment_id):
    p=db.get_or_404(FeePayment,payment_id); p.verified=True
    audit("payment_verified","payment",p.id,f"Student {p.student_id}")
    db.session.commit(); flash("Payment marked verified.", "success")
    return redirect(url_for("main.student_detail",student_id=p.student_id))
@main.route("/admin/users", methods=["GET","POST"])
@role_required("admin")
def users():
    if request.method=="POST":
        username=request.form.get("username","").strip()
        full_name=request.form.get("full_name","").strip()
        role=request.form.get("role","")
        password=request.form.get("password","")
        if not username or not full_name or role not in ROLES or len(password)<12:
            flash("Provide a name, username, valid role and password of at least 12 characters.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("That username already exists.", "danger")
        else:
            u=User(username=username,full_name=full_name,role=role,active=True);u.set_password(password);db.session.add(u)
            audit("user_created","user",username,f"Role {role}");db.session.commit();flash("Staff account created.", "success")
        return redirect(url_for("main.users"))
    return render_template("users.html", users=User.query.order_by(User.username).all(), roles=sorted(ROLES))
@main.route("/admin/user/<int:user_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_user(user_id):
    u=db.get_or_404(User,user_id)
    if u.id==current_user.id:
        flash("You cannot deactivate your own account.", "danger")
    else:
        u.active=not u.active;audit("user_activated" if u.active else "user_deactivated","user",u.id);db.session.commit()
    return redirect(url_for("main.users"))
@main.route("/admin/settings", methods=["GET","POST"])
@role_required("admin","head")
def settings():
    if request.method=="POST":
        for key in ["registration_open","school_name","required_docs","fee_tracking_enabled"]:
            value=request.form.get(key,"")
            if key in {"registration_open","fee_tracking_enabled"} and value not in {"0","1"}: continue
            item=SystemSetting.query.filter_by(key=key).first()
            if not item: item=SystemSetting(key=key,value=value);db.session.add(item)
            else: item.value=value
        audit("settings_updated","system",None,"Registration and system settings changed")
        db.session.commit();flash("Settings saved.", "success");return redirect(url_for("main.settings"))
    return render_template("settings.html", registration_open=setting("registration_open","1"), school_name=setting("school_name",current_app.config["SCHOOL_NAME"]), required_docs=setting("required_docs","joining_letter,academic_record"), fee_tracking_enabled=setting("fee_tracking_enabled","1"), years=AcademicYear.query.order_by(AcademicYear.name.desc()).all())
@main.route("/admin/year", methods=["POST"])
@role_required("admin")
def add_year():
    name=request.form.get("name","").strip()
    if not re.fullmatch(r"20\d{2}",name):
        flash("Academic year must be a four-digit year.", "danger")
    elif AcademicYear.query.filter_by(name=name).first():
        flash("That academic year already exists.", "warning")
    else:
        db.session.add(AcademicYear(name=name,is_open=request.form.get("is_open")=="yes"));audit("academic_year_created","academic_year",name);db.session.commit();flash("Academic year created.", "success")
    return redirect(url_for("main.settings"))
@main.route("/admin/reports")
@role_required("admin","head","admissions","finance")
def reports():
    years=AcademicYear.query.order_by(AcademicYear.name.desc()).all()
    year=request.args.get("year","")
    query=Student.query.join(AcademicYear)
    if year: query=query.filter(AcademicYear.name==year)
    students=query.order_by(Student.created_at.desc()).all()
    stats={"total":len(students),"arrived":sum(1 for s in students if s.arrival_at),"complete":sum(1 for s in students if s.status=="Fully registered"),
           "boarding":sum(1 for s in students if s.student_type=="Boarding"),"day":sum(1 for s in students if s.student_type=="Day"),
           "pending_docs":sum(1 for s in students if any(d.status!="Verified" for d in s.documents))}
    return render_template("reports.html",years=years,year=year,students=students,stats=stats)
@main.route("/admin/export.csv")
@role_required("admin","head","admissions","finance")
def export_csv():
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(["Registration Reference","Admission Number","Academic Year","First Name","Middle Name","Surname","Date of Birth","Gender","Primary School","Selection Number","Student Type","Guardian Name","Guardian Phone","Status","Fee Status","Amount Due","Amount Paid","Submitted At","Arrival At"])
    for s in Student.query.join(AcademicYear).order_by(Student.created_at.desc()).all():
        writer.writerow([s.registration_ref,s.admission_number,s.academic_year.name,s.first_name,s.middle_name,s.surname,s.dob,s.gender,s.primary_school,s.selection_number,s.student_type,s.guardian_name,s.guardian_phone,s.status,s.fee_status,s.amount_due,s.amount_paid,s.created_at,s.arrival_at])
    audit("report_exported","student",None,"CSV registration export");db.session.commit()
    return current_app.response_class("\ufeff"+output.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=mrisho-gambo-registrations.csv"})
@main.route("/admin/audit")
@role_required("admin","head")
def audit_report():
    logs=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(500).all()
    return render_template("audit.html",logs=logs)
@main.route("/health")
def health():
    return jsonify({"status":"ok"})
