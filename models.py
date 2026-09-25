from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="Employee")   # Admin, Employee
    designation = db.Column(db.String(120))
    hourly_rate = db.Column(db.Float, default=0)
    monthly_salary = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attendances = db.relationship("Attendance", backref="user", cascade="all, delete-orphan", lazy=True)
    tasks = db.relationship("Task", backref="assignee", foreign_keys="Task.assigned_to", cascade="all, delete-orphan", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "Admin"


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    company = db.Column(db.String(150))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(50))
    address = db.Column(db.String(255))
    status = db.Column(db.String(30), default="Lead")  # Lead, Active, Inactive
    notes = db.Column(db.Text)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    deals = db.relationship("Deal", backref="customer", cascade="all, delete-orphan", lazy=True)
    activities = db.relationship("Activity", backref="customer", cascade="all, delete-orphan", lazy=True)

    @property
    def open_deal_value(self):
        return sum(d.value for d in self.deals if d.stage not in ("Won", "Lost"))


class Deal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    value = db.Column(db.Float, default=0)
    stage = db.Column(db.String(30), default="New")  # New, Contacted, Proposal, Won, Lost
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expected_close = db.Column(db.Date, nullable=True)


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"))


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow().date, nullable=False)
    check_in = db.Column(db.DateTime, nullable=True)
    check_out = db.Column(db.DateTime, nullable=True)

    @property
    def hours_worked(self):
        if self.check_in and self.check_out:
            return round((self.check_out - self.check_in).total_seconds() / 3600, 2)
        return 0

    @property
    def status(self):
        if self.check_in and self.check_out:
            return "Checked Out"
        if self.check_in:
            return "Checked In"
        return "Absent"


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    time_limit_hours = db.Column(db.Float, default=0)   # employee's estimated time limit for the task
    status = db.Column(db.String(20), default="Pending")  # Pending, In Progress, Completed
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def time_spent_hours(self):
        if self.started_at and self.completed_at:
            return round((self.completed_at - self.started_at).total_seconds() / 3600, 2)
        return 0

    @property
    def is_over_limit(self):
        if self.time_limit_hours and self.time_spent_hours:
            return self.time_spent_hours > self.time_limit_hours
        return False


class Leave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    from_date = db.Column(db.Date, nullable=False)
    to_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default="Pending")  # Pending, Approved, Rejected
    decided_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])

    @property
    def days(self):
        return (self.to_date - self.from_date).days + 1


class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)     # name shown to the user
    stored_name = db.Column(db.String(255), nullable=False)  # actual name on disk
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer", backref=db.backref("attachments", cascade="all, delete-orphan", lazy=True))
