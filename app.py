import os
import csv
import io
import uuid
from datetime import datetime, date, timedelta
from flask import (
    Flask, render_template, redirect, url_for, request, flash, Response, send_from_directory
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from werkzeug.utils import secure_filename
from sqlalchemy import func
from models import db, User, Customer, Deal, Activity, Attendance, Task, Leave, Attachment

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ---------- Database Settings ----------
# Locally (XAMPP) these fall back to XAMPP's defaults automatically.
# On a live host (Railway, Render, etc.) set these as Environment Variables instead —
# never hardcode real production passwords in this file.
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")     # XAMPP's default blank password
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "3306")
DB_NAME = os.environ.get("DB_NAME", "crm_db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max upload

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in first."
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def get_notifications():
    """Build a simple, on-the-fly list of things the current user should know about."""
    items = []
    if not current_user.is_authenticated:
        return items

    soon = date.today() + timedelta(days=2)

    if current_user.is_admin:
        my_tasks = Task.query.filter(Task.status != "Completed")
        pending_leaves = Leave.query.filter_by(status="Pending").count()
        if pending_leaves:
            items.append({
                "text": f"{pending_leaves} leave request(s) waiting for approval",
                "url": url_for("leaves"),
                "kind": "leave",
            })
    else:
        my_tasks = Task.query.filter_by(assigned_to=current_user.id).filter(Task.status != "Completed")

    for t in my_tasks:
        if t.due_date and t.due_date <= soon:
            overdue = t.due_date < date.today()
            items.append({
                "text": f"{'Overdue' if overdue else 'Due soon'}: \"{t.title}\"" + (f" ({t.assignee.name})" if current_user.is_admin else ""),
                "url": url_for("tasks"),
                "kind": "overdue" if overdue else "due",
            })

    if not current_user.is_admin:
        my_leave_updates = Leave.query.filter(
            Leave.user_id == current_user.id, Leave.status != "Pending"
        ).order_by(Leave.created_at.desc()).limit(3).all()
        for lv in my_leave_updates:
            items.append({
                "text": f"Your leave ({lv.from_date.strftime('%d %b')}–{lv.to_date.strftime('%d %b')}) was {lv.status.lower()}",
                "url": url_for("leaves"),
                "kind": "leave",
            })

    return items


@app.context_processor
def inject_notifications():
    if current_user.is_authenticated:
        notes = get_notifications()
        return {"nav_notifications": notes, "nav_notification_count": len(notes)}
    return {"nav_notifications": [], "nav_notification_count": 0}


STAGES = ["New", "Contacted", "Proposal", "Won", "Lost"]
STATUSES = ["Lead", "Active", "Inactive"]
TASK_STATUSES = ["Pending", "In Progress", "Completed"]


def admin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash("Only Admins can access that page.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


# ---------- Auth ----------

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("This email is already registered.", "error")
            return redirect(url_for("register"))
        # The very first account becomes an Admin automatically; everyone after is an Employee.
        role = "Admin" if User.query.count() == 0 else "Employee"
        user = User(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------- Dashboard ----------

@app.route("/")
@login_required
def dashboard():
    total_customers = Customer.query.count()
    total_leads = Customer.query.filter_by(status="Lead").count()
    total_active = Customer.query.filter_by(status="Active").count()

    open_deals = Deal.query.filter(Deal.stage.notin_(["Won", "Lost"])).all()
    open_value = sum(d.value for d in open_deals)
    won_value = db.session.query(func.coalesce(func.sum(Deal.value), 0)).filter(Deal.stage == "Won").scalar()

    pipeline = {}
    for stage in STAGES:
        count = Deal.query.filter_by(stage=stage).count()
        value = db.session.query(func.coalesce(func.sum(Deal.value), 0)).filter(Deal.stage == stage).scalar()
        pipeline[stage] = {"count": count, "value": value}

    recent_activities = Activity.query.order_by(Activity.created_at.desc()).limit(8).all()
    recent_customers = Customer.query.order_by(Customer.created_at.desc()).limit(5).all()

    my_attendance_today = Attendance.query.filter_by(user_id=current_user.id, date=date.today()).first()
    my_open_tasks = Task.query.filter_by(assigned_to=current_user.id).filter(Task.status != "Completed").count()

    # --- Analytics: won-deal value per month for the last 6 months ---
    month_labels, month_values = [], []
    cursor = date.today().replace(day=1)
    month_starts = []
    for _ in range(6):
        month_starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_starts.reverse()
    for m_start in month_starts:
        next_month = (m_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        total = db.session.query(func.coalesce(func.sum(Deal.value), 0)).filter(
            Deal.stage == "Won", Deal.created_at >= m_start, Deal.created_at < next_month
        ).scalar()
        month_labels.append(m_start.strftime("%b %Y"))
        month_values.append(float(total))

    # --- Analytics: top 5 customers by total deal value ---
    top_customers_q = (
        db.session.query(Customer.name, func.coalesce(func.sum(Deal.value), 0).label("total"))
        .join(Deal, Deal.customer_id == Customer.id)
        .group_by(Customer.id)
        .order_by(func.sum(Deal.value).desc())
        .limit(5)
        .all()
    )
    top_customer_labels = [row[0] for row in top_customers_q]
    top_customer_values = [float(row[1]) for row in top_customers_q]

    return render_template(
        "dashboard.html",
        total_customers=total_customers,
        total_leads=total_leads,
        total_active=total_active,
        open_value=open_value,
        won_value=won_value,
        pipeline=pipeline,
        stages=STAGES,
        recent_activities=recent_activities,
        recent_customers=recent_customers,
        my_attendance_today=my_attendance_today,
        my_open_tasks=my_open_tasks,
        month_labels=month_labels,
        month_values=month_values,
        top_customer_labels=top_customer_labels,
        top_customer_values=top_customer_values,
    )


# ---------- Customers ----------

@app.route("/customers")
@login_required
def customers():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    query = Customer.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Customer.name.ilike(like)) | (Customer.company.ilike(like)) | (Customer.email.ilike(like))
        )
    if status:
        query = query.filter_by(status=status)
    all_customers = query.order_by(Customer.created_at.desc()).all()
    return render_template("customers.html", customers=all_customers, q=q, status=status, statuses=STATUSES)


@app.route("/customers/add", methods=["GET", "POST"])
@login_required
def add_customer():
    if request.method == "POST":
        c = Customer(
            name=request.form.get("name", "").strip(),
            company=request.form.get("company", "").strip(),
            email=request.form.get("email", "").strip(),
            phone=request.form.get("phone", "").strip(),
            address=request.form.get("address", "").strip(),
            status=request.form.get("status", "Lead"),
            notes=request.form.get("notes", "").strip(),
            owner_id=current_user.id,
        )
        if not c.name:
            flash("Name is required.", "error")
            return redirect(url_for("add_customer"))
        db.session.add(c)
        db.session.commit()
        flash("Customer added.", "success")
        return redirect(url_for("customers"))
    return render_template("customer_form.html", customer=None, statuses=STATUSES)


@app.route("/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    activities = Activity.query.filter_by(customer_id=customer_id).order_by(Activity.created_at.desc()).all()
    return render_template("customer_detail.html", customer=customer, activities=activities, stages=STAGES)


@app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if request.method == "POST":
        customer.name = request.form.get("name", "").strip()
        customer.company = request.form.get("company", "").strip()
        customer.email = request.form.get("email", "").strip()
        customer.phone = request.form.get("phone", "").strip()
        customer.address = request.form.get("address", "").strip()
        customer.status = request.form.get("status", "Lead")
        customer.notes = request.form.get("notes", "").strip()
        db.session.commit()
        flash("Customer updated.", "success")
        return redirect(url_for("customer_detail", customer_id=customer.id))
    return render_template("customer_form.html", customer=customer, statuses=STATUSES)


@app.route("/customers/<int:customer_id>/delete", methods=["POST"])
@login_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    flash("Customer deleted.", "success")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/note", methods=["POST"])
@login_required
def add_note(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    note = request.form.get("note", "").strip()
    if note:
        db.session.add(Activity(customer_id=customer.id, note=note, author_id=current_user.id))
        db.session.commit()
        flash("Note added.", "success")
    return redirect(url_for("customer_detail", customer_id=customer.id))


# ---------- Deals ----------

@app.route("/deals")
@login_required
def deals():
    stage_filter = request.args.get("stage", "")
    query = Deal.query
    if stage_filter:
        query = query.filter_by(stage=stage_filter)
    all_deals = query.order_by(Deal.created_at.desc()).all()
    return render_template("deals.html", deals=all_deals, stages=STAGES, stage_filter=stage_filter)


@app.route("/deals/add", methods=["GET", "POST"])
@login_required
def add_deal():
    customers_list = Customer.query.order_by(Customer.name).all()
    preselect = request.args.get("customer_id", type=int)
    if request.method == "POST":
        expected = request.form.get("expected_close")
        expected_date = None
        if expected:
            try:
                expected_date = datetime.strptime(expected, "%Y-%m-%d").date()
            except ValueError:
                expected_date = None
        d = Deal(
            title=request.form.get("title", "").strip(),
            value=float(request.form.get("value") or 0),
            stage=request.form.get("stage", "New"),
            customer_id=request.form.get("customer_id", type=int),
            owner_id=current_user.id,
            expected_close=expected_date,
        )
        if not d.title or not d.customer_id:
            flash("Title and customer are required.", "error")
            return redirect(url_for("add_deal"))
        db.session.add(d)
        db.session.commit()
        flash("Deal added.", "success")
        return redirect(url_for("deals"))
    return render_template("deal_form.html", deal=None, customers=customers_list, stages=STAGES, preselect=preselect)


@app.route("/deals/<int:deal_id>/edit", methods=["GET", "POST"])
@login_required
def edit_deal(deal_id):
    deal = Deal.query.get_or_404(deal_id)
    customers_list = Customer.query.order_by(Customer.name).all()
    if request.method == "POST":
        expected = request.form.get("expected_close")
        deal.expected_close = None
        if expected:
            try:
                deal.expected_close = datetime.strptime(expected, "%Y-%m-%d").date()
            except ValueError:
                pass
        deal.title = request.form.get("title", "").strip()
        deal.value = float(request.form.get("value") or 0)
        deal.stage = request.form.get("stage", "New")
        deal.customer_id = request.form.get("customer_id", type=int)
        db.session.commit()
        flash("Deal updated.", "success")
        return redirect(url_for("deals"))
    return render_template("deal_form.html", deal=deal, customers=customers_list, stages=STAGES, preselect=None)


@app.route("/deals/<int:deal_id>/delete", methods=["POST"])
@login_required
def delete_deal(deal_id):
    deal = Deal.query.get_or_404(deal_id)
    db.session.delete(deal)
    db.session.commit()
    flash("Deal deleted.", "success")
    return redirect(url_for("deals"))


@app.route("/deals/<int:deal_id>/stage", methods=["POST"])
@login_required
def update_deal_stage(deal_id):
    deal = Deal.query.get_or_404(deal_id)
    stage = request.form.get("stage")
    if stage in STAGES:
        deal.stage = stage
        db.session.commit()
    return redirect(request.referrer or url_for("deals"))


# ---------- Attendance (Check In / Check Out) ----------

@app.route("/attendance")
@login_required
def attendance():
    today = date.today()
    my_today = Attendance.query.filter_by(user_id=current_user.id, date=today).first()

    if current_user.is_admin:
        team_today = (
            db.session.query(Attendance, User)
            .join(User, Attendance.user_id == User.id)
            .filter(Attendance.date == today)
            .all()
        )
        all_employees = User.query.order_by(User.name).all()
        checked_in_ids = {a.user_id for a, u in team_today}
        not_checked_in = [e for e in all_employees if e.id not in checked_in_ids]
    else:
        team_today = None
        not_checked_in = None

    my_history = (
        Attendance.query.filter_by(user_id=current_user.id)
        .order_by(Attendance.date.desc())
        .limit(20)
        .all()
    )

    return render_template(
        "attendance.html",
        my_today=my_today,
        team_today=team_today,
        not_checked_in=not_checked_in,
        my_history=my_history,
        today=today,
    )


@app.route("/attendance/checkin", methods=["POST"])
@login_required
def check_in():
    today = date.today()
    existing = Attendance.query.filter_by(user_id=current_user.id, date=today).first()
    if existing and existing.check_in:
        flash("You have already checked in today.", "error")
    else:
        if not existing:
            existing = Attendance(user_id=current_user.id, date=today)
            db.session.add(existing)
        existing.check_in = datetime.utcnow()
        db.session.commit()
        flash("Checked in successfully.", "success")
    return redirect(url_for("attendance"))


@app.route("/attendance/checkout", methods=["POST"])
@login_required
def check_out():
    today = date.today()
    existing = Attendance.query.filter_by(user_id=current_user.id, date=today).first()
    if not existing or not existing.check_in:
        flash("You need to check in first.", "error")
    elif existing.check_out:
        flash("You have already checked out today.", "error")
    else:
        existing.check_out = datetime.utcnow()
        db.session.commit()
        flash("Checked out successfully.", "success")
    return redirect(url_for("attendance"))


# ---------- Employees (Admin) ----------

@app.route("/employees")
@login_required
@admin_required
def employees():
    all_employees = User.query.order_by(User.name).all()
    return render_template("employees.html", employees=all_employees)


@app.route("/employees/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_employee():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or not password:
            flash("Name, email and password are required.", "error")
            return redirect(url_for("add_employee"))
        if User.query.filter_by(email=email).first():
            flash("This email is already registered.", "error")
            return redirect(url_for("add_employee"))
        employee = User(
            name=name,
            email=email,
            designation=request.form.get("designation", "").strip(),
            role=request.form.get("role", "Employee"),
            hourly_rate=float(request.form.get("hourly_rate") or 0),
            monthly_salary=float(request.form.get("monthly_salary") or 0),
        )
        employee.set_password(password)
        db.session.add(employee)
        db.session.commit()
        flash(f"Employee added. Share these login details with {employee.name}: {email} / (the password you set).", "success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=None)


@app.route("/employees/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_employee(user_id):
    employee = User.query.get_or_404(user_id)
    if request.method == "POST":
        employee.name = request.form.get("name", "").strip()
        employee.designation = request.form.get("designation", "").strip()
        employee.role = request.form.get("role", "Employee")
        employee.hourly_rate = float(request.form.get("hourly_rate") or 0)
        employee.monthly_salary = float(request.form.get("monthly_salary") or 0)
        new_password = request.form.get("password", "").strip()
        if new_password:
            employee.set_password(new_password)
        db.session.commit()
        flash("Employee updated.", "success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=employee)


@app.route("/employees/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_employee(user_id):
    if user_id == current_user.id:
        flash("You can't delete your own account.", "error")
        return redirect(url_for("employees"))
    employee = User.query.get_or_404(user_id)
    try:
        db.session.delete(employee)
        db.session.commit()
        flash("Employee removed.", "success")
    except Exception:
        db.session.rollback()
        flash("Can't remove this employee — they have customers, deals or tasks linked to them. Reassign those first.", "error")
    return redirect(url_for("employees"))


# ---------- Tasks ----------

@app.route("/tasks")
@login_required
def tasks():
    status_filter = request.args.get("status", "")
    if current_user.is_admin:
        query = Task.query
    else:
        query = Task.query.filter_by(assigned_to=current_user.id)
    if status_filter:
        query = query.filter_by(status=status_filter)
    all_tasks = query.order_by(Task.created_at.desc()).all()
    employees_list = User.query.order_by(User.name).all() if current_user.is_admin else None
    return render_template(
        "tasks.html", tasks=all_tasks, statuses=TASK_STATUSES, status_filter=status_filter,
        employees=employees_list,
    )


@app.route("/tasks/add", methods=["GET", "POST"])
@login_required
def add_task():
    employees_list = User.query.order_by(User.name).all()
    if request.method == "POST":
        due = request.form.get("due_date")
        due_date = None
        if due:
            try:
                due_date = datetime.strptime(due, "%Y-%m-%d").date()
            except ValueError:
                due_date = None
        assigned_to = request.form.get("assigned_to", type=int) if current_user.is_admin else current_user.id
        t = Task(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            assigned_to=assigned_to,
            assigned_by=current_user.id,
            time_limit_hours=float(request.form.get("time_limit_hours") or 0),
            due_date=due_date,
        )
        if not t.title or not t.assigned_to:
            flash("Title and assigned employee are required.", "error")
            return redirect(url_for("add_task"))
        db.session.add(t)
        db.session.commit()
        flash("Task added.", "success")
        return redirect(url_for("tasks"))
    return render_template("task_form.html", employees=employees_list, is_admin=current_user.is_admin)


@app.route("/tasks/<int:task_id>/start", methods=["POST"])
@login_required
def start_task(task_id):
    t = Task.query.get_or_404(task_id)
    if t.assigned_to != current_user.id and not current_user.is_admin:
        flash("You can only work on tasks assigned to you.", "error")
        return redirect(url_for("tasks"))
    t.status = "In Progress"
    t.started_at = datetime.utcnow()
    db.session.commit()
    flash("Task started. Timer is running.", "success")
    return redirect(url_for("tasks"))


@app.route("/tasks/<int:task_id>/complete", methods=["POST"])
@login_required
def complete_task(task_id):
    t = Task.query.get_or_404(task_id)
    if t.assigned_to != current_user.id and not current_user.is_admin:
        flash("You can only work on tasks assigned to you.", "error")
        return redirect(url_for("tasks"))
    t.status = "Completed"
    t.completed_at = datetime.utcnow()
    if not t.started_at:
        t.started_at = t.completed_at
    db.session.commit()
    flash(f"Task completed — took {t.time_spent_hours} hour(s).", "success")
    return redirect(url_for("tasks"))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    t = Task.query.get_or_404(task_id)
    if not current_user.is_admin and t.assigned_by != current_user.id:
        flash("You can't delete that task.", "error")
        return redirect(url_for("tasks"))
    db.session.delete(t)
    db.session.commit()
    flash("Task deleted.", "success")
    return redirect(url_for("tasks"))


# ---------- Payroll / Salary ----------

@app.route("/payroll")
@login_required
@admin_required
def payroll():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        year_i, month_i = map(int, month.split("-"))
    except ValueError:
        year_i, month_i = date.today().year, date.today().month
        month = date.today().strftime("%Y-%m")

    all_employees = User.query.order_by(User.name).all()
    rows = []
    for emp in all_employees:
        records = Attendance.query.filter(
            Attendance.user_id == emp.id,
            func.extract("year", Attendance.date) == year_i,
            func.extract("month", Attendance.date) == month_i,
        ).all()
        total_hours = sum(r.hours_worked for r in records)
        days_present = len([r for r in records if r.check_in])
        calculated_pay = emp.monthly_salary if emp.monthly_salary else round(total_hours * emp.hourly_rate, 2)
        rows.append({
            "employee": emp,
            "days_present": days_present,
            "total_hours": round(total_hours, 2),
            "calculated_pay": calculated_pay,
        })

    return render_template("payroll.html", rows=rows, month=month)


# ---------- Leave Management ----------

@app.route("/leaves")
@login_required
def leaves():
    if current_user.is_admin:
        all_leaves = Leave.query.order_by(Leave.created_at.desc()).all()
    else:
        all_leaves = Leave.query.filter_by(user_id=current_user.id).order_by(Leave.created_at.desc()).all()
    return render_template("leaves.html", leaves=all_leaves)


@app.route("/leaves/add", methods=["GET", "POST"])
@login_required
def add_leave():
    if request.method == "POST":
        try:
            from_date = datetime.strptime(request.form.get("from_date", ""), "%Y-%m-%d").date()
            to_date = datetime.strptime(request.form.get("to_date", ""), "%Y-%m-%d").date()
        except ValueError:
            flash("Please provide valid dates.", "error")
            return redirect(url_for("add_leave"))
        if to_date < from_date:
            flash("End date can't be before start date.", "error")
            return redirect(url_for("add_leave"))
        lv = Leave(
            user_id=current_user.id,
            from_date=from_date,
            to_date=to_date,
            reason=request.form.get("reason", "").strip(),
        )
        db.session.add(lv)
        db.session.commit()
        flash("Leave request submitted.", "success")
        return redirect(url_for("leaves"))
    return render_template("leave_form.html")


@app.route("/leaves/<int:leave_id>/decide", methods=["POST"])
@login_required
@admin_required
def decide_leave(leave_id):
    lv = Leave.query.get_or_404(leave_id)
    decision = request.form.get("decision")
    if decision in ("Approved", "Rejected"):
        lv.status = decision
        lv.decided_by = current_user.id
        db.session.commit()
        flash(f"Leave {decision.lower()}.", "success")
    return redirect(url_for("leaves"))


@app.route("/leaves/<int:leave_id>/delete", methods=["POST"])
@login_required
def delete_leave(leave_id):
    lv = Leave.query.get_or_404(leave_id)
    if lv.user_id != current_user.id and not current_user.is_admin:
        flash("You can't delete that request.", "error")
        return redirect(url_for("leaves"))
    db.session.delete(lv)
    db.session.commit()
    flash("Leave request removed.", "success")
    return redirect(url_for("leaves"))


# ---------- Notifications ----------

@app.route("/notifications")
@login_required
def notifications():
    return render_template("notifications.html", notes=get_notifications())


# ---------- Profile (Forgot Password self-service) ----------

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", "").strip() or current_user.name
        current_user.designation = request.form.get("designation", "").strip()

        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        if new_pw:
            if not current_pw or not current_user.check_password(current_pw):
                flash("Your current password is incorrect, so the password was not changed.", "error")
                return redirect(url_for("profile"))
            current_user.set_password(new_pw)
            flash("Profile and password updated.", "success")
        else:
            flash("Profile updated.", "success")
        db.session.commit()
        return redirect(url_for("profile"))
    return render_template("profile.html")


# ---------- File Attachments (Customers) ----------

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "docx", "xlsx", "csv", "txt"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/customers/<int:customer_id>/upload", methods=["POST"])
@login_required
def upload_attachment(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Please choose a file to upload.", "error")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    if not _allowed_file(file.filename):
        flash("That file type isn't allowed. Use PDF, image, Word, Excel, CSV or text files.", "error")
        return redirect(url_for("customer_detail", customer_id=customer_id))

    original_name = secure_filename(file.filename)
    stored_name = f"{uuid.uuid4().hex}_{original_name}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], stored_name))

    db.session.add(Attachment(
        customer_id=customer_id, filename=original_name, stored_name=stored_name, uploaded_by=current_user.id,
    ))
    db.session.commit()
    flash("File uploaded.", "success")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/uploads/<path:stored_name>")
@login_required
def download_attachment(stored_name):
    return send_from_directory(app.config["UPLOAD_FOLDER"], stored_name)


@app.route("/manifest.json")
def web_manifest():
    response = send_from_directory(app.static_folder, "manifest.json")
    response.headers["Content-Type"] = "application/manifest+json"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/offline")
def offline_page():
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Offline</title></head>"
        "<body style='font-family:sans-serif;text-align:center;padding:60px 20px;background:#F3F4EF;color:#16202A'>"
        "<h2>You're offline</h2><p>SoftAccess CRM needs an internet connection. Please reconnect and try again.</p>"
        "<button onclick='location.reload()' style='padding:10px 18px;border:0;border-radius:6px;background:#2F6F5E;color:#fff'>Retry</button>"
        "</body></html>"
    )


@app.route("/service-worker.js")
def service_worker():
    # Served from the site root (not /static/) so its scope covers the whole
    # app, not just the static folder — required for "Add to Home Screen" to
    # control every page, not only static assets.
    response = send_from_directory(app.static_folder, "service-worker.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Content-Type"] = "application/javascript"
    return response


@app.route("/attachments/<int:attachment_id>/delete", methods=["POST"])
@login_required
def delete_attachment(attachment_id):
    att = Attachment.query.get_or_404(attachment_id)
    customer_id = att.customer_id
    try:
        os.remove(os.path.join(app.config["UPLOAD_FOLDER"], att.stored_name))
    except OSError:
        pass
    db.session.delete(att)
    db.session.commit()
    flash("File removed.", "success")
    return redirect(url_for("customer_detail", customer_id=customer_id))


# ---------- Reports & CSV Export ----------

def _csv_response(rows, header, filename):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/customers/export")
@login_required
def export_customers():
    rows = [
        [c.name, c.company, c.email, c.phone, c.status, c.address, c.created_at.strftime("%Y-%m-%d")]
        for c in Customer.query.order_by(Customer.name).all()
    ]
    return _csv_response(rows, ["Name", "Company", "Email", "Phone", "Status", "Address", "Created"], "customers.csv")


@app.route("/deals/export")
@login_required
def export_deals():
    rows = [
        [d.title, d.customer.name, d.value, d.stage, d.expected_close.strftime("%Y-%m-%d") if d.expected_close else ""]
        for d in Deal.query.order_by(Deal.created_at.desc()).all()
    ]
    return _csv_response(rows, ["Title", "Customer", "Value", "Stage", "Expected Close"], "deals.csv")


@app.route("/payroll/export")
@login_required
@admin_required
def export_payroll():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        year_i, month_i = map(int, month.split("-"))
    except ValueError:
        year_i, month_i = date.today().year, date.today().month

    rows = []
    for emp in User.query.order_by(User.name).all():
        records = Attendance.query.filter(
            Attendance.user_id == emp.id,
            func.extract("year", Attendance.date) == year_i,
            func.extract("month", Attendance.date) == month_i,
        ).all()
        total_hours = sum(r.hours_worked for r in records)
        days_present = len([r for r in records if r.check_in])
        pay = emp.monthly_salary if emp.monthly_salary else round(total_hours * emp.hourly_rate, 2)
        rows.append([emp.name, days_present, round(total_hours, 2), emp.hourly_rate, emp.monthly_salary, pay])

    return _csv_response(
        rows, ["Employee", "Days Present", "Hours Worked", "Hourly Rate", "Monthly Salary", "Calculated Pay"],
        f"payroll_{month}.csv",
    )


@app.route("/attendance/export")
@login_required
def export_attendance():
    if current_user.is_admin:
        records = Attendance.query.order_by(Attendance.date.desc()).all()
    else:
        records = Attendance.query.filter_by(user_id=current_user.id).order_by(Attendance.date.desc()).all()
    rows = [
        [r.user.name, r.date.strftime("%Y-%m-%d"),
         r.check_in.strftime("%H:%M") if r.check_in else "",
         r.check_out.strftime("%H:%M") if r.check_out else "",
         r.hours_worked, r.status]
        for r in records
    ]
    return _csv_response(rows, ["Employee", "Date", "Check In", "Check Out", "Hours", "Status"], "attendance.csv")


# ---------- CLI helper to init db ----------

@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    # load_dotenv=False avoids a known crash between python-dotenv and very new
    # Python versions (e.g. 3.14) when Flask's CLI tries to auto-load a .env file.
    # This block only runs for local development (python app.py). A live host like
    # Railway/Render uses gunicorn instead, which never calls app.run().
    app.run(debug=True, load_dotenv=False)
