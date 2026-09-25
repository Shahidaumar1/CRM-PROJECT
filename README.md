# SoftAccess CRM

A complete, working Customer Relationship Management (CRM) web app — built with **Python Flask** and **MySQL**.

## Features
- Login / Register (secure password hashing). **The very first account to register automatically becomes Admin** — everyone after that is an Employee.
- Dashboard — customer counts, leads, open pipeline value, sales pipeline by stage, recent activity, your check-in status, your open tasks
- Customers — add / edit / delete, search and filter by status (Lead, Active, Inactive)
- Customer detail page — contact info, notes/activity timeline, and their deals
- Deals — add / edit / delete, change stage (New → Contacted → Proposal → Won/Lost) directly from the table
- **Attendance** — employees check in / check out with one click; admins see the whole team's status for today and who's absent
- **Tasks** — assign a task to an employee with a time limit (in hours); employee clicks Start / Complete and the actual time taken is calculated automatically and compared to the limit
- **Employees** (Admin only) — manage everyone's role, designation, hourly rate, or a fixed monthly salary
- **Payroll** (Admin only) — pick a month and see each employee's days present, hours worked, and calculated pay (hours × hourly rate, or the fixed monthly salary if set)
- MySQL database (works with XAMPP)
- Responsive design (works on mobile too)

## Roles
- **Admin** — full access: Customers, Deals, Attendance (team view), Tasks (assign to anyone), Employees, Payroll, Leave approvals.
- **Employee** — Customers, Deals, their own Attendance, their own Tasks, and their own Leave requests only.

The first person to register becomes Admin. To make someone else an Admin later, go to **Employees → Edit** and change their Role.

## More Features
- **Leave Management** — employees submit leave requests; admins approve or reject them from the Leaves page.
- **Profile & Password Change** — every user can update their own name and password from the Profile page (their avatar/name in the sidebar). If someone forgets their password entirely, an Admin can reset it from Employees → Edit.
- **Reports & Export** — "Export CSV" buttons on Customers, Deals, Attendance and Payroll let you download the data straight into Excel.
- **Notifications** — the bell-style "Notifications" link in the sidebar shows overdue/upcoming task deadlines and (for Admins) pending leave requests, with a live count badge.
- **Dashboard Analytics** — the dashboard now shows a 6-month "Won Deals" bar chart and a "Top Customers by Deal Value" chart.
- **File Attachments** — each customer's detail page has a Files section to upload and download documents (quotations, contracts, IDs, etc. — PDF, images, Word, Excel, CSV, text; 10 MB max per file).

## Setup (with XAMPP / MySQL)

This project uses **MySQL** — not SQLite.

1. Open **XAMPP Control Panel** and click "Start" next to **MySQL** (Apache is not required, only MySQL).
2. Open `http://localhost/phpmyadmin` in your browser.
3. Click "New" at the top, name the database `crm_db`, and click "Create".
   (If you change `DB_NAME` in `app.py`, use that name instead.)
4. Make sure Python 3.9+ is installed. In your terminal/CMD, go to the project folder:
   ```bash
   cd crm_project
   ```
5. Create a virtual environment (optional but recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate      # On Windows: venv\Scripts\activate
   ```
6. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
7. Run the app:
   ```bash
   python app.py
   ```
8. Open your browser at: **http://127.0.0.1:5000**

When the app starts, Flask automatically creates the tables (`user`, `customer`, `deal`, `activity`) inside `crm_db`. Register an account first, then log in.

### If your MySQL password isn't blank
At the top of `app.py` you'll find:
```python
DB_USER = "root"
DB_PASSWORD = ""          # enter your MySQL password here
DB_HOST = "localhost"
DB_PORT = "3306"
DB_NAME = "crm_db"
```
Update these to match your XAMPP MySQL username/password.

## Project Structure
```
crm_project/
├── app.py                  # Flask routes, app logic, and MySQL connection settings
├── models.py                # Database models (User, Customer, Deal, Activity)
├── requirements.txt
├── static/
│   └── css/style.css        # Styling
└── templates/
    ├── base.html
    ├── login.html / register.html
    ├── dashboard.html
    ├── customers.html / customer_form.html / customer_detail.html
    └── deals.html / deal_form.html
```

## Ideas to Extend
- Email/SMS reminders for follow-ups
- Multiple users with roles (Admin / Sales Agent)
- CSV export / import
- Kanban-style drag & drop board for deals
- File attachments (quotations, invoices)

## Going Live (Deploy to Railway)

This project can't go live on GitHub or Vercel by itself (see explanation below), but **Railway** hosts the app *and* gives you a free MySQL database in the same place. Steps:

1. Push this project to a GitHub repository (see the Git commands your assistant gave you earlier).
2. Go to [railway.app](https://railway.app) and sign up (you can sign in with GitHub).
3. Click **New Project → Deploy from GitHub repo**, and select your repository.
4. In the same project, click **+ New → Database → Add MySQL**. Railway creates a MySQL instance for you.
5. Click the MySQL service → **Variables** tab, and note the values for `MYSQLHOST`, `MYSQLPORT`, `MYSQLUSER`, `MYSQLPASSWORD`, `MYSQLDATABASE`.
6. Click your **web app service** → **Variables** tab, and add:
   ```
   DB_HOST      = (the MYSQLHOST value)
   DB_PORT      = (the MYSQLPORT value)
   DB_USER      = (the MYSQLUSER value)
   DB_PASSWORD  = (the MYSQLPASSWORD value)
   DB_NAME      = (the MYSQLDATABASE value)
   SECRET_KEY   = (any long random string)
   ```
7. Railway will detect the `Procfile` and run `gunicorn app:app` automatically. Wait for the deploy to finish, then open the generated public URL — your CRM is live.
8. Register your first account on the live URL — it becomes Admin, same as locally.

Your local XAMPP setup and the live Railway site use **separate databases** — data doesn't sync between them automatically.

## Production Note
`SECRET_KEY` and all database credentials are now read from environment variables (see `app.py`), with safe local defaults for XAMPP. Never commit real production passwords into `app.py` or GitHub — always set them as environment variables on your host instead.
