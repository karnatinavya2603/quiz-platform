import sqlite3
import os
import csv
import json
import io
import random
import smtplib
import threading
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from flask import Flask, request, redirect, session, render_template_string, jsonify, send_file
from datetime import datetime
from quiz_runner import generate_testcases, run_code
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.secret_key = "quiz_secret_2026"

DB_FILE = os.path.join(os.path.dirname(__file__), "quiz.db")

from config import SMTP_SENDER, SMTP_PASSWORD, ADMIN_EMAIL, SMTP_PORT, SMTP_USE_SSL

# ── DB ────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    UNIQUE NOT NULL,
            email    TEXT    NOT NULL,
            password TEXT    NOT NULL,
            role     TEXT    NOT NULL DEFAULT 'user',
            approved INTEGER NOT NULL DEFAULT 0,
            token    TEXT
        )
        """)
        # Navya = admin, pre-approved
        conn.execute("""
        INSERT OR IGNORE INTO users(id,username,email,password,role,approved)
        VALUES (1,'navya','navyakarnati2603@gmail.com','navya@admin','admin',1)
        """)
        conn.commit()

init_db()

# ── PDF Generator ─────────────────────────────────────────────
def generate_result_pdf(username, mcq_score, mcq_total, coding_score, all_results):
    path   = f"/tmp/result_{username}.pdf"
    doc    = SimpleDocTemplate(path, pagesize=A4, rightMargin=40, leftMargin=40,
                                topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story  = []

    # Title
    story.append(Paragraph("Quiz Platform — Result Report", ParagraphStyle(
        'Title', parent=styles['Title'], fontSize=20, textColor=colors.HexColor('#1e2a3a'), spaceAfter=6)))
    story.append(Paragraph(f"Candidate: <b>{username}</b>", styles['Normal']))
    story.append(Paragraph(f"Date: {datetime.now().strftime('%d %B %Y  %I:%M %p')}", styles['Normal']))
    story.append(Spacer(1, 16))

    # Score summary table
    total = mcq_score + coding_score
    summary = [
        ['Section', 'Score'],
        ['MCQ', f"{mcq_score} / {mcq_total}"],
        ['Coding', f"{coding_score}"],
        ['Total Score', f"{total}"],
    ]
    t = Table(summary, colWidths=[280, 160])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e2a3a')),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,-1), 11),
        ('BACKGROUND', (0,3), (-1,3), colors.HexColor('#28a745')),
        ('TEXTCOLOR',  (0,3), (-1,3), colors.white),
        ('FONTNAME',   (0,3), (-1,3), 'Helvetica-Bold'),
        ('GRID',       (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,2), [colors.HexColor('#f8f9fa'), colors.white]),
        ('PADDING',    (0,0), (-1,-1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    # Coding test case details
    if all_results:
        story.append(Paragraph("Coding Test Case Results", ParagraphStyle(
            'H2', parent=styles['Heading2'], fontSize=13,
            textColor=colors.HexColor('#1e2a3a'), spaceAfter=6)))
        for i, item in enumerate(all_results, 1):
            story.append(Paragraph(f"Q{i}: {item['question']}", styles['Heading3']))
            rows = [['Input', 'Expected', 'Got', 'Result']]
            for r in item['results']:
                rows.append([r['input'], r['expected'], r['output'],
                              r['status']])
            ct = Table(rows, colWidths=[110, 110, 110, 80])
            ct.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#343a40')),
                ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
                ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0,0), (-1,-1), 9),
                ('GRID',       (0,0), (-1,-1), 0.4, colors.grey),
                ('PADDING',    (0,0), (-1,-1), 6),
                *[('BACKGROUND', (3, ri), (3, ri),
                   colors.HexColor('#d4edda') if rows[ri][3]=='PASS' else colors.HexColor('#f8d7da'))
                  for ri in range(1, len(rows))]
            ]))
            story.append(ct)
            story.append(Spacer(1, 10))

    doc.build(story)
    return path


# ── Email helper ──────────────────────────────────────────────
def send_email_async(to, subject, body, pdf_path=None):
    def _send():
        try:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"]    = SMTP_SENDER
            msg["To"]      = to
            msg.attach(MIMEText(body, "html"))

            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f"attachment; filename=result_{to.split('@')[0]}.pdf")
                msg.attach(part)

            if SMTP_USE_SSL:
                with smtplib.SMTP_SSL("smtp.gmail.com", SMTP_PORT) as s:
                    s.login(SMTP_SENDER, SMTP_PASSWORD)
                    s.send_message(msg)
            else:
                with smtplib.SMTP("smtp.gmail.com", SMTP_PORT) as s:
                    s.starttls()
                    s.login(SMTP_SENDER, SMTP_PASSWORD)
                    s.send_message(msg)
            print(f"[EMAIL] Sent to {to}")
        except Exception as e:
            print(f"[EMAIL ERROR] {e}")
    threading.Thread(target=_send, daemon=True).start()

def notify_admin_new_login(username, email, role, time_str):
    """Tell Navya (admin) that someone just logged in."""
    body = f"""
    <h3>Quiz Platform — Login Alert</h3>
    <p><b>User:</b> {username}</p>
    <p><b>Email:</b> {email}</p>
    <p><b>Role:</b> {role}</p>
    <p><b>Time:</b> {time_str}</p>
    """
    send_email_async(ADMIN_EMAIL, f"[Quiz] Login: {username}", body)

def notify_user_login(to_email, username):
    """Welcome email to the user who just logged in."""
    body = f"""
    <h3>Welcome, {username}!</h3>
    <p>You have successfully logged in to the Quiz Platform.</p>
    <p>Good luck with your exam!</p>
    """
    send_email_async(to_email, "Quiz Platform — Login Successful", body)

def notify_admin_new_register(username, email, role="user", token=""):
    """Tell Navya someone registered — includes one-click Approve button."""
    approve_url = f"{request.host_url.rstrip('/')}/approve_token/{token}"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;border:1px solid #ddd;border-radius:10px;padding:24px;">
      <h2 style="color:#333;">New Registration — Approval Needed</h2>
      <p><b>Username:</b> {username}</p>
      <p><b>Email:</b> {email}</p>
      <p><b>Registered As:</b> {role.capitalize()}</p>
      <hr>
      <p>Click the button below to approve this account:</p>
      <a href="{approve_url}"
         style="display:inline-block;padding:12px 28px;background:#28a745;color:#fff;
                text-decoration:none;border-radius:6px;font-size:16px;font-weight:bold;">
        Approve {username}
      </a>
      <p style="color:#999;font-size:12px;margin-top:16px;">
        This link approves the account instantly — no login required.
      </p>
    </div>
    """
    send_email_async(ADMIN_EMAIL, f"[Quiz] New Registration ({role}): {username}", body)

# ── CSS ───────────────────────────────────────────────────────
CSS = """
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body { background: #f0f2f5; }
  .card { border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,.1); }
</style>
"""

# ── Routes ────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect('/login')

@app.route('/test_email')
def test_email():
    from config import ADMIN_EMAIL, SMTP_SENDER, SMTP_PORT, SMTP_USE_SSL, SMTP_PASSWORD
    import smtplib
    from email.mime.text import MIMEText
    
    res = f"Testing Email with: Port={SMTP_PORT}, SSL={SMTP_USE_SSL}, Sender={SMTP_SENDER}<br>"
    try:
        msg = MIMEText("This is a test email from your Quiz Platform.")
        msg["Subject"] = "SMTP Test"
        msg["From"] = SMTP_SENDER
        msg["To"] = ADMIN_EMAIL
        
        if SMTP_USE_SSL:
            with smtplib.SMTP_SSL("smtp.gmail.com", SMTP_PORT, timeout=10) as s:
                s.login(SMTP_SENDER, SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP("smtp.gmail.com", SMTP_PORT, timeout=10) as s:
                s.starttls()
                s.login(SMTP_SENDER, SMTP_PASSWORD)
                s.send_message(msg)
        return res + "<h3 style='color:green'>Success! Email sent.</h3>"
    except Exception as e:
        return res + f"<h3 style='color:red'>Failed!</h3> Error: {str(e)}"


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if not user:
            error = "Invalid username or password."
        elif user['role'] == 'user' and not user['approved']:
            error = "Your account is pending admin approval."
        else:
            # Save session
            session.clear()
            session['username'] = user['username']
            session['email']    = user['email']
            session['role']     = user['role']

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Track login count and last login time
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET login_count = login_count + 1, last_login = ? WHERE username = ?",
                    (now, user['username'])
                )
                conn.commit()

            # Email: notify admin about any login
            notify_admin_new_login(user['username'], user['email'], user['role'], now)

            # Email: welcome the user themselves (skip for admin to avoid noise)
            if user['role'] == 'user':
                notify_user_login(user['email'], user['username'])

            if user['role'] == 'admin':
                return redirect('/admin')
            return redirect('/dashboard')

    return render_template_string(CSS + """
    <div class="container mt-5 d-flex justify-content-center">
      <div class="card p-4" style="width:380px">
        <h4 class="mb-3 text-center">Quiz Platform Login</h4>
        {% if error %}
          <div class="alert alert-danger py-2">{{ error }}</div>
        {% endif %}
        <form method="post">
          <div class="mb-3">
            <label class="form-label">Username</label>
            <input name="username" class="form-control" required autofocus>
          </div>
          <div class="mb-3">
            <label class="form-label">Password</label>
            <input name="password" type="password" class="form-control" required>
          </div>
          <button class="btn btn-primary w-100">Login</button>
        </form>
        <hr>
        <p class="text-center mb-0">No account? <a href="/register">Register</a></p>
      </div>
    </div>
    """, error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role     = request.form.get('role', 'user').strip()

        if role not in ('admin', 'user'):
            role = 'user'

        if not username or not email or not password:
            msg = "All fields are required."
        else:
            try:
                token = secrets.token_urlsafe(32)
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO users(username,email,password,role,approved,token) VALUES(?,?,?,?,0,?)",
                        (username, email, password, role, token)
                    )
                    conn.commit()
                notify_admin_new_register(username, email, role, token)
                return render_template_string(CSS + """
                <div class="container mt-5 d-flex justify-content-center">
                  <div class="card p-4 text-center" style="width:380px">
                    <h5>Registration Submitted!</h5>
                    <p>Navya (admin) will review and approve your account.<br>
                       You will be able to login once approved.</p>
                    <a href="/login" class="btn btn-primary">Back to Login</a>
                  </div>
                </div>
                """)
            except sqlite3.IntegrityError:
                msg = "Username already taken."

    return render_template_string(CSS + """
    <div class="container mt-5 d-flex justify-content-center">
      <div class="card p-4" style="width:380px">
        <h4 class="mb-3 text-center">Register</h4>
        {% if msg %}
          <div class="alert alert-danger py-2">{{ msg }}</div>
        {% endif %}
        <form method="post">
          <div class="mb-3">
            <label class="form-label">Username</label>
            <input name="username" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Email</label>
            <input name="email" type="email" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Password</label>
            <input name="password" type="password" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label fw-semibold">Register As</label>
            <div class="d-flex gap-3 mt-1">
              <div class="form-check">
                <input class="form-check-input" type="radio" name="role" id="roleUser" value="user" checked>
                <label class="form-check-label" for="roleUser">
                  <span class="badge bg-primary fs-6 px-3 py-2">User</span>
                </label>
              </div>
              <div class="form-check">
                <input class="form-check-input" type="radio" name="role" id="roleAdmin" value="admin">
                <label class="form-check-label" for="roleAdmin">
                  <span class="badge bg-danger fs-6 px-3 py-2">Admin</span>
                </label>
              </div>
            </div>
          </div>
          <button class="btn btn-success w-100">Register</button>
        </form>
        <hr>
        <p class="text-center mb-0">Already registered? <a href="/login">Login</a></p>
      </div>
    </div>
    """, msg=msg)


# ── User dashboard ────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if not session.get('username') or session.get('role') != 'user':
        return redirect('/login')

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (session['username'],)).fetchone()
    try:
        mcq_count = conn.execute("SELECT COUNT(*) FROM questions WHERE published=1").fetchone()[0]
    except:
        mcq_count = 0
    try:
        coding_count = conn.execute("SELECT COUNT(*) FROM coding_questions WHERE published=1").fetchone()[0]
    except:
        coding_count = 0
    conn.close()

    quiz_status = user['quiz_status'] or 'not_started'
    quiz_score  = user['quiz_score'] or 0
    login_count = user['login_count'] or 0
    last_login  = user['last_login'] or 'First time'

    status_color = {'not_started': 'secondary', 'in_progress': 'warning', 'completed': 'success'}
    status_label = {'not_started': 'Not Started', 'in_progress': 'In Progress', 'completed': 'Completed'}

    return render_template_string(CSS + """
    <style>
      .stat-card { border-radius:12px; padding:18px 20px; color:#fff; }
      .stat-card h2 { font-size:2rem; font-weight:700; margin:0; }
      .stat-card p  { margin:4px 0 0; font-size:.85rem; opacity:.9; }
      body { background:#f0f2f5; }
      .topbar { background:#1e2a3a; color:#fff; padding:14px 28px;
                display:flex; justify-content:space-between; align-items:center; }
      .exam-card { border-radius:14px; overflow:hidden; transition:transform .2s; }
      .exam-card:hover { transform:translateY(-4px); box-shadow:0 8px 24px rgba(0,0,0,.15); }
    </style>

    <!-- Top bar -->
    <div class="topbar">
      <div>
        <span style="font-size:1.1rem;font-weight:600;">Quiz Platform</span>
        <span class="ms-3 text-muted" style="font-size:.85rem;">{{ now }}</span>
      </div>
      <div class="d-flex align-items-center gap-3">
        <span style="font-size:.9rem;">Hello, <b>{{ username }}</b></span>
        <a href="/logout" class="btn btn-sm btn-outline-light">Logout</a>
      </div>
    </div>

    <div class="container py-4">

      <!-- Welcome Banner -->
      <div class="card mb-4 p-4" style="background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border-radius:14px;">
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <h4 class="mb-1">Welcome back, <b>{{ username }}</b>!</h4>
            <p class="mb-0" style="opacity:.85;">Ready to take your exam? Choose a section below.</p>
          </div>
          <div class="text-end">
            <span class="badge bg-light text-dark fs-6 px-3 py-2">
              Quiz: <b>{{ status_label }}</b>
            </span>
          </div>
        </div>
      </div>

      <!-- Stat Cards -->
      <div class="row g-3 mb-4">
        <div class="col-md-3">
          <div class="stat-card" style="background:linear-gradient(135deg,#11998e,#38ef7d);">
            <h2>{{ quiz_score }}</h2>
            <p>Your Score</p>
          </div>
        </div>
        <div class="col-md-3">
          <div class="stat-card" style="background:linear-gradient(135deg,#2193b0,#6dd5ed);">
            <h2>{{ mcq_count }}</h2>
            <p>MCQ Questions</p>
          </div>
        </div>
        <div class="col-md-3">
          <div class="stat-card" style="background:linear-gradient(135deg,#f7971e,#ffd200);">
            <h2>{{ coding_count }}</h2>
            <p>Coding Questions</p>
          </div>
        </div>
        <div class="col-md-3">
          <div class="stat-card" style="background:linear-gradient(135deg,#e96c75,#c0392b);">
            <h2>{{ login_count }}</h2>
            <p>Times Logged In</p>
          </div>
        </div>
      </div>

      <!-- Exam Cards -->
      <div class="row g-4 mb-4">
        <div class="col-md-6">
          <div class="card exam-card">
            <div style="background:linear-gradient(135deg,#0061ff,#60efff);padding:24px;color:#fff;">
              <h5 class="mb-1">MCQ Exam</h5>
              <p class="mb-0" style="opacity:.85;">Multiple choice questions — 10 sec per question</p>
            </div>
            <div class="p-3 d-flex justify-content-between align-items-center">
              <span class="text-muted">{{ mcq_count }} questions available</span>
              {% if quiz_status == 'completed' %}
                <span class="btn btn-secondary btn-sm disabled">Completed</span>
              {% else %}
                <a href="/quiz" class="btn btn-primary btn-sm">Start MCQ</a>
              {% endif %}
            </div>
          </div>
        </div>
        <div class="col-md-6">
          <div class="card exam-card">
            <div style="background:linear-gradient(135deg,#11998e,#38ef7d);padding:24px;color:#fff;">
              <h5 class="mb-1">Coding Exam</h5>
              <p class="mb-0" style="opacity:.85;">Write Python code — 30 min timer</p>
            </div>
            <div class="p-3 d-flex justify-content-between align-items-center">
              <span class="text-muted">{{ coding_count }} questions available</span>
              {% if quiz_status == 'completed' %}
                <span class="btn btn-secondary btn-sm disabled">Completed</span>
              {% else %}
                <a href="/coding" class="btn btn-success btn-sm">Start Coding</a>
              {% endif %}
            </div>
          </div>
        </div>
      </div>

      <!-- Info Card -->
      <div class="card p-3">
        <h6 class="mb-3 text-muted">Your Activity</h6>
        <div class="row text-center">
          <div class="col-md-4 border-end">
            <p class="mb-1 text-muted" style="font-size:.85rem;">Quiz Status</p>
            <span class="badge bg-{{ status_color }} fs-6 px-3 py-2">{{ status_label }}</span>
          </div>
          <div class="col-md-4 border-end">
            <p class="mb-1 text-muted" style="font-size:.85rem;">Total Logins</p>
            <b style="font-size:1.2rem;">{{ login_count }}</b>
          </div>
          <div class="col-md-4">
            <p class="mb-1 text-muted" style="font-size:.85rem;">Last Login</p>
            <b style="font-size:.9rem;">{{ last_login }}</b>
          </div>
        </div>
      </div>

    </div>
    """,
    username=session['username'],
    now=datetime.now().strftime("%A, %d %B %Y  %I:%M %p"),
    quiz_status=quiz_status,
    quiz_score=quiz_score,
    login_count=login_count,
    last_login=last_login,
    mcq_count=mcq_count,
    coding_count=coding_count,
    status_color=status_color[quiz_status],
    status_label=status_label[quiz_status]
    )


# ── Admin dashboard ───────────────────────────────────────────
@app.route('/admin')
def admin():
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db()
    users        = conn.execute("SELECT * FROM users WHERE role='user'").fetchall()
    total        = len(users)
    approved     = sum(1 for u in users if u['approved'])
    pending      = total - approved
    completed    = sum(1 for u in users if u['quiz_status'] == 'completed')
    inprogress   = sum(1 for u in users if u['quiz_status'] == 'in_progress')
    not_started  = sum(1 for u in users if u['quiz_status'] == 'not_started' and u['approved'])
    total_logins = conn.execute("SELECT SUM(login_count) FROM users WHERE role='user'").fetchone()[0] or 0

    try:
        mcq_total     = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        mcq_count     = conn.execute("SELECT COUNT(*) FROM questions WHERE published=1").fetchone()[0]
    except:
        mcq_total = mcq_count = 0
    try:
        coding_total  = conn.execute("SELECT COUNT(*) FROM coding_questions").fetchone()[0]
        coding_count  = conn.execute("SELECT COUNT(*) FROM coding_questions WHERE published=1").fetchone()[0]
    except:
        coding_total = coding_count = 0
    conn.close()

    return render_template_string(CSS + """
    <style>
      .stat-card { border-radius:12px; padding:20px; color:#fff; text-align:center; }
      .stat-card h2 { font-size:2.5rem; font-weight:700; margin:0; }
      .stat-card p  { margin:4px 0 0; font-size:.95rem; opacity:.9; }
      .sidebar { background:#1e2a3a; min-height:100vh; padding:20px 0; }
      .sidebar a { display:block; color:#adb5bd; padding:10px 24px; text-decoration:none; font-size:.95rem; }
      .sidebar a:hover, .sidebar a.active { background:#2c3e50; color:#fff; border-left:3px solid #0d6efd; }
      .sidebar .brand { color:#fff; font-size:1.2rem; font-weight:700; padding:10px 24px 20px; border-bottom:1px solid #2c3e50; margin-bottom:10px; }
      .main { padding:28px; background:#f0f2f5; min-height:100vh; }
      .badge-status { font-size:.8rem; padding:5px 10px; border-radius:20px; }
    </style>

    <div class="d-flex" style="min-height:100vh;">

      <!-- Sidebar -->
      <div class="sidebar" style="width:220px;flex-shrink:0;">
        <div class="brand">Quiz Admin</div>
        <a href="/admin" class="active">Dashboard</a>
        <a href="/admin/users">Manage Users</a>
        <a href="/admin/add_mcq">Add MCQ</a>
        <a href="/admin/add_coding">Add Coding</a>
        <a href="/admin/upload">Upload Questions</a>
        <a href="/logout" style="color:#e74c3c;margin-top:20px;">Logout</a>
      </div>

      <!-- Main -->
      <div class="main flex-grow-1">

        <!-- Header -->
        <div class="d-flex justify-content-between align-items-center mb-4">
          <div>
            <h4 class="mb-0">Welcome back, <b>{{ username }}</b></h4>
            <small class="text-muted">{{ now }}</small>
          </div>
        </div>

        <!-- Stat Cards Row 1 -->
        <div class="row g-3 mb-4">
          <div class="col-md-3">
            <div class="stat-card" style="background:linear-gradient(135deg,#667eea,#764ba2);">
              <h2>{{ total }}</h2>
              <p>Total Registered</p>
            </div>
          </div>
          <div class="col-md-3">
            <div class="stat-card" style="background:linear-gradient(135deg,#11998e,#38ef7d);">
              <h2>{{ approved }}</h2>
              <p>Approved Users</p>
            </div>
          </div>
          <div class="col-md-3">
            <div class="stat-card" style="background:linear-gradient(135deg,#f7971e,#ffd200);">
              <h2>{{ pending }}</h2>
              <p>Pending Approval</p>
            </div>
          </div>
          <div class="col-md-3">
            <div class="stat-card" style="background:linear-gradient(135deg,#e96c75,#c0392b);">
              <h2>{{ total_logins }}</h2>
              <p>Total Logins</p>
            </div>
          </div>
        </div>

        <!-- Stat Cards Row 2 -->
        <div class="row g-3 mb-4">
          <div class="col-md-4">
            <div class="stat-card" style="background:linear-gradient(135deg,#2193b0,#6dd5ed);">
              <h2>{{ completed }}</h2>
              <p>Quiz Completed</p>
            </div>
          </div>
          <div class="col-md-4">
            <div class="stat-card" style="background:linear-gradient(135deg,#ee9ca7,#ffdde1);">
              <h2 style="color:#333;">{{ inprogress }}</h2>
              <p style="color:#555;">Quiz In Progress</p>
            </div>
          </div>
          <div class="col-md-4">
            <div class="stat-card" style="background:linear-gradient(135deg,#bdc3c7,#2c3e50);">
              <h2>{{ not_started }}</h2>
              <p>Not Started Yet</p>
            </div>
          </div>
        </div>

        <!-- Question Bank -->
        <div class="row g-3 mb-4">
          <div class="col-md-6">
            <div class="card p-3 text-center">
              <h5 class="text-muted">MCQ Questions</h5>
              <h2 class="text-primary">{{ mcq_count }}</h2>
              <p class="text-muted mb-1" style="font-size:.82rem;">Published &nbsp;|&nbsp; {{ mcq_total }} Total</p>
              <a href="/admin/add_mcq" class="btn btn-sm btn-outline-primary mt-1">+ Add MCQ</a>
            </div>
          </div>
          <div class="col-md-6">
            <div class="card p-3 text-center">
              <h5 class="text-muted">Coding Questions</h5>
              <h2 class="text-success">{{ coding_count }}</h2>
              <p class="text-muted mb-1" style="font-size:.82rem;">Published &nbsp;|&nbsp; {{ coding_total }} Total</p>
              <a href="/admin/add_coding" class="btn btn-sm btn-outline-success mt-1">+ Add Coding</a>
            </div>
          </div>
        </div>

        <!-- Pending Approvals -->
        {% if pending > 0 %}
        <div class="card p-3 mb-4 border-warning">
          <h6 class="text-warning mb-3">⚠ Pending Approvals ({{ pending }})</h6>
          <table class="table table-sm mb-0">
            <thead class="table-light">
              <tr><th>Username</th><th>Email</th><th>Action</th></tr>
            </thead>
            <tbody>
            {% for u in users if not u['approved'] %}
              <tr>
                <td>{{ u['username'] }}</td>
                <td>{{ u['email'] }}</td>
                <td><a href="/approve/{{ u['id'] }}" class="btn btn-sm btn-success">Approve</a></td>
              </tr>
            {% endfor %}
            </tbody>
          </table>
        </div>
        {% endif %}

        <!-- All Users Table -->
        <div class="card p-3">
          <h6 class="mb-3">All Users</h6>
          <table class="table table-hover table-sm mb-0">
            <thead class="table-dark">
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th>Status</th>
                <th>Quiz</th>
                <th>Score</th>
                <th>Logins</th>
                <th>Last Login</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
            {% for u in users %}
              <tr>
                <td><b>{{ u['username'] }}</b></td>
                <td>{{ u['email'] }}</td>
                <td>
                  {% if u['approved'] %}
                    <span class="badge bg-success badge-status">Approved</span>
                  {% else %}
                    <span class="badge bg-warning text-dark badge-status">Pending</span>
                  {% endif %}
                </td>
                <td>
                  {% if u['quiz_status'] == 'completed' %}
                    <span class="badge bg-success badge-status">Completed</span>
                  {% elif u['quiz_status'] == 'in_progress' %}
                    <span class="badge bg-info badge-status">In Progress</span>
                  {% else %}
                    <span class="badge bg-secondary badge-status">Not Started</span>
                  {% endif %}
                </td>
                <td>{{ u['quiz_score'] or '-' }}</td>
                <td>{{ u['login_count'] or 0 }}</td>
                <td style="font-size:.8rem;">{{ u['last_login'] or 'Never' }}</td>
                <td>
                  {% if not u['approved'] %}
                    <a href="/approve/{{ u['id'] }}" class="btn btn-sm btn-success">Approve</a>
                  {% else %}
                    <a href="/revoke/{{ u['id'] }}" class="btn btn-sm btn-outline-danger btn-sm">Revoke</a>
                  {% endif %}
                </td>
              </tr>
            {% else %}
              <tr><td colspan="8" class="text-center text-muted">No users registered yet.</td></tr>
            {% endfor %}
            </tbody>
          </table>
        </div>

      </div>
    </div>
    """,
    username=session['username'],
    now=datetime.now().strftime("%A, %d %B %Y  %I:%M %p"),
    users=users,
    total=total, approved=approved, pending=pending,
    completed=completed, inprogress=inprogress, not_started=not_started,
    total_logins=total_logins,
    mcq_count=mcq_count, mcq_total=mcq_total,
    coding_count=coding_count, coding_total=coding_total
    )


@app.route('/admin/users')
def admin_users():
    if session.get('role') != 'admin':
        return redirect('/login')
    return redirect('/admin')


@app.route('/approve/<int:uid>')
def approve(uid):
    if session.get('role') != 'admin':
        return redirect('/login')
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        conn.execute("UPDATE users SET approved=1 WHERE id=?", (uid,))
        conn.commit()
    if user:
        _send_approval_email(user['email'], user['username'])
    return redirect('/admin')


@app.route('/approve_token/<token>')
def approve_token(token):
    """One-click approve from email — no admin login needed."""
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
        if not user:
            return render_template_string(CSS + """
            <div class="container mt-5 d-flex justify-content-center">
              <div class="card p-4 text-center" style="width:400px">
                <h5 class="text-danger">Invalid or already used link.</h5>
                <a href="/admin" class="btn btn-primary mt-3">Go to Admin Panel</a>
              </div>
            </div>
            """)
        conn.execute("UPDATE users SET approved=1, token=NULL WHERE token=?", (token,))
        conn.commit()

    _send_approval_email(user['email'], user['username'])

    return render_template_string(CSS + """
    <div class="container mt-5 d-flex justify-content-center">
      <div class="card p-4 text-center" style="width:400px">
        <h2 style="color:#28a745;">&#10003; Approved!</h2>
        <p><b>{{ username }}</b> can now login to the platform.</p>
        <a href="/admin" class="btn btn-primary mt-2">Go to Admin Panel</a>
      </div>
    </div>
    """, username=user['username'])


def _send_approval_email(to_email, username):
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;border:1px solid #ddd;border-radius:10px;padding:24px;">
      <h2 style="color:#28a745;">Account Approved!</h2>
      <p>Hello <b>{username}</b>,</p>
      <p>Your account has been approved by the admin. You can now login:</p>
      <a href="http://127.0.0.1:5000/login"
         style="display:inline-block;padding:12px 28px;background:#007bff;color:#fff;
                text-decoration:none;border-radius:6px;font-size:16px;font-weight:bold;">
        Login Now
      </a>
    </div>
    """
    send_email_async(to_email, "Quiz Platform — Account Approved", body)


@app.route('/revoke/<int:uid>')
def revoke(uid):
    if session.get('role') != 'admin':
        return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE users SET approved=0 WHERE id=?", (uid,))
        conn.commit()
    return redirect('/admin')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ── MCQ Exam ──────────────────────────────────────────────────
@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    if session.get('role') != 'user':
        return redirect('/login')

    # Load questions into session once
    if 'q_list' not in session:
        conn = get_db()
        try:
            qs = conn.execute("SELECT * FROM questions WHERE published=1").fetchall()
        except:
            qs = []
        conn.close()
        if not qs:
            return render_template_string(CSS + """
            <div class="container mt-5 d-flex justify-content-center">
              <div class="card p-4 text-center" style="width:400px">
                <h5>No questions available yet</h5>
                <p class="text-muted">Admin has not published any MCQ questions.</p>
                <a href="/dashboard" class="btn btn-primary">Back to Dashboard</a>
              </div>
            </div>""")
        session['q_list']  = random.sample([dict(q) for q in qs], min(len(qs), 20))
        session['q_index'] = 0
        session['score']   = 0
        session['total']   = 0
        with get_db() as conn:
            conn.execute("UPDATE users SET quiz_status='in_progress' WHERE username=?",
                         (session['username'],))
            conn.commit()

    # Handle answer submission
    if request.method == 'POST':
        ans = request.form.get('opt', '').lower()
        q   = session['q_list'][session['q_index']]
        
        expected_ans = str(q['answer']).lower().strip()
        selected_text = str(q.get(ans, '')).lower().strip()
        
        if ans == expected_ans or selected_text == expected_ans:
            session['score'] += 1
            
        session['total']   += 1
        session['q_index'] += 1

    # All done → go to coding
    if session['q_index'] >= len(session['q_list']):
        return redirect('/coding')

    q   = session['q_list'][session['q_index']]
    num = session['q_index'] + 1
    tot = len(session['q_list'])

    return render_template_string(CSS + """
    <style>
      body { background:#f0f2f5; }
      .opt-label { display:block; border:2px solid #dee2e6; border-radius:10px;
                   padding:12px 16px; margin-bottom:10px; cursor:pointer;
                   transition:.2s; font-size:1rem; }
      .opt-label:hover { border-color:#0d6efd; background:#f0f4ff; }
      input[type=radio]:checked + .opt-label { border-color:#0d6efd; background:#e8f0fe; font-weight:600; }
      input[type=radio] { display:none; }
      .progress-bar { transition:width .4s ease; }
    </style>

    <!-- Top bar -->
    <div style="background:#1e2a3a;color:#fff;padding:12px 28px;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-weight:600;">MCQ Exam</span>
      <span>Question {{ num }} of {{ tot }}</span>
      <span style="font-size:1.1rem;">⏱ <span id="timer" style="font-weight:700;color:#ffd200;">10</span>s</span>
    </div>

    <!-- Progress bar -->
    <div class="progress" style="height:6px;border-radius:0;">
      <div class="progress-bar bg-primary" style="width:{{ (num/tot*100)|int }}%"></div>
    </div>

    <div class="container mt-4" style="max-width:680px;">
      <div class="card p-4 shadow-sm">
        <p class="text-muted mb-2" style="font-size:.85rem;">Question {{ num }} / {{ tot }}</p>
        <h5 class="mb-4">{{ q['question'] }}</h5>

        <form method="post" id="qform">
          <div>
            <input type="radio" name="opt" value="a" id="oa">
            <label for="oa" class="opt-label">A.&nbsp; {{ q['a'] }}</label>
          </div>
          <div>
            <input type="radio" name="opt" value="b" id="ob">
            <label for="ob" class="opt-label">B.&nbsp; {{ q['b'] }}</label>
          </div>
          <div>
            <input type="radio" name="opt" value="c" id="oc">
            <label for="oc" class="opt-label">C.&nbsp; {{ q['c'] }}</label>
          </div>
          <div>
            <input type="radio" name="opt" value="d" id="od">
            <label for="od" class="opt-label">D.&nbsp; {{ q['d'] }}</label>
          </div>

          <div class="d-flex justify-content-between align-items-center mt-3">
            <span class="text-muted" style="font-size:.85rem;">Score so far: <b>{{ score }}</b></span>
            <button class="btn btn-primary px-4">Next →</button>
          </div>
        </form>
      </div>
    </div>

    <script>
    let t = 10;
    const el = document.getElementById('timer');
    const iv = setInterval(() => {
      t--;
      el.innerText = t;
      if (t <= 3) el.style.color = '#e74c3c';
      if (t <= 0) { clearInterval(iv); document.getElementById('qform').submit(); }
    }, 1000);
    </script>
    """, q=q, num=num, tot=tot, score=session['score'])


# ── Coding Exam ───────────────────────────────────────────────
@app.route('/coding', methods=['GET', 'POST'])
def coding():
    if session.get('role') != 'user':
        return redirect('/login')

    # Load coding questions into session once
    if 'c_list' not in session:
        conn = get_db()
        try:
            qs = conn.execute("SELECT * FROM coding_questions WHERE published=1").fetchall()
        except:
            qs = []
        conn.close()
        if not qs:
            return render_template_string(CSS + """
            <div class="container mt-5 d-flex justify-content-center">
              <div class="card p-4 text-center" style="width:400px">
                <h5>No coding questions available</h5>
                <a href="/dashboard" class="btn btn-primary">Back to Dashboard</a>
              </div>
            </div>""")
        session['c_list']        = [dict(q) for q in qs]
        session['c_index']       = 0
        session['coding_score']  = 0
        session['test_results']  = []
        session['all_results']   = []
        session.setdefault('score', 0)

    if request.method == 'POST':
        code       = request.form.get('code', '')
        user_input = request.form.get('user_input', '')
        q          = session['c_list'][session['c_index']]

        tests   = generate_testcases(q['question'])
        results = []
        passed  = 0
        for inp, expected in tests:
            output = run_code(code, inp)
            ok     = output.strip() == expected.strip()
            if ok: passed += 1
            results.append({'input': inp, 'expected': expected,
                             'output': output, 'status': 'PASS' if ok else 'FAIL'})

        if passed == len(tests):
            session['coding_score'] += 15

        session['test_results'] = results
        session['all_results']  = session.get('all_results', []) + [
            {'question': q['question'], 'results': results}
        ]
        session['output']  = run_code(code, user_input)
        session['c_index'] += 1

    if session['c_index'] >= len(session['c_list']):
        return redirect('/result')

    q = session['c_list'][session['c_index']]

    return render_template_string(CSS + """
    <style>body{background:#f0f2f5;}</style>

    <!-- Top bar -->
    <div style="background:#1e2a3a;color:#fff;padding:12px 28px;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-weight:600;">Coding Exam — Question {{ cidx }} of {{ ctot }}</span>
      <span>⏱ <span id="timer" style="font-weight:700;color:#ffd200;"></span></span>
    </div>
    <div class="progress" style="height:6px;border-radius:0;">
      <div class="progress-bar bg-success" style="width:{{ (cidx/ctot*100)|int }}%"></div>
    </div>

    <div class="container mt-3" style="max-width:960px;">
      <div class="row g-3">

        <!-- Question panel -->
        <div class="col-md-4">
          <div class="card p-3 h-100">
            <h6>{{ q['question'] }}</h6>
            <hr>
            <p class="mb-1"><b>Sample Input:</b><br><code>{{ q['sample_input'] }}</code></p>
            <p class="mb-0"><b>Sample Output:</b><br><code>{{ q['sample_output'] }}</code></p>

            {% if test_results %}
            <hr>
            <h6>Test Results</h6>
            {% for t in test_results %}
            <div class="p-2 rounded mb-1 {{ 'bg-success' if t.status=='PASS' else 'bg-danger' }} text-white" style="font-size:.78rem;">
              <b>{{ t.status }}</b> | in: {{ t.input }} | exp: {{ t.expected }} | got: {{ t.output }}
            </div>
            {% endfor %}
            {% endif %}
          </div>
        </div>

        <!-- Editor panel -->
        <div class="col-md-8">
          <div class="card p-3">
            <form method="post" id="cform">
              <div class="d-flex justify-content-between align-items-center mb-2 bg-light p-2 rounded-top border-bottom">
                <div class="d-flex align-items-center gap-2">
                  <select id="lang_select" class="form-select form-select-sm fw-bold border-0 bg-transparent" style="width:auto; cursor:pointer;" onchange="updateMode()">
                    <option value="python">🐍 Python 3 (IDLE Mode)</option>
                  </select>
                  <span id="compiler_badge" class="badge rounded-pill bg-success" style="font-size:0.65rem; padding: 4px 8px;">REAL-TIME ACTIVE</span>
                </div>
                <div class="d-flex align-items-center gap-3">
                  <div class="form-check form-switch mb-0">
                    <input class="form-check-input" type="checkbox" id="live_run_toggle" checked>
                    <label class="form-check-label text-muted" style="font-size:0.75rem;" for="live_run_toggle">Auto-Run</label>
                  </div>
                  <span id="run_status" class="badge bg-secondary" style="font-size: 0.65rem;">IDLE</span>
                </div>
              </div>
              <div id="editor" style="height:350px; border: 1px solid #dee2e6; border-top:0; position: relative; width: 100%; display: block; background: #272822; z-index: 10;"></div>
              <textarea name="code" id="code_ta" hidden></textarea>

              <div class="mt-2 d-flex gap-2">
                <input name="user_input" class="form-control" placeholder="Custom input (optional)" style="max-width:280px;">
                <button type="button" class="btn btn-warning" onclick="runCode()">Run</button>
                <button type="submit" class="btn btn-success" onclick="sync()">Submit & Next →</button>
              </div>
            </form>

            <div class="mt-0">
              <div class="p-2 bg-dark text-white-50 small fw-bold d-flex justify-content-between align-items-center rounded-bottom" style="font-size:0.7rem; border-top: 1px solid #444;">
                <span>TERMINAL OUTPUT</span>
                <span id="char_count">0 chars</span>
              </div>
              <pre id="live_out" class="mt-2 p-3 bg-dark text-white rounded-3 shadow-sm border-0" style="min-height:120px; font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace; font-size:.9rem; overflow-x:auto; border-left: 5px solid #6c757d; border-radius: 0 0 8px 8px;">{{ output }}</pre>
            </div>
          </div>
        </div>

      </div>
    </div>

    <script>
    window.onerror = function(msg, url, line) {
        console.error("Global Error: ", msg, url, line);
        const statusEl = document.getElementById('run_status');
        if (statusEl) {
            statusEl.innerText = 'ERR: ' + msg.split('\n')[0];
            statusEl.className = 'badge bg-danger';
            statusEl.title = msg;
        }
    };
    </script>
    <script src="https://cdn.jsdelivr.net/npm/ace-builds@1.32.3/src-min-noconflict/ace.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/ace-builds@1.32.3/src-min-noconflict/ext-language_tools.js"></script>
    <script>
    let editor;
    let debounceTimer;
    
    window.onload = function() {
        if (typeof ace !== 'undefined') {
            editor = ace.edit("editor");
        ace.require("ace/ext/language_tools");
        
        window.updateMode = function() {
            const lang = document.getElementById('lang_select').value;
            if (lang === 'python') {
                editor.session.setMode("ace/mode/python");
                editor.setOptions({
                    enableBasicAutocompletion: true,
                    enableLiveAutocompletion: true,
                    enableSnippets: true,
                    useSoftTabs: true,
                    tabSize: 4,
                    behavioursEnabled: true,
                    autoScrollEditorIntoView: true
                });
                document.getElementById('compiler_badge').innerText = 'PYTHON REAL-TIME ACTIVE';
            }
        };

        editor.setTheme("ace/theme/monokai");
        editor.setReadOnly(false);
        editor.container.style.lineHeight = "1.5";
        editor.setOptions({
            fontSize: "15px",
            showPrintMargin: false,
            displayIndentGuides: true,
            highlightActiveLine: true,
            wrap: true,
            scrollPastEnd: 0.5,
            dragEnabled: true
        });
        
        updateMode();
        editor.setValue({{ saved_code|tojson if saved_code else '"# Write your Python solution here\\n"'|safe }}, -1);
        editor.clearSelection();
        
        setTimeout(() => { editor.focus(); editor.resize(); }, 100);
        document.getElementById('editor').addEventListener('click', () => editor.focus());

        window.sync = function(){ document.getElementById('code_ta').value = editor.getValue(); };
        window.getEditorValue = function() { return editor.getValue(); };

        editor.on("change", () => {
            document.getElementById('char_count').innerText = editor.getValue().length + ' chars';
            if (document.getElementById('live_run_toggle').checked) {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(runCode, 1000);
            }
        });
    } else {
        // Fallback to plain textarea
        console.warn("Ace not loaded, falling back to textarea.");
        const ta = document.getElementById('code_ta');
        const container = document.getElementById('editor');
        ta.hidden = false;
        ta.classList.add('form-control', 'bg-dark', 'text-white');
        ta.style.height = '350px';
        ta.style.fontFamily = 'monospace';
        ta.style.fontSize = '15px';
        container.style.display = 'none';
        
        window.sync = function(){};
        window.getEditorValue = function() { return ta.value; };
        ta.addEventListener('input', () => {
            document.getElementById('char_count').innerText = ta.value.length + ' chars';
            if (document.getElementById('live_run_toggle').checked) {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(runCode, 1000);
            }
        });
        document.getElementById('compiler_badge').className = 'badge bg-warning text-dark';
        }
    };
    function runCode(){
      const statusEl = document.getElementById('run_status');
      const outEl = document.getElementById('live_out');
      const code = getEditorValue();
      if (!code.trim()) return;

      statusEl.innerText = 'RUNNING...';
      statusEl.className = 'badge bg-warning text-dark';
      outEl.style.borderLeftColor = '#ffc107';

      sync();
      fetch('/run_code', {
        method:'POST',
        headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:'code='+encodeURIComponent(code)+'&input='+encodeURIComponent(document.querySelector('[name=user_input]').value)
      }).then(r=>r.text()).then(d=>{ 
          outEl.innerText=d; 
          statusEl.innerText = 'DONE';
          statusEl.className = 'badge bg-success';
          outEl.style.borderLeftColor = '#198754';
          setTimeout(() => {
              if (statusEl.innerText === 'DONE') {
                  statusEl.innerText = 'IDLE';
                  statusEl.className = 'badge bg-secondary';
                  outEl.style.borderLeftColor = '#6c757d';
              }
          }, 2000);
      }).catch(e => {
          statusEl.innerText = 'ERROR';
          statusEl.className = 'badge bg-danger';
          outEl.style.borderLeftColor = '#dc3545';
          outEl.innerText = 'Execution Error: ' + e;
      });
    }

    // 30 min countdown
    let secs = 1800;
    const tel = document.getElementById('timer');
    setInterval(()=>{
      secs--;
      let m=Math.floor(secs/60), s=secs%60;
      tel.innerText = m+'m '+String(s).padStart(2,'0')+'s';
      if(secs<=0){ sync(); document.getElementById('cform').submit(); }
    },1000);
    </script>
    """, q=q, cidx=session['c_index']+1, ctot=len(session['c_list']),
    test_results=session.get('test_results', []),
    output=session.get('output', ''))


@app.route('/run_code', methods=['POST'])
def run_code_api():
    return run_code(request.form.get('code', ''), request.form.get('input', ''))


@app.route('/download_result')
def download_result():
    path = session.get('pdf_path')
    if path and os.path.exists(path):
        return send_file(path, as_attachment=True,
                         download_name=f"result_{session.get('username')}.pdf")
    return redirect('/dashboard')


# ── Result ────────────────────────────────────────────────────
@app.route('/result')
def result():
    if session.get('role') != 'user':
        return redirect('/login')

    mcq_score    = session.get('score', 0)
    coding_score = session.get('coding_score', 0)
    total_score  = mcq_score + coding_score
    mcq_total    = session.get('total', 0)

    with get_db() as conn:
        conn.execute(
            "UPDATE users SET quiz_status='completed', quiz_score=? WHERE username=?",
            (total_score, session['username'])
        )
        conn.commit()

    # Generate PDF
    pdf_path = generate_result_pdf(
        session.get('username'), mcq_score, mcq_total,
        coding_score, session.get('all_results', [])
    )
    session['pdf_path'] = pdf_path

    email = session.get('email')
    if email:
        body = f"""
        <div style="font-family:Arial;max-width:500px;margin:auto;padding:24px;
                    border:1px solid #ddd;border-radius:10px;">
          <h2 style="color:#28a745;">Exam Completed!</h2>
          <p>Hello <b>{session.get('username')}</b>,</p>
          <p>Your quiz results are attached as a <b>PDF</b>. Here's a quick summary:</p>
          <table style="width:100%;border-collapse:collapse;margin:12px 0;">
            <tr style="background:#1e2a3a;color:#fff;">
              <th style="padding:10px;text-align:left;">Section</th>
              <th style="padding:10px;text-align:left;">Score</th>
            </tr>
            <tr><td style="padding:8px;border:1px solid #ddd;">MCQ</td>
                <td style="padding:8px;border:1px solid #ddd;"><b>{mcq_score} / {mcq_total}</b></td></tr>
            <tr><td style="padding:8px;border:1px solid #ddd;">Coding</td>
                <td style="padding:8px;border:1px solid #ddd;"><b>{coding_score}</b></td></tr>
            <tr style="background:#d4edda;">
              <td style="padding:8px;border:1px solid #ddd;"><b>Total Score</b></td>
              <td style="padding:8px;border:1px solid #ddd;"><b>{total_score}</b></td>
            </tr>
          </table>
          <p style="color:#666;font-size:.85rem;">
            Please find your detailed result PDF attached to this email.
          </p>
        </div>"""
        send_email_async(email, "Quiz Platform — Your Result (PDF Attached)", body, pdf_path)
        notify_admin_new_login(session.get('username'), email, 'user — exam completed',
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return render_template_string(CSS + """
    <style>body{background:#f0f2f5;}</style>
    <div class="container mt-5" style="max-width:520px;">
      <div class="card p-4 text-center shadow">
        <div style="font-size:3rem;">🎉</div>
        <h3 class="mt-2">Exam Completed!</h3>
        <p class="text-muted">Well done, <b>{{ username }}</b>!</p>
        <hr>
        <div class="row g-3 mt-1">
          <div class="col-4">
            <div class="p-3 bg-light rounded">
              <h4 class="text-primary mb-0">{{ mcq_score }}</h4>
              <small class="text-muted">MCQ Score</small>
            </div>
          </div>
          <div class="col-4">
            <div class="p-3 bg-light rounded">
              <h4 class="text-success mb-0">{{ coding_score }}</h4>
              <small class="text-muted">Coding Score</small>
            </div>
          </div>
          <div class="col-4">
            <div class="p-3 rounded" style="background:#667eea;color:#fff;">
              <h4 class="mb-0">{{ total_score }}</h4>
              <small>Total Score</small>
            </div>
          </div>
        </div>
        <p class="text-muted mt-3" style="font-size:.85rem;">
          A result email with PDF has been sent to your inbox.
        </p>
        <a href="/download_result" class="btn btn-success mt-2 w-100">Download PDF Report</a>
        <a href="/dashboard" class="btn btn-outline-primary mt-2 w-100">Back to Dashboard</a>
      </div>
    </div>
    """, username=session.get('username'),
    mcq_score=mcq_score, coding_score=coding_score, total_score=total_score)


ADMIN_SIDEBAR = """
<style>
  .sidebar { background:#1e2a3a; min-height:100vh; padding:20px 0; width:220px; flex-shrink:0; }
  .sidebar a { display:block; color:#adb5bd; padding:10px 24px; text-decoration:none; font-size:.95rem; }
  .sidebar a:hover, .sidebar a.active { background:#2c3e50; color:#fff; border-left:3px solid #0d6efd; }
  .sidebar .brand { color:#fff; font-size:1.1rem; font-weight:700; padding:10px 24px 20px; border-bottom:1px solid #2c3e50; margin-bottom:10px; }
  .main { padding:28px; background:#f0f2f5; min-height:100vh; flex-grow:1; }
</style>
<div class="d-flex" style="min-height:100vh;">
  <div class="sidebar">
    <div class="brand">Quiz Admin</div>
    <a href="/admin">Dashboard</a>
    <a href="/admin/users">Manage Users</a>
    <a href="/admin/add_mcq" class="{{ 'active' if active=='mcq' else '' }}">Add MCQ</a>
    <a href="/admin/add_coding" class="{{ 'active' if active=='coding' else '' }}">Add Coding</a>
    <a href="/admin/upload" class="{{ 'active' if active=='upload' else '' }}">Upload Questions</a>
    <a href="/logout" style="color:#e74c3c;margin-top:20px;">Logout</a>
  </div>
  <div class="main">
"""

# ── Add MCQ ───────────────────────────────────────────────────
@app.route('/admin/add_mcq', methods=['GET', 'POST'])
def add_mcq():
    if session.get('role') != 'admin':
        return redirect('/login')

    msg = ""
    new_ids = []

    if request.method == 'POST':
        action = request.form.get('action', 'manual')

        if action == 'manual':
            with get_db() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT, a TEXT, b TEXT, c TEXT, d TEXT,
                    answer TEXT, published INTEGER DEFAULT 0)""")
                conn.execute(
                    "INSERT INTO questions(question,a,b,c,d,answer,published) VALUES(?,?,?,?,?,?,0)",
                    (request.form['q'], request.form['a'], request.form['b'],
                     request.form['c'], request.form['d'], request.form['ans'])
                )
                conn.commit()
            msg = "saved"

        elif action == 'upload_csv':
            f = request.files.get('csvfile')
            if f and f.filename:
                ext     = f.filename.rsplit('.', 1)[-1].lower()
                content = f.read().decode('utf-8', errors='ignore')
                imported = 0
                errors   = []
                try:
                    rows = json.loads(content) if ext == 'json' else list(csv.DictReader(io.StringIO(content)))
                    with get_db() as conn:
                        conn.execute("""CREATE TABLE IF NOT EXISTS questions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            question TEXT, a TEXT, b TEXT, c TEXT, d TEXT,
                            answer TEXT, published INTEGER DEFAULT 0)""")
                        for i, raw in enumerate(rows):
                            r = normalize_row(raw)
                            q   = find_col(r, 'question', 'q', 'ques')
                            oa  = find_col(r, 'a', 'option_a', 'option a', 'opt_a', 'opt1', 'option1', 'choice_a', 'choice1')
                            ob  = find_col(r, 'b', 'option_b', 'option b', 'opt_b', 'opt2', 'option2', 'choice_b', 'choice2')
                            oc  = find_col(r, 'c', 'option_c', 'option c', 'opt_c', 'opt3', 'option3', 'choice_c', 'choice3')
                            od  = find_col(r, 'd', 'option_d', 'option d', 'opt_d', 'opt4', 'option4', 'choice_d', 'choice4')
                            ans = find_col(r, 'answer', 'correct', 'correct_answer', 'ans', 'correct_option')
                            if not q:
                                errors.append(f"Row {i+1}: missing question"); continue
                            try:
                                cur = conn.execute(
                                    "INSERT INTO questions(question,a,b,c,d,answer,published) VALUES(?,?,?,?,?,?,0)",
                                    (q, oa, ob, oc, od, ans.lower())
                                )
                                new_ids.append(cur.lastrowid)
                                imported += 1
                            except Exception as e:
                                errors.append(f"Row {i+1}: {e}")
                        conn.commit()
                    msg = f"csv_ok:{imported}:{';'.join(errors)}"
                except Exception as e:
                    msg = f"csv_err:{e}"

        elif action == 'publish_sel':
            ids = request.form.getlist('pub_ids')
            with get_db() as conn:
                for qid in ids:
                    conn.execute("UPDATE questions SET published=1 WHERE id=?", (qid,))
                conn.commit()
            msg = f"published:{len(ids)}"

    conn = get_db()
    try:
        questions = conn.execute("SELECT * FROM questions ORDER BY id DESC").fetchall()
    except:
        questions = []
    conn.close()
    new_ids_set = set(new_ids)

    published_count   = sum(1 for q in questions if q['published'])
    unpublished_count = len(questions) - published_count

    return render_template_string(CSS + ADMIN_SIDEBAR + """
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h5 class="mb-0">MCQ Questions</h5>
      <div class="d-flex gap-2">
        <span class="badge bg-success fs-6 px-3">{{ published_count }} Published</span>
        <span class="badge bg-secondary fs-6 px-3">{{ unpublished_count }} Draft</span>
        <a href="/admin/publish_all/mcq" class="btn btn-success btn-sm">Publish All</a>
        <a href="/admin/unpublish_all/mcq" class="btn btn-outline-secondary btn-sm">Unpublish All</a>
      </div>
    </div>

    {% if msg == 'saved' %}
    <div class="alert alert-success alert-dismissible">Question saved! <button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
    {% elif msg and msg.startswith('csv_ok') %}
      {% set parts = msg.split(':') %}
      <div class="alert alert-success alert-dismissible">
        <b>{{ parts[1] }} questions imported from CSV!</b>
        {% if parts[2] %}<br><small>{{ parts[2] }}</small>{% endif %}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% elif msg and msg.startswith('csv_err') %}
      <div class="alert alert-danger">Upload error: {{ msg.split(':',1)[1] }}</div>
    {% elif msg and msg.startswith('published') %}
      <div class="alert alert-success alert-dismissible">{{ msg.split(':')[1] }} questions published! <button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
    {% endif %}

    <div class="row g-4">
      <!-- Left panel: manual + upload -->
      <div class="col-md-4">
        <!-- Manual entry -->
        <div class="card p-4 mb-3">
          <h6 class="mb-3">Add New MCQ</h6>
          <form method="post">
            <input type="hidden" name="action" value="manual">
            <textarea name="q" class="form-control mb-2" rows="2" placeholder="Question" required></textarea>
            <input name="a" class="form-control mb-2" placeholder="Option A" required>
            <input name="b" class="form-control mb-2" placeholder="Option B" required>
            <input name="c" class="form-control mb-2" placeholder="Option C" required>
            <input name="d" class="form-control mb-2" placeholder="Option D" required>
            <label class="form-label mt-1">Correct Answer</label>
            <select name="ans" class="form-select mb-3">
              <option value="a">A</option><option value="b">B</option>
              <option value="c">C</option><option value="d">D</option>
            </select>
            <button class="btn btn-primary w-100">Save Question</button>
          </form>
        </div>

        <!-- Inline CSV upload -->
        <div class="card p-4">
          <h6 class="mb-2">Upload CSV / JSON</h6>
          <form method="post" enctype="multipart/form-data">
            <input type="hidden" name="action" value="upload_csv">
            <div style="border:2px dashed #0d6efd;border-radius:8px;padding:16px;text-align:center;cursor:pointer;background:#f8f9ff;"
                 onclick="document.getElementById('mcq_csv').click()">
              <div style="font-size:1.5rem;">📄</div>
              <p class="mb-0 fw-semibold" style="font-size:.9rem;">Click to select CSV / JSON</p>
              <input id="mcq_csv" type="file" name="csvfile" accept=".csv,.json" hidden
                     onchange="document.getElementById('mcq_fn').innerText=this.files[0].name">
            </div>
            <p id="mcq_fn" class="text-muted text-center mt-1 mb-2" style="font-size:.8rem;">No file chosen</p>
            <button class="btn btn-outline-primary w-100">Import File</button>
          </form>
          <div class="mt-2 p-2 bg-light rounded" style="font-size:.75rem;">
            <b>Accepted columns:</b><br>
            <code>question, a/opt1, b/opt2, c/opt3, d/opt4, answer</code>
          </div>
        </div>
      </div>

      <!-- Right panel: questions table -->
      <div class="col-md-8">
        <div class="card p-3">
          <h6 class="mb-3">All MCQ Questions ({{ questions|length }})</h6>
          <div style="max-height:580px;overflow-y:auto;">
          <table class="table table-sm table-hover align-middle">
            <thead class="table-dark sticky-top">
              <tr><th>#</th><th>Question</th><th>Ans</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody>
            {% for q in questions %}
            <tr class="{{ 'table-warning border-start border-warning border-3' if q['id'] in new_ids_set else ('table-success' if q['published'] else '') }}">
              <td>{{ q['id'] }}</td>
              <td style="max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{{ q['question'] }}">
                {% if q['id'] in new_ids_set %}<span class="badge bg-warning text-dark me-1">New</span>{% endif %}
                {{ q['question'] }}
              </td>
              <td><span class="badge bg-primary">{{ q['answer']|upper }}</span></td>
              <td>
                {% if q['published'] %}<span class="badge bg-success">Published</span>
                {% else %}<span class="badge bg-secondary">Draft</span>{% endif %}
              </td>
              <td>
                <div class="d-flex gap-1">
                  {% if q['published'] %}
                    <a href="/admin/unpublish/mcq/{{ q['id'] }}" class="btn btn-sm btn-warning">Unpublish</a>
                  {% else %}
                    <a href="/admin/publish/mcq/{{ q['id'] }}" class="btn btn-sm btn-success">Publish</a>
                  {% endif %}
                  <a href="/admin/delete_mcq/{{ q['id'] }}" class="btn btn-sm btn-outline-danger" onclick="return confirm('Delete?')">Delete</a>
                </div>
              </td>
            </tr>
            {% else %}
            <tr><td colspan="5" class="text-center text-muted py-3">No questions yet — add one or upload a file.</td></tr>
            {% endfor %}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
    """, msg=msg, questions=questions, active='mcq',
    published_count=published_count, unpublished_count=unpublished_count,
    new_ids_set=new_ids_set)


# ── Add Coding ────────────────────────────────────────────────
@app.route('/admin/add_coding', methods=['GET', 'POST'])
def add_coding():
    if session.get('role') != 'admin':
        return redirect('/login')

    msg     = ""
    new_ids = []

    if request.method == 'POST':
        action = request.form.get('action', 'manual')

        if action == 'manual':
            with get_db() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS coding_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT, sample_input TEXT,
                    sample_output TEXT, published INTEGER DEFAULT 0)""")
                conn.execute(
                    "INSERT INTO coding_questions(question,sample_input,sample_output,published) VALUES(?,?,?,0)",
                    (request.form['q'], request.form['si'], request.form['so'])
                )
                conn.commit()
            msg = "saved"

        elif action == 'upload_csv':
            f = request.files.get('csvfile')
            if f and f.filename:
                ext     = f.filename.rsplit('.', 1)[-1].lower()
                content = f.read().decode('utf-8', errors='ignore')
                imported = 0
                errors   = []
                try:
                    rows = json.loads(content) if ext == 'json' else list(csv.DictReader(io.StringIO(content)))
                    with get_db() as conn:
                        conn.execute("""CREATE TABLE IF NOT EXISTS coding_questions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            question TEXT, sample_input TEXT,
                            sample_output TEXT, published INTEGER DEFAULT 0)""")
                        for i, raw in enumerate(rows):
                            r  = normalize_row(raw)
                            q  = find_col(r, 'question', 'q', 'ques')
                            si = find_col(r, 'sample_input', 'input', 'sample input', 'sampleinput')
                            so = find_col(r, 'sample_output', 'output', 'sample output', 'sampleoutput')
                            if not q:
                                errors.append(f"Row {i+1}: missing question"); continue
                            try:
                                cur = conn.execute(
                                    "INSERT INTO coding_questions(question,sample_input,sample_output,published) VALUES(?,?,?,0)",
                                    (q, si, so)
                                )
                                new_ids.append(cur.lastrowid)
                                imported += 1
                            except Exception as e:
                                errors.append(f"Row {i+1}: {e}")
                        conn.commit()
                    msg = f"csv_ok:{imported}:{';'.join(errors)}"
                except Exception as e:
                    msg = f"csv_err:{e}"

    conn = get_db()
    try:
        questions = conn.execute("SELECT * FROM coding_questions ORDER BY id DESC").fetchall()
    except:
        questions = []
    conn.close()

    published_count   = sum(1 for q in questions if q['published'])
    unpublished_count = len(questions) - published_count
    new_ids_set = set(new_ids)

    return render_template_string(CSS + ADMIN_SIDEBAR + """
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h5 class="mb-0">Coding Questions</h5>
      <div class="d-flex gap-2">
        <span class="badge bg-success fs-6 px-3">{{ published_count }} Published</span>
        <span class="badge bg-secondary fs-6 px-3">{{ unpublished_count }} Draft</span>
        <a href="/admin/publish_all/coding" class="btn btn-success btn-sm">Publish All</a>
        <a href="/admin/unpublish_all/coding" class="btn btn-outline-secondary btn-sm">Unpublish All</a>
      </div>
    </div>

    {% if msg == 'saved' %}
    <div class="alert alert-success alert-dismissible">Question saved! <button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
    {% elif msg and msg.startswith('csv_ok') %}
      {% set parts = msg.split(':') %}
      <div class="alert alert-success alert-dismissible">
        <b>{{ parts[1] }} questions imported from CSV!</b>
        {% if parts[2] %}<br><small>{{ parts[2] }}</small>{% endif %}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% elif msg and msg.startswith('csv_err') %}
      <div class="alert alert-danger">Upload error: {{ msg.split(':',1)[1] }}</div>
    {% endif %}

    <div class="row g-4">
      <!-- Left panel -->
      <div class="col-md-4">
        <div class="card p-4 mb-3">
          <h6 class="mb-3">Add New Coding Question</h6>
          <form method="post">
            <input type="hidden" name="action" value="manual">
            <textarea name="q"  class="form-control mb-2" rows="4" placeholder="Question description" required></textarea>
            <input   name="si" class="form-control mb-2" placeholder="Sample Input">
            <input   name="so" class="form-control mb-3" placeholder="Sample Output">
            <button class="btn btn-success w-100">Save Question</button>
          </form>
        </div>

        <!-- Inline CSV upload -->
        <div class="card p-4">
          <h6 class="mb-2">Upload CSV / JSON</h6>
          <form method="post" enctype="multipart/form-data">
            <input type="hidden" name="action" value="upload_csv">
            <div style="border:2px dashed #198754;border-radius:8px;padding:16px;text-align:center;cursor:pointer;background:#f8fff9;"
                 onclick="document.getElementById('cod_csv').click()">
              <div style="font-size:1.5rem;">💻</div>
              <p class="mb-0 fw-semibold" style="font-size:.9rem;">Click to select CSV / JSON</p>
              <input id="cod_csv" type="file" name="csvfile" accept=".csv,.json" hidden
                     onchange="document.getElementById('cod_fn').innerText=this.files[0].name">
            </div>
            <p id="cod_fn" class="text-muted text-center mt-1 mb-2" style="font-size:.8rem;">No file chosen</p>
            <button class="btn btn-outline-success w-100">Import File</button>
          </form>
          <div class="mt-2 p-2 bg-light rounded" style="font-size:.75rem;">
            <b>Accepted columns:</b><br>
            <code>question, sample_input, sample_output</code>
          </div>
        </div>
      </div>

      <!-- Right panel -->
      <div class="col-md-8">
        <div class="card p-3">
          <h6 class="mb-3">All Coding Questions ({{ questions|length }})</h6>
          <div style="max-height:580px;overflow-y:auto;">
          <table class="table table-sm table-hover align-middle">
            <thead class="table-dark sticky-top">
              <tr><th>#</th><th>Question</th><th>Input</th><th>Output</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody>
            {% for q in questions %}
            <tr class="{{ 'table-warning' if q['id'] in new_ids_set else ('table-success' if q['published'] else '') }}">
              <td>{{ q['id'] }}</td>
              <td style="max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{{ q['question'] }}">
                {% if q['id'] in new_ids_set %}<span class="badge bg-warning text-dark me-1">New</span>{% endif %}
                {{ q['question'] }}
              </td>
              <td>{{ q['sample_input'] }}</td>
              <td>{{ q['sample_output'] }}</td>
              <td>
                {% if q['published'] %}<span class="badge bg-success">Published</span>
                {% else %}<span class="badge bg-secondary">Draft</span>{% endif %}
              </td>
              <td>
                <div class="d-flex gap-1">
                  {% if q['published'] %}
                    <a href="/admin/unpublish/coding/{{ q['id'] }}" class="btn btn-sm btn-warning">Unpublish</a>
                  {% else %}
                    <a href="/admin/publish/coding/{{ q['id'] }}" class="btn btn-sm btn-success">Publish</a>
                  {% endif %}
                  <a href="/admin/delete_coding/{{ q['id'] }}" class="btn btn-sm btn-outline-danger" onclick="return confirm('Delete?')">Delete</a>
                </div>
              </td>
            </tr>
            {% else %}
            <tr><td colspan="6" class="text-center text-muted py-3">No questions yet — add one or upload a file.</td></tr>
            {% endfor %}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
    """, msg=msg, questions=questions, active='coding',
    published_count=published_count, unpublished_count=unpublished_count,
    new_ids_set=new_ids_set)


# ── Upload Questions ──────────────────────────────────────────
def normalize_row(row):
    """Normalize all keys and values — skip None/empty keys."""
    result = {}
    for k, v in row.items():
        if k is None:
            continue
        clean_key = str(k).strip().lower().replace(' ', '_')
        if not clean_key:
            continue
        result[clean_key] = str(v).strip() if v is not None else ''
    return result

def find_col(row, *names):
    """Find first matching key from candidates."""
    for n in names:
        v = row.get(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ''

@app.route('/admin/upload', methods=['GET', 'POST'])
def upload_questions():
    if session.get('role') != 'admin':
        return redirect('/login')

    result       = None
    new_ids      = []   # IDs of just-imported questions
    import_qtype = None

    if request.method == 'POST':
        action = request.form.get('action', 'import')

        # ── Publish/Unpublish imported questions ──
        if action in ('publish_imported', 'unpublish_imported'):
            ids   = request.form.getlist('qids')
            qtype = request.form.get('qtype_imported', 'mcq')
            table = 'questions' if qtype == 'mcq' else 'coding_questions'
            val   = 1 if action == 'publish_imported' else 0
            with get_db() as conn:
                for qid in ids:
                    conn.execute(f"UPDATE {table} SET published=? WHERE id=?", (val, qid))
                conn.commit()
            label = 'Published' if val else 'Unpublished'
            result = {'status': 'success', 'imported': len(ids), 'errors': [],
                      'qtype': qtype, 'msg': f'{label} {len(ids)} questions.', 'action': label}
        else:
            # ── File import ──
            qtype = request.form.get('qtype')
            f     = request.files.get('file')

            if not f or not f.filename:
                result = {'status': 'error', 'msg': 'No file selected.'}
            else:
                ext     = f.filename.rsplit('.', 1)[-1].lower()
                content = f.read().decode('utf-8', errors='ignore')
                imported = 0
                errors   = []

                try:
                    rows = []
                    if ext == 'json':
                        data = json.loads(content)
                        rows = data if isinstance(data, list) else [data]
                    elif ext == 'csv':
                        rows = list(csv.DictReader(io.StringIO(content)))
                    else:
                        result = {'status': 'error', 'msg': 'Only CSV or JSON files supported.'}

                    if rows and not result:
                        with get_db() as conn:
                            if qtype == 'mcq':
                                conn.execute("""CREATE TABLE IF NOT EXISTS questions (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    question TEXT, a TEXT, b TEXT, c TEXT, d TEXT,
                                    answer TEXT, published INTEGER DEFAULT 0)""")
                                for i, raw in enumerate(rows):
                                    r = normalize_row(raw)
                                    try:
                                        q  = find_col(r, 'question', 'q', 'ques')
                                        oa = find_col(r, 'a', 'option_a', 'option a', 'opt_a', 'opt1', 'option1', 'choice_a', 'choice1')
                                        ob = find_col(r, 'b', 'option_b', 'option b', 'opt_b', 'opt2', 'option2', 'choice_b', 'choice2')
                                        oc = find_col(r, 'c', 'option_c', 'option c', 'opt_c', 'opt3', 'option3', 'choice_c', 'choice3')
                                        od = find_col(r, 'd', 'option_d', 'option d', 'opt_d', 'opt4', 'option4', 'choice_d', 'choice4')
                                        ans = find_col(r, 'answer', 'correct', 'correct_answer', 'ans', 'correct_option')
                                        if not q:
                                            errors.append(f"Row {i+1}: missing question text"); continue
                                        cur = conn.execute(
                                            "INSERT INTO questions(question,a,b,c,d,answer,published) VALUES(?,?,?,?,?,?,0)",
                                            (q, oa, ob, oc, od, ans.lower())
                                        )
                                        new_ids.append(cur.lastrowid)
                                        imported += 1
                                    except Exception as e:
                                        errors.append(f"Row {i+1}: {e}")
                            else:
                                conn.execute("""CREATE TABLE IF NOT EXISTS coding_questions (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    question TEXT, sample_input TEXT,
                                    sample_output TEXT, published INTEGER DEFAULT 0)""")
                                for i, raw in enumerate(rows):
                                    r = normalize_row(raw)
                                    try:
                                        q  = find_col(r, 'question', 'q', 'ques')
                                        si = find_col(r, 'sample_input', 'input', 'sample input')
                                        so = find_col(r, 'sample_output', 'output', 'sample output')
                                        if not q:
                                            errors.append(f"Row {i+1}: missing question text"); continue
                                        cur = conn.execute(
                                            "INSERT INTO coding_questions(question,sample_input,sample_output,published) VALUES(?,?,?,0)",
                                            (q, si, so)
                                        )
                                        new_ids.append(cur.lastrowid)
                                        imported += 1
                                    except Exception as e:
                                        errors.append(f"Row {i+1}: {e}")
                            conn.commit()

                        import_qtype = qtype
                        result = {'status': 'success', 'imported': imported,
                                  'errors': errors, 'qtype': qtype, 'action': 'import'}

                except Exception as e:
                    result = {'status': 'error', 'msg': str(e)}

    # Load just-imported questions to show publish panel
    imported_questions = []
    if new_ids and import_qtype:
        conn = get_db()
        table = 'questions' if import_qtype == 'mcq' else 'coding_questions'
        placeholders = ','.join('?' * len(new_ids))
        imported_questions = conn.execute(
            f"SELECT * FROM {table} WHERE id IN ({placeholders})", new_ids
        ).fetchall()
        conn.close()

    return render_template_string(CSS + ADMIN_SIDEBAR + """
    <h5 class="mb-4">Upload Questions</h5>

    {% if result %}
      {% if result.status == 'success' %}
      <div class="alert alert-success alert-dismissible fade show">
        <b>{{ result.imported }} {{ result.qtype|upper }} question(s)
        {% if result.action == 'import' %}imported{% else %}{{ result.action|lower }}ed{% endif %}
        successfully!</b>
        {% if result.errors %}
        <ul class="mb-0 mt-1">{% for e in result.errors %}<li>{{ e }}</li>{% endfor %}</ul>
        {% endif %}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
      {% else %}
      <div class="alert alert-danger"><b>Error:</b> {{ result.msg }}</div>
      {% endif %}
    {% endif %}

    <!-- After-import: Publish panel -->
    {% if imported_questions %}
    <div class="card border-success mb-4 p-3">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h6 class="mb-0 text-success">{{ imported_questions|length }} questions just imported — review &amp; publish</h6>
        <div class="d-flex gap-2">
          <form method="post">
            <input type="hidden" name="action" value="publish_imported">
            <input type="hidden" name="qtype_imported" value="{{ import_qtype }}">
            {% for q in imported_questions %}
            <input type="hidden" name="qids" value="{{ q['id'] }}">
            {% endfor %}
            <button class="btn btn-success btn-sm">Publish All {{ imported_questions|length }}</button>
          </form>
          <form method="post">
            <input type="hidden" name="action" value="unpublish_imported">
            <input type="hidden" name="qtype_imported" value="{{ import_qtype }}">
            {% for q in imported_questions %}
            <input type="hidden" name="qids" value="{{ q['id'] }}">
            {% endfor %}
            <button class="btn btn-outline-secondary btn-sm">Keep as Draft</button>
          </form>
        </div>
      </div>
      <table class="table table-sm table-hover align-middle mb-0">
        <thead class="table-dark">
          <tr>
            <th>#</th><th>Question</th>
            {% if import_qtype == 'mcq' %}<th>A</th><th>B</th><th>C</th><th>D</th><th>Ans</th>{% else %}<th>Input</th><th>Output</th>{% endif %}
            <th>Status</th><th>Action</th>
          </tr>
        </thead>
        <tbody>
        {% for q in imported_questions %}
        <tr class="{{ 'table-success' if q['published'] else '' }}">
          <td>{{ q['id'] }}</td>
          <td style="max-width:250px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ q['question'] }}</td>
          {% if import_qtype == 'mcq' %}
            <td>{{ q['a'] }}</td><td>{{ q['b'] }}</td><td>{{ q['c'] }}</td><td>{{ q['d'] }}</td>
            <td><span class="badge bg-primary">{{ q['answer']|upper }}</span></td>
          {% else %}
            <td>{{ q['sample_input'] }}</td><td>{{ q['sample_output'] }}</td>
          {% endif %}
          <td>
            {% if q['published'] %}<span class="badge bg-success">Published</span>
            {% else %}<span class="badge bg-secondary">Draft</span>{% endif %}
          </td>
          <td>
            {% if q['published'] %}
              <a href="/admin/unpublish/{{ import_qtype }}/{{ q['id'] }}" class="btn btn-sm btn-warning">Unpublish</a>
            {% else %}
              <a href="/admin/publish/{{ import_qtype }}/{{ q['id'] }}" class="btn btn-sm btn-success">Publish</a>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    {% endif %}

    <div class="row g-4">

      <!-- MCQ Upload -->
      <div class="col-md-6">
        <div class="card p-4 h-100">
          <h6 class="mb-1">Upload MCQ Questions</h6>
          <p class="text-muted mb-3" style="font-size:.85rem;">CSV or JSON — any column name format accepted</p>
          <form method="post" enctype="multipart/form-data">
            <input type="hidden" name="qtype" value="mcq">
            <div style="border:2px dashed #0d6efd;background:#f8f9ff;border-radius:8px;padding:24px;text-align:center;cursor:pointer;"
                 onclick="document.getElementById('mcq_file').click()">
              <div style="font-size:2rem;">📄</div>
              <p class="mb-1 fw-semibold">Click to select file</p>
              <p class="text-muted mb-0" style="font-size:.8rem;">CSV or JSON only</p>
              <input id="mcq_file" type="file" name="file" accept=".csv,.json" hidden
                     onchange="document.getElementById('mcq_name').innerText=this.files[0].name">
            </div>
            <p id="mcq_name" class="text-muted text-center my-2" style="font-size:.85rem;">No file chosen</p>
            <button class="btn btn-primary w-100">Import MCQ</button>
          </form>
          <div class="mt-3 p-3 bg-light rounded">
            <b style="font-size:.82rem;">CSV format (any of these column names work):</b>
            <code style="font-size:.75rem;display:block;margin-top:6px;white-space:pre-wrap;">question, a, b, c, d, answer
"What is 2+2?","1","2","3","4","d"</code>
          </div>
        </div>
      </div>

      <!-- Coding Upload -->
      <div class="col-md-6">
        <div class="card p-4 h-100">
          <h6 class="mb-1">Upload Coding Questions</h6>
          <p class="text-muted mb-3" style="font-size:.85rem;">CSV or JSON — any column name format accepted</p>
          <form method="post" enctype="multipart/form-data">
            <input type="hidden" name="qtype" value="coding">
            <div style="border:2px dashed #198754;background:#f8fff9;border-radius:8px;padding:24px;text-align:center;cursor:pointer;"
                 onclick="document.getElementById('cod_file').click()">
              <div style="font-size:2rem;">💻</div>
              <p class="mb-1 fw-semibold">Click to select file</p>
              <p class="text-muted mb-0" style="font-size:.8rem;">CSV or JSON only</p>
              <input id="cod_file" type="file" name="file" accept=".csv,.json" hidden
                     onchange="document.getElementById('cod_name').innerText=this.files[0].name">
            </div>
            <p id="cod_name" class="text-muted text-center my-2" style="font-size:.85rem;">No file chosen</p>
            <button class="btn btn-success w-100">Import Coding</button>
          </form>
          <div class="mt-3 p-3 bg-light rounded">
            <b style="font-size:.82rem;">CSV format:</b>
            <code style="font-size:.75rem;display:block;margin-top:6px;white-space:pre-wrap;">question, sample_input, sample_output
"Reverse a string","hello","olleh"</code>
          </div>
        </div>
      </div>

    </div>

    <!-- Download sample files -->
    <div class="card p-3 mt-4">
      <h6 class="mb-3">Download Sample Files</h6>
      <div class="d-flex gap-3 flex-wrap">
        <a href="/admin/sample/mcq_csv" class="btn btn-outline-primary btn-sm">MCQ Sample CSV</a>
        <a href="/admin/sample/mcq_json" class="btn btn-outline-primary btn-sm">MCQ Sample JSON</a>
        <a href="/admin/sample/coding_csv" class="btn btn-outline-success btn-sm">Coding Sample CSV</a>
        <a href="/admin/sample/coding_json" class="btn btn-outline-success btn-sm">Coding Sample JSON</a>
      </div>
    </div>

  </div>
</div>
    """, result=result, active='upload',
    imported_questions=imported_questions, import_qtype=import_qtype)


# ── Sample file downloads ─────────────────────────────────────
@app.route('/admin/sample/<kind>')
def sample_file(kind):
    if session.get('role') != 'admin':
        return redirect('/login')
    from flask import Response
    samples = {
        'mcq_csv': (
            "question,a,b,c,d,answer\n"
            "\"What is the capital of France?\",\"Berlin\",\"Madrid\",\"Paris\",\"Rome\",\"c\"\n"
            "\"Which language is used in Flask?\",\"Java\",\"Python\",\"PHP\",\"Ruby\",\"b\"\n",
            'mcq_questions.csv', 'text/csv'
        ),
        'mcq_json': (
            json.dumps([
                {"question":"What is 2+2?","a":"1","b":"2","c":"3","d":"4","answer":"d"},
                {"question":"Which is NOT a Python data type?","a":"int","b":"float","c":"char","d":"str","answer":"c"}
            ], indent=2),
            'mcq_questions.json', 'application/json'
        ),
        'coding_csv': (
            "question,sample_input,sample_output\n"
            "\"Write a program to reverse a string\",\"hello\",\"olleh\"\n"
            "\"Find the sum of a list of numbers\",\"1 2 3\",\"6\"\n",
            'coding_questions.csv', 'text/csv'
        ),
        'coding_json': (
            json.dumps([
                {"question":"Print the largest number in a list","sample_input":"1 2 3","sample_output":"3"},
                {"question":"Count vowels in a string","sample_input":"hello","sample_output":"2"}
            ], indent=2),
            'coding_questions.json', 'application/json'
        ),
    }
    if kind not in samples:
        return "Not found", 404
    content, filename, mimetype = samples[kind]
    return Response(content, mimetype=mimetype,
                    headers={"Content-Disposition": f"attachment;filename={filename}"})


# ── Publish / Unpublish ───────────────────────────────────────
@app.route('/admin/publish/mcq/<int:qid>')
def publish_mcq(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE questions SET published=1 WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_mcq')

@app.route('/admin/unpublish/mcq/<int:qid>')
def unpublish_mcq(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE questions SET published=0 WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_mcq')

@app.route('/admin/publish/coding/<int:qid>')
def publish_coding(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE coding_questions SET published=1 WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_coding')

@app.route('/admin/unpublish/coding/<int:qid>')
def unpublish_coding(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE coding_questions SET published=0 WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_coding')

@app.route('/admin/publish_all/<qtype>')
def publish_all(qtype):
    if session.get('role') != 'admin': return redirect('/login')
    table = 'questions' if qtype == 'mcq' else 'coding_questions'
    with get_db() as conn:
        conn.execute(f"UPDATE {table} SET published=1")
        conn.commit()
    return redirect(f"/admin/add_{'mcq' if qtype=='mcq' else 'coding'}")

@app.route('/admin/unpublish_all/<qtype>')
def unpublish_all(qtype):
    if session.get('role') != 'admin': return redirect('/login')
    table = 'questions' if qtype == 'mcq' else 'coding_questions'
    with get_db() as conn:
        conn.execute(f"UPDATE {table} SET published=0")
        conn.commit()
    return redirect(f"/admin/add_{'mcq' if qtype=='mcq' else 'coding'}")


# ── Delete questions ──────────────────────────────────────────
@app.route('/admin/delete_mcq/<int:qid>')
def delete_mcq(qid):
    if session.get('role') != 'admin':
        return redirect('/login')
    with get_db() as conn:
        conn.execute("DELETE FROM questions WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_mcq')


@app.route('/admin/delete_coding/<int:qid>')
def delete_coding(qid):
    if session.get('role') != 'admin':
        return redirect('/login')
    with get_db() as conn:
        conn.execute("DELETE FROM coding_questions WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_coding')


if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
