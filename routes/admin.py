import csv
import io
import json
from flask import Blueprint, request, redirect, session, render_template_string, Response
from database import get_db
from services.email_service import send_approval_email
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

CSS = '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">'

SIDEBAR = """
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


def normalize_row(row):
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
    for n in names:
        v = row.get(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ''


@admin_bp.route('/admin')
def admin():
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db()
    users       = conn.execute("SELECT * FROM users WHERE role='user'").fetchall()
    total       = len(users)
    approved    = sum(1 for u in users if u['approved'])
    pending     = total - approved
    completed   = sum(1 for u in users if u['quiz_status'] == 'completed')
    inprogress  = sum(1 for u in users if u['quiz_status'] == 'in_progress')
    not_started = sum(1 for u in users if u['quiz_status'] == 'not_started' and u['approved'])
    total_logins = conn.execute("SELECT SUM(login_count) FROM users WHERE role='user'").fetchone()[0] or 0

    try:
        mcq_total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        mcq_count = conn.execute("SELECT COUNT(*) FROM questions WHERE published=1").fetchone()[0]
    except Exception:
        mcq_total = mcq_count = 0
    try:
        coding_total = conn.execute("SELECT COUNT(*) FROM coding_questions").fetchone()[0]
        coding_count = conn.execute("SELECT COUNT(*) FROM coding_questions WHERE published=1").fetchone()[0]
    except Exception:
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
      <div class="sidebar" style="width:220px;flex-shrink:0;">
        <div class="brand">Quiz Admin</div>
        <a href="/admin" class="active">Dashboard</a>
        <a href="/admin/users">Manage Users</a>
        <a href="/admin/add_mcq">Add MCQ</a>
        <a href="/admin/add_coding">Add Coding</a>
        <a href="/admin/upload">Upload Questions</a>
        <a href="/logout" style="color:#e74c3c;margin-top:20px;">Logout</a>
      </div>
      <div class="main flex-grow-1">
        <div class="d-flex justify-content-between align-items-center mb-4">
          <div>
            <h4 class="mb-0">Welcome back, <b>{{ username }}</b></h4>
            <small class="text-muted">{{ now }}</small>
          </div>
        </div>

        <div class="row g-3 mb-4">
          <div class="col-md-3">
            <div class="stat-card" style="background:linear-gradient(135deg,#667eea,#764ba2);">
              <h2>{{ total }}</h2><p>Total Registered</p>
            </div>
          </div>
          <div class="col-md-3">
            <div class="stat-card" style="background:linear-gradient(135deg,#11998e,#38ef7d);">
              <h2>{{ approved }}</h2><p>Approved Users</p>
            </div>
          </div>
          <div class="col-md-3">
            <div class="stat-card" style="background:linear-gradient(135deg,#f7971e,#ffd200);">
              <h2>{{ pending }}</h2><p>Pending Approval</p>
            </div>
          </div>
          <div class="col-md-3">
            <div class="stat-card" style="background:linear-gradient(135deg,#e96c75,#c0392b);">
              <h2>{{ total_logins }}</h2><p>Total Logins</p>
            </div>
          </div>
        </div>

        <div class="row g-3 mb-4">
          <div class="col-md-4">
            <div class="stat-card" style="background:linear-gradient(135deg,#2193b0,#6dd5ed);">
              <h2>{{ completed }}</h2><p>Quiz Completed</p>
            </div>
          </div>
          <div class="col-md-4">
            <div class="stat-card" style="background:linear-gradient(135deg,#ee9ca7,#ffdde1);">
              <h2 style="color:#333;">{{ inprogress }}</h2><p style="color:#555;">Quiz In Progress</p>
            </div>
          </div>
          <div class="col-md-4">
            <div class="stat-card" style="background:linear-gradient(135deg,#bdc3c7,#2c3e50);">
              <h2>{{ not_started }}</h2><p>Not Started Yet</p>
            </div>
          </div>
        </div>

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

        {% if pending > 0 %}
        <div class="card p-3 mb-4 border-warning">
          <h6 class="text-warning mb-3">Pending Approvals ({{ pending }})</h6>
          <table class="table table-sm mb-0">
            <thead class="table-light"><tr><th>Username</th><th>Email</th><th>Action</th></tr></thead>
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

        <div class="card p-3">
          <h6 class="mb-3">All Users</h6>
          <table class="table table-hover table-sm mb-0">
            <thead class="table-dark">
              <tr><th>Username</th><th>Email</th><th>Status</th><th>Quiz</th><th>Score</th><th>Logins</th><th>Last Login</th><th>Action</th></tr>
            </thead>
            <tbody>
            {% for u in users %}
              <tr>
                <td><b>{{ u['username'] }}</b></td>
                <td>{{ u['email'] }}</td>
                <td>
                  {% if u['approved'] %}<span class="badge bg-success badge-status">Approved</span>
                  {% else %}<span class="badge bg-warning text-dark badge-status">Pending</span>{% endif %}
                </td>
                <td>
                  {% if u['quiz_status'] == 'completed' %}<span class="badge bg-success badge-status">Completed</span>
                  {% elif u['quiz_status'] == 'in_progress' %}<span class="badge bg-info badge-status">In Progress</span>
                  {% else %}<span class="badge bg-secondary badge-status">Not Started</span>{% endif %}
                </td>
                <td>{{ u['quiz_score'] or '-' }}</td>
                <td>{{ u['login_count'] or 0 }}</td>
                <td style="font-size:.8rem;">{{ u['last_login'] or 'Never' }}</td>
                <td>
                  {% if not u['approved'] %}
                    <a href="/approve/{{ u['id'] }}" class="btn btn-sm btn-success">Approve</a>
                  {% else %}
                    <a href="/revoke/{{ u['id'] }}" class="btn btn-sm btn-outline-danger">Revoke</a>
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
    users=users, total=total, approved=approved, pending=pending,
    completed=completed, inprogress=inprogress, not_started=not_started,
    total_logins=total_logins,
    mcq_count=mcq_count, mcq_total=mcq_total,
    coding_count=coding_count, coding_total=coding_total)


@admin_bp.route('/admin/users')
def admin_users():
    if session.get('role') != 'admin':
        return redirect('/login')
    return redirect('/admin')


@admin_bp.route('/approve/<int:uid>')
def approve(uid):
    if session.get('role') != 'admin':
        return redirect('/login')
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        conn.execute("UPDATE users SET approved=1 WHERE id=?", (uid,))
        conn.commit()
    if user:
        send_approval_email(user['email'], user['username'])
    return redirect('/admin')


@admin_bp.route('/approve_token/<token>')
def approve_token(token):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
        if not user:
            return render_template_string(CSS + """
            <div class="container mt-5 d-flex justify-content-center">
              <div class="card p-4 text-center" style="width:400px">
                <h5 class="text-danger">Invalid or already used link.</h5>
                <a href="/admin" class="btn btn-primary mt-3">Go to Admin Panel</a>
              </div>
            </div>""")
        conn.execute("UPDATE users SET approved=1, token=NULL WHERE token=?", (token,))
        conn.commit()

    send_approval_email(user['email'], user['username'])

    return render_template_string(CSS + """
    <div class="container mt-5 d-flex justify-content-center">
      <div class="card p-4 text-center" style="width:400px">
        <h2 style="color:#28a745;">&#10003; Approved!</h2>
        <p><b>{{ username }}</b> can now login to the platform.</p>
        <a href="/admin" class="btn btn-primary mt-2">Go to Admin Panel</a>
      </div>
    </div>
    """, username=user['username'])


@admin_bp.route('/revoke/<int:uid>')
def revoke(uid):
    if session.get('role') != 'admin':
        return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE users SET approved=0 WHERE id=?", (uid,))
        conn.commit()
    return redirect('/admin')


@admin_bp.route('/admin/add_mcq', methods=['GET', 'POST'])
def add_mcq():
    if session.get('role') != 'admin':
        return redirect('/login')

    msg = ""
    new_ids = []

    if request.method == 'POST':
        action = request.form.get('action', 'manual')

        if action == 'manual':
            with get_db() as conn:
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
                        for i, raw in enumerate(rows):
                            r   = normalize_row(raw)
                            q   = find_col(r, 'question', 'q', 'ques')
                            oa  = find_col(r, 'a', 'option_a', 'option_a', 'opt_a', 'opt1', 'option1', 'choice_a', 'choice1')
                            ob  = find_col(r, 'b', 'option_b', 'option_b', 'opt_b', 'opt2', 'option2', 'choice_b', 'choice2')
                            oc  = find_col(r, 'c', 'option_c', 'option_c', 'opt_c', 'opt3', 'option3', 'choice_c', 'choice3')
                            od  = find_col(r, 'd', 'option_d', 'option_d', 'opt_d', 'opt4', 'option4', 'choice_d', 'choice4')
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
    except Exception:
        questions = []
    conn.close()
    new_ids_set       = set(new_ids)
    published_count   = sum(1 for q in questions if q['published'])
    unpublished_count = len(questions) - published_count

    return render_template_string(CSS + SIDEBAR + """
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
      <div class="col-md-4">
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
            <tr><td colspan="5" class="text-center text-muted py-3">No questions yet.</td></tr>
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


@admin_bp.route('/admin/add_coding', methods=['GET', 'POST'])
def add_coding():
    if session.get('role') != 'admin':
        return redirect('/login')

    msg     = ""
    new_ids = []

    if request.method == 'POST':
        action = request.form.get('action', 'manual')

        if action == 'manual':
            with get_db() as conn:
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
                        for i, raw in enumerate(rows):
                            r  = normalize_row(raw)
                            q  = find_col(r, 'question', 'q', 'ques')
                            si = find_col(r, 'sample_input', 'input', 'sample_input', 'sampleinput')
                            so = find_col(r, 'sample_output', 'output', 'sample_output', 'sampleoutput')
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
    except Exception:
        questions = []
    conn.close()

    published_count   = sum(1 for q in questions if q['published'])
    unpublished_count = len(questions) - published_count
    new_ids_set = set(new_ids)

    return render_template_string(CSS + SIDEBAR + """
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
        <b>{{ parts[1] }} questions imported!</b>
        {% if parts[2] %}<br><small>{{ parts[2] }}</small>{% endif %}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% elif msg and msg.startswith('csv_err') %}
      <div class="alert alert-danger">Upload error: {{ msg.split(':',1)[1] }}</div>
    {% endif %}

    <div class="row g-4">
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
            <tr><td colspan="6" class="text-center text-muted py-3">No questions yet.</td></tr>
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


@admin_bp.route('/admin/upload', methods=['GET', 'POST'])
def upload_questions():
    if session.get('role') != 'admin':
        return redirect('/login')

    result       = None
    new_ids      = []
    import_qtype = None

    if request.method == 'POST':
        action = request.form.get('action', 'import')

        if action in ('publish_imported', 'unpublish_imported'):
            ids   = request.form.getlist('qids')
            qtype = request.form.get('qtype_imported', 'mcq')
            table = 'questions' if qtype == 'mcq' else 'coding_questions'
            val   = 1 if action == 'publish_imported' else 0
            with get_db() as conn:
                for qid in ids:
                    conn.execute(f"UPDATE {table} SET published=? WHERE id=?", (val, qid))
                conn.commit()
            label  = 'Published' if val else 'Unpublished'
            result = {'status': 'success', 'imported': len(ids), 'errors': [],
                      'qtype': qtype, 'msg': f'{label} {len(ids)} questions.', 'action': label}
        else:
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
                                for i, raw in enumerate(rows):
                                    r = normalize_row(raw)
                                    try:
                                        q   = find_col(r, 'question', 'q', 'ques')
                                        oa  = find_col(r, 'a', 'option_a', 'opt_a', 'opt1', 'option1', 'choice_a', 'choice1')
                                        ob  = find_col(r, 'b', 'option_b', 'opt_b', 'opt2', 'option2', 'choice_b', 'choice2')
                                        oc  = find_col(r, 'c', 'option_c', 'opt_c', 'opt3', 'option3', 'choice_c', 'choice3')
                                        od  = find_col(r, 'd', 'option_d', 'opt_d', 'opt4', 'option4', 'choice_d', 'choice4')
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
                                for i, raw in enumerate(rows):
                                    r = normalize_row(raw)
                                    try:
                                        q  = find_col(r, 'question', 'q', 'ques')
                                        si = find_col(r, 'sample_input', 'input', 'sample_input')
                                        so = find_col(r, 'sample_output', 'output', 'sample_output')
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

    imported_questions = []
    if new_ids and import_qtype:
        conn = get_db()
        table        = 'questions' if import_qtype == 'mcq' else 'coding_questions'
        placeholders = ','.join('?' * len(new_ids))
        imported_questions = conn.execute(
            f"SELECT * FROM {table} WHERE id IN ({placeholders})", new_ids
        ).fetchall()
        conn.close()

    return render_template_string(CSS + SIDEBAR + """
    <h5 class="mb-4">Upload Questions</h5>

    {% if result %}
      {% if result.status == 'success' %}
      <div class="alert alert-success alert-dismissible fade show">
        <b>{{ result.imported }} {{ result.qtype|upper }} question(s)
        {% if result.action == 'import' %}imported{% else %}{{ result.action|lower }}ed{% endif %}
        successfully!</b>
        {% if result.errors %}<ul class="mb-0 mt-1">{% for e in result.errors %}<li>{{ e }}</li>{% endfor %}</ul>{% endif %}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
      {% else %}
      <div class="alert alert-danger"><b>Error:</b> {{ result.msg }}</div>
      {% endif %}
    {% endif %}

    {% if imported_questions %}
    <div class="card border-success mb-4 p-3">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h6 class="mb-0 text-success">{{ imported_questions|length }} questions just imported — review &amp; publish</h6>
        <div class="d-flex gap-2">
          <form method="post">
            <input type="hidden" name="action" value="publish_imported">
            <input type="hidden" name="qtype_imported" value="{{ import_qtype }}">
            {% for q in imported_questions %}<input type="hidden" name="qids" value="{{ q['id'] }}">{% endfor %}
            <button class="btn btn-success btn-sm">Publish All {{ imported_questions|length }}</button>
          </form>
          <form method="post">
            <input type="hidden" name="action" value="unpublish_imported">
            <input type="hidden" name="qtype_imported" value="{{ import_qtype }}">
            {% for q in imported_questions %}<input type="hidden" name="qids" value="{{ q['id'] }}">{% endfor %}
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
          <td>{% if q['published'] %}<span class="badge bg-success">Published</span>{% else %}<span class="badge bg-secondary">Draft</span>{% endif %}</td>
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
            <b style="font-size:.82rem;">CSV format:</b>
            <code style="font-size:.75rem;display:block;margin-top:6px;white-space:pre-wrap;">question, a, b, c, d, answer</code>
          </div>
        </div>
      </div>
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
            <code style="font-size:.75rem;display:block;margin-top:6px;white-space:pre-wrap;">question, sample_input, sample_output</code>
          </div>
        </div>
      </div>
    </div>

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


@admin_bp.route('/admin/sample/<kind>')
def sample_file(kind):
    if session.get('role') != 'admin':
        return redirect('/login')
    samples = {
        'mcq_csv': (
            "question,a,b,c,d,answer\n"
            "\"What is the capital of France?\",\"Berlin\",\"Madrid\",\"Paris\",\"Rome\",\"c\"\n"
            "\"Which language is used in Flask?\",\"Java\",\"Python\",\"PHP\",\"Ruby\",\"b\"\n",
            'mcq_questions.csv', 'text/csv'
        ),
        'mcq_json': (
            json.dumps([
                {"question": "What is 2+2?", "a": "1", "b": "2", "c": "3", "d": "4", "answer": "d"},
                {"question": "Which is NOT a Python data type?", "a": "int", "b": "float", "c": "char", "d": "str", "answer": "c"}
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
                {"question": "Print the largest number in a list", "sample_input": "1 2 3", "sample_output": "3"},
                {"question": "Count vowels in a string", "sample_input": "hello", "sample_output": "2"}
            ], indent=2),
            'coding_questions.json', 'application/json'
        ),
    }
    if kind not in samples:
        return "Not found", 404
    content, filename, mimetype = samples[kind]
    return Response(content, mimetype=mimetype,
                    headers={"Content-Disposition": f"attachment;filename={filename}"})


@admin_bp.route('/admin/publish/mcq/<int:qid>')
def publish_mcq(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE questions SET published=1 WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_mcq')


@admin_bp.route('/admin/unpublish/mcq/<int:qid>')
def unpublish_mcq(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE questions SET published=0 WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_mcq')


@admin_bp.route('/admin/publish/coding/<int:qid>')
def publish_coding(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE coding_questions SET published=1 WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_coding')


@admin_bp.route('/admin/unpublish/coding/<int:qid>')
def unpublish_coding(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("UPDATE coding_questions SET published=0 WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_coding')


@admin_bp.route('/admin/publish_all/<qtype>')
def publish_all(qtype):
    if session.get('role') != 'admin': return redirect('/login')
    table = 'questions' if qtype == 'mcq' else 'coding_questions'
    with get_db() as conn:
        conn.execute(f"UPDATE {table} SET published=1")
        conn.commit()
    return redirect(f"/admin/add_{'mcq' if qtype == 'mcq' else 'coding'}")


@admin_bp.route('/admin/unpublish_all/<qtype>')
def unpublish_all(qtype):
    if session.get('role') != 'admin': return redirect('/login')
    table = 'questions' if qtype == 'mcq' else 'coding_questions'
    with get_db() as conn:
        conn.execute(f"UPDATE {table} SET published=0")
        conn.commit()
    return redirect(f"/admin/add_{'mcq' if qtype == 'mcq' else 'coding'}")


@admin_bp.route('/admin/delete_mcq/<int:qid>')
def delete_mcq(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("DELETE FROM questions WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_mcq')


@admin_bp.route('/admin/delete_coding/<int:qid>')
def delete_coding(qid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        conn.execute("DELETE FROM coding_questions WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/add_coding')
