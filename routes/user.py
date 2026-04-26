from datetime import datetime
from flask import Blueprint, redirect, session, render_template_string
from database import get_db

user_bp = Blueprint('user', __name__)

CSS = '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">'


@user_bp.route('/dashboard')
def dashboard():
    if not session.get('username') or session.get('role') != 'user':
        return redirect('/login')

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (session['username'],)).fetchone()
    try:
        mcq_count = conn.execute("SELECT COUNT(*) FROM questions WHERE published=1").fetchone()[0]
    except Exception:
        mcq_count = 0
    try:
        coding_count = conn.execute("SELECT COUNT(*) FROM coding_questions WHERE published=1").fetchone()[0]
    except Exception:
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

      <div class="row g-3 mb-4">
        <div class="col-md-3">
          <div class="stat-card" style="background:linear-gradient(135deg,#11998e,#38ef7d);">
            <h2>{{ quiz_score }}</h2><p>Your Score</p>
          </div>
        </div>
        <div class="col-md-3">
          <div class="stat-card" style="background:linear-gradient(135deg,#2193b0,#6dd5ed);">
            <h2>{{ mcq_count }}</h2><p>MCQ Questions</p>
          </div>
        </div>
        <div class="col-md-3">
          <div class="stat-card" style="background:linear-gradient(135deg,#f7971e,#ffd200);">
            <h2>{{ coding_count }}</h2><p>Coding Questions</p>
          </div>
        </div>
        <div class="col-md-3">
          <div class="stat-card" style="background:linear-gradient(135deg,#e96c75,#c0392b);">
            <h2>{{ login_count }}</h2><p>Times Logged In</p>
          </div>
        </div>
      </div>

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
    status_label=status_label[quiz_status])
