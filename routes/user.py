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
    
    # Fetch dynamic settings
    settings = {row['key']: row['value'] for row in conn.execute("SELECT * FROM settings").fetchall()}
    pass_per = float(settings.get('pass_percentage', 60))
    wait_days = int(settings.get('retake_wait_days', 7))
    expiry_h = int(settings.get('quiz_expiry_hours', 48))

    # Fetch user attempts for per-quiz lockout
    user_attempts = conn.execute("""
        SELECT quiz_id, percentage, attempt_date 
        FROM user_quiz_attempts 
        WHERE username=? 
        ORDER BY attempt_date DESC
    """, (session['username'],)).fetchall()
    
    attempts_by_quiz = {}
    for att in user_attempts:
        if att['quiz_id'] not in attempts_by_quiz:
            attempts_by_quiz[att['quiz_id']] = att

    # Fetch active quizzes
    active_quizzes_raw = conn.execute("""
        SELECT q.*, c.name as cat_name, c.type as cat_type 
        FROM quizzes q 
        JOIN categories c ON q.category_id = c.id 
        WHERE q.is_active = 1
    """).fetchall()
    
    active_quizzes = []
    for q in active_quizzes_raw:
        q_dict = dict(q)
        
        # Per-quiz lockout logic
        q_dict['is_locked'] = False
        q_dict['lock_message'] = ""
        q_dict['is_passed'] = False
        
        att = attempts_by_quiz.get(q_dict['id'])
        if att:
            if att['percentage'] >= pass_per:
                q_dict['is_passed'] = True
            else:
                last_date = datetime.strptime(att['attempt_date'], "%Y-%m-%d %H:%M:%S")
                diff = datetime.now() - last_date
                if diff.total_seconds() < wait_days * 24 * 3600:
                    q_dict['is_locked'] = True
                    rem_seconds = int(wait_days * 24 * 3600 - diff.total_seconds())
                    d = rem_seconds // (24 * 3600)
                    h = (rem_seconds % (24 * 3600)) // 3600
                    m = (rem_seconds % 3600) // 60
                    parts = []
                    if d > 0: parts.append(f"{d}d")
                    if h > 0: parts.append(f"{h}h")
                    if m > 0: parts.append(f"{m}m")
                    q_dict['lock_message'] = f"Try again after {wait_days} days"
        
        active_quizzes.append(q_dict)
    
    mcq_count = conn.execute("SELECT COUNT(*) FROM questions WHERE published=1").fetchone()[0]
    coding_count = conn.execute("SELECT COUNT(*) FROM coding_questions WHERE published=1").fetchone()[0]
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
      .waiting-box { background:#fff3cd; border:1px solid #ffeeba; color:#856404; padding:15px; border-radius:10px; margin-bottom:20px; text-align:center; }
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
            <p class="mb-0" style="opacity:.85;">Ready for your next assessment?</p>
          </div>
          <div class="text-end">
            <span class="badge bg-light text-dark fs-6 px-3 py-2">
              Status: <b>{{ status_label }}</b>
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

      <h5 class="mb-3">Available Quizzes</h5>
      <div class="row g-4 mb-4">
        {% for quiz in active_quizzes %}
        <div class="col-md-6">
          <div class="card exam-card h-100 shadow-sm">
            <div style="background:linear-gradient(135deg, {{ '#0061ff,#60efff' if quiz.cat_type == 'mcq' else ('#11998e,#38ef7d' if quiz.cat_type == 'coding' else '#667eea,#764ba2') }});padding:24px;color:#fff;">
              <h5 class="mb-1">{{ quiz.name }}</h5>
              <p class="mb-0 small" style="opacity:.85;">{{ quiz.cat_name }} | {{ quiz.time_limit }} mins | +{{ quiz.positive_marks }}/-{{ quiz.negative_marks }} marks</p>
              {% if quiz.cat_type == 'mixed' %}
                <span class="badge bg-light text-dark mt-2">🔀 MCQ + Coding</span>
              {% endif %}
            </div>
            <div class="p-3 d-flex justify-content-between align-items-center">
              <span class="text-muted small">Pass Criteria: {{ pass_per }}%</span>
              {% if quiz.is_passed %}
                <button class="btn btn-success btn-sm disabled">Passed &#10004;</button>
              {% elif quiz.is_locked %}
                <button class="btn btn-secondary btn-sm disabled">{{ quiz.lock_message }}</button>
              {% else %}
                <a href="/instructions?quiz_id={{ quiz.id }}" class="btn btn-{{ 'primary' if quiz.cat_type == 'mcq' else ('success' if quiz.cat_type == 'coding' else 'info') }} btn-sm">Start Quiz</a>
              {% endif %}
            </div>
          </div>
        </div>
        {% else %}
        <div class="col-12 text-center py-5">
           <p class="text-muted">No quizzes available at the moment.</p>
        </div>
        {% endfor %}
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
    quiz_score=quiz_score,
    mcq_count=mcq_count,
    coding_count=coding_count,
    login_count=login_count,
    last_login=last_login,
    status_color=status_color[quiz_status],
    status_label=status_label[quiz_status],
    pass_per=int(pass_per),
    active_quizzes=active_quizzes)
