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
    <a href="/admin" class="{{ 'active' if active=='dashboard' else '' }}">Dashboard</a>
    <a href="/admin/quizzes" class="{{ 'active' if active=='quizzes' else '' }}">Manage Quizzes</a>
    <a href="/admin/categories" class="{{ 'active' if active=='categories' else '' }}">Manage Questions</a>
    <a href="/admin/analytics" class="{{ 'active' if active=='analytics' else '' }}">User Analytics</a>
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

    mcq_total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    mcq_count = conn.execute("SELECT COUNT(*) FROM questions WHERE published=1").fetchone()[0]
    coding_total = conn.execute("SELECT COUNT(*) FROM coding_questions").fetchone()[0]
    coding_count = conn.execute("SELECT COUNT(*) FROM coding_questions WHERE published=1").fetchone()[0]
    quizzes = conn.execute("""
        SELECT q.*, c.name as cat_name, c.type as cat_type,
        (SELECT COUNT(*) FROM quiz_topics WHERE quiz_id = q.id) + 
        (SELECT COUNT(*) FROM quiz_manual_questions WHERE quiz_id = q.id) as q_count
        FROM quizzes q
        JOIN categories c ON q.category_id = c.id
        ORDER BY q.id DESC
    """).fetchall()
    conn.close()

    return render_template_string(CSS + SIDEBAR + """
    <style>
      .stat-card { border-radius:12px; padding:20px; color:#fff; text-align:center; }
      .stat-card h2 { font-size:2.5rem; font-weight:700; margin:0; }
      .stat-card p  { margin:4px 0 0; font-size:.95rem; opacity:.9; }
      .badge-status { font-size:.8rem; padding:5px 10px; border-radius:20px; }
    </style>
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
            <div class="card p-3 text-center shadow-sm border-0">
              <h5 class="text-muted small fw-bold">MCQ QUESTIONS</h5>
              <h2 class="text-primary fw-bold">{{ mcq_total }}</h2>
              <p class="text-muted mb-0" style="font-size:.82rem;">Total questions in database</p>
            </div>
          </div>
          <div class="col-md-6">
            <div class="card p-3 text-center shadow-sm border-0">
              <h5 class="text-muted small fw-bold">CODING QUESTIONS</h5>
              <h2 class="text-success fw-bold">{{ coding_total }}</h2>
              <p class="text-muted mb-0" style="font-size:.82rem;">Total tasks in database</p>
            </div>
          </div>
        </div>

        <div class="card p-3 shadow-sm border-0">
          <!-- Search + Tabs Header -->
          <div class="d-flex justify-content-between align-items-center mb-3">
            <div class="d-flex gap-2">
              <button class="btn btn-sm btn-primary fw-bold user-tab active" data-tab="pending" onclick="switchTab('pending')">
                Pending <span class="badge bg-warning text-dark ms-1">{{ pending }}</span>
              </button>
              <button class="btn btn-sm btn-outline-secondary fw-bold user-tab" data-tab="approved" onclick="switchTab('approved')">
                Approved <span class="badge bg-success ms-1">{{ approved }}</span>
              </button>
              <button class="btn btn-sm btn-outline-secondary fw-bold user-tab" data-tab="all" onclick="switchTab('all')">
                All Users <span class="badge bg-dark ms-1">{{ total }}</span>
              </button>
            </div>
            <div style="width:260px;">
              <input type="text" id="userSearch" class="form-control form-control-sm" placeholder="Search by name or email..." oninput="filterAndPaginate()">
            </div>
          </div>

          <!-- Pending Tab (with bulk approve) -->
          <form method="post" action="/admin/bulk_approve" id="tab-pending">
            <table class="table table-hover table-sm mb-2" id="pending-table">
              <thead class="table-warning">
                <tr>
                  <th style="width:30px;"><input type="checkbox" id="selectAll" onclick="document.querySelectorAll('.bulk-chk:not([style*=display])').forEach(c=>c.checked=this.checked)"></th>
                  <th>Username</th><th>Email</th><th>Action</th>
                </tr>
              </thead>
              <tbody>
              {% for u in users if not u['approved'] %}
                <tr class="user-row" data-name="{{ u['username']|lower }}" data-email="{{ u['email']|lower }}" data-status="pending">
                  <td><input type="checkbox" name="user_ids" value="{{ u['id'] }}" class="bulk-chk"></td>
                  <td><b>{{ u['username'] }}</b></td>
                  <td>{{ u['email'] }}</td>
                  <td><a href="/approve/{{ u['id'] }}" class="btn btn-sm btn-success py-0 px-2">Approve</a></td>
                </tr>
              {% else %}
                <tr class="empty-msg"><td colspan="4" class="text-center text-muted py-4">No pending approvals 🎉</td></tr>
              {% endfor %}
              </tbody>
            </table>
            {% if pending > 0 %}
            <div class="d-flex justify-content-between align-items-center">
              <button type="submit" class="btn btn-warning btn-sm fw-bold px-3">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" class="me-1"><path d="M12.354 4.354a.5.5 0 0 0-.708-.708L5 10.293 2.354 7.646a.5.5 0 1 0-.708.708l3 3a.5.5 0 0 0 .708 0l7-7z"/></svg>
                Approve Selected
              </button>
              <div id="pagination-pending" class="d-flex align-items-center gap-2"></div>
            </div>
            {% endif %}
          </form>

          <!-- Approved Tab -->
          <div id="tab-approved" class="d-none">
            <table class="table table-hover table-sm mb-2" id="approved-table">
              <thead class="table-dark">
                <tr><th>Username</th><th>Email</th><th>Quiz</th><th>Score</th><th>Logins</th><th>Last Login</th><th>Action</th></tr>
              </thead>
              <tbody>
              {% for u in users if u['approved'] %}
                <tr class="user-row" data-name="{{ u['username']|lower }}" data-email="{{ u['email']|lower }}" data-status="approved">
                  <td><b>{{ u['username'] }}</b></td>
                  <td>{{ u['email'] }}</td>
                  <td>
                    {% if u['quiz_status'] == 'completed' %}<span class="badge bg-success badge-status">Completed</span>
                    {% elif u['quiz_status'] == 'in_progress' %}<span class="badge bg-info badge-status">In Progress</span>
                    {% else %}<span class="badge bg-secondary badge-status">Not Started</span>{% endif %}
                  </td>
                  <td>{{ u['quiz_score'] or '-' }}</td>
                  <td>{{ u['login_count'] or 0 }}</td>
                  <td style="font-size:.78rem;">{{ u['last_login'] or 'Never' }}</td>
                  <td><a href="/revoke/{{ u['id'] }}" class="btn btn-sm btn-outline-danger py-0 px-2">Revoke</a></td>
                </tr>
              {% else %}
                <tr class="empty-msg"><td colspan="7" class="text-center text-muted py-4">No approved users yet.</td></tr>
              {% endfor %}
              </tbody>
            </table>
            <div id="pagination-approved" class="d-flex justify-content-end align-items-center gap-2"></div>
          </div>

          <!-- All Users Tab -->
          <div id="tab-all" class="d-none">
            <table class="table table-hover table-sm mb-2" id="all-table">
              <thead class="table-dark">
                <tr><th>Username</th><th>Email</th><th>Status</th><th>Quiz</th><th>Score</th><th>Logins</th><th>Last Login</th><th>Action</th></tr>
              </thead>
              <tbody>
              {% for u in users %}
                <tr class="user-row" data-name="{{ u['username']|lower }}" data-email="{{ u['email']|lower }}" data-status="all">
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
                  <td style="font-size:.78rem;">{{ u['last_login'] or 'Never' }}</td>
                  <td>
                    {% if not u['approved'] %}
                      <a href="/approve/{{ u['id'] }}" class="btn btn-sm btn-success py-0 px-2">Approve</a>
                    {% else %}
                      <a href="/revoke/{{ u['id'] }}" class="btn btn-sm btn-outline-danger py-0 px-2">Revoke</a>
                    {% endif %}
                  </td>
                </tr>
              {% else %}
                <tr class="empty-msg"><td colspan="8" class="text-center text-muted py-4">No users registered yet.</td></tr>
              {% endfor %}
              </tbody>
            </table>
            <div id="pagination-all" class="d-flex justify-content-end align-items-center gap-2"></div>
          </div>
        </div>

        <script>
          const PER_PAGE = 10;
          let currentTab = 'pending';
          let currentPages = { pending: 1, approved: 1, all: 1 };

          function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.user-tab').forEach(b => {
              b.classList.remove('btn-primary', 'active');
              b.classList.add('btn-outline-secondary');
            });
            const btn = document.querySelector(`.user-tab[data-tab="${tab}"]`);
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-primary', 'active');

            document.getElementById('tab-pending').classList.toggle('d-none', tab !== 'pending');
            document.getElementById('tab-approved').classList.toggle('d-none', tab !== 'approved');
            document.getElementById('tab-all').classList.toggle('d-none', tab !== 'all');

            filterAndPaginate();
          }

          function filterAndPaginate() {
            const query = document.getElementById('userSearch').value.toLowerCase().trim();
            const tabId = currentTab === 'pending' ? 'pending-table' : (currentTab === 'approved' ? 'approved-table' : 'all-table');
            const rows = Array.from(document.querySelectorAll(`#${tabId} tbody .user-row`));

            // Filter
            let visible = [];
            rows.forEach(row => {
              const name = row.dataset.name || '';
              const email = row.dataset.email || '';
              const match = !query || name.includes(query) || email.includes(query);
              if (match) {
                visible.push(row);
              }
              row.style.display = 'none';
            });

            // Paginate
            const totalPages = Math.max(1, Math.ceil(visible.length / PER_PAGE));
            if (currentPages[currentTab] > totalPages) currentPages[currentTab] = 1;
            const page = currentPages[currentTab];
            const start = (page - 1) * PER_PAGE;
            const end = start + PER_PAGE;

            visible.forEach((row, i) => {
              row.style.display = (i >= start && i < end) ? '' : 'none';
            });

            // Show empty message if no results
            const emptyMsg = document.querySelector(`#${tabId} tbody .empty-msg`);
            if (emptyMsg) emptyMsg.style.display = visible.length === 0 ? '' : 'none';

            // Render pagination controls
            const pagDiv = document.getElementById(`pagination-${currentTab}`);
            if (visible.length <= PER_PAGE) {
              pagDiv.innerHTML = `<small class="text-muted">${visible.length} user${visible.length !== 1 ? 's' : ''}</small>`;
              return;
            }

            let html = `<small class="text-muted me-2">Page ${page}/${totalPages} (${visible.length} users)</small>`;
            html += `<button class="btn btn-sm btn-outline-secondary" ${page <= 1 ? 'disabled' : ''} onclick="goPage(${page - 1})">‹ Prev</button>`;
            
            // Show page numbers (max 5)
            let pStart = Math.max(1, page - 2);
            let pEnd = Math.min(totalPages, pStart + 4);
            if (pEnd - pStart < 4) pStart = Math.max(1, pEnd - 4);
            
            for (let p = pStart; p <= pEnd; p++) {
              html += `<button class="btn btn-sm ${p === page ? 'btn-primary' : 'btn-outline-secondary'}" onclick="goPage(${p})">${p}</button>`;
            }
            
            html += `<button class="btn btn-sm btn-outline-secondary" ${page >= totalPages ? 'disabled' : ''} onclick="goPage(${page + 1})">Next ›</button>`;
            pagDiv.innerHTML = html;
          }

          function goPage(p) {
            currentPages[currentTab] = p;
            filterAndPaginate();
          }

          // Initialize
          filterAndPaginate();
        </script>
      </div>
    </div>
    """,
    username=session['username'],
    now=datetime.now().strftime("%A, %d %B %Y  %I:%M %p"),
    users=users, total=total, approved=approved, pending=pending,
    completed=completed, inprogress=inprogress, not_started=not_started,
    total_logins=total_logins,
    mcq_count=mcq_count, mcq_total=mcq_total,
    coding_count=coding_count, coding_total=coding_total,
    quizzes=quizzes,
    active='dashboard')





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
        send_approval_email(user['email'], user['username'], request.host_url)
    return redirect('/admin')


@admin_bp.route('/admin/bulk_approve', methods=['POST'])
def bulk_approve():
    if session.get('role') != 'admin':
        return redirect('/login')
    
    user_ids = request.form.getlist('user_ids')
    if user_ids:
        with get_db() as conn:
            placeholders = ','.join('?' for _ in user_ids)
            conn.execute(f"UPDATE users SET approved=1 WHERE id IN ({placeholders})", user_ids)
            users_to_email = conn.execute(f"SELECT email, username FROM users WHERE id IN ({placeholders})", user_ids).fetchall()
            conn.commit()
            
        for u in users_to_email:
            send_approval_email(u['email'], u['username'], request.host_url)
            
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

    send_approval_email(user['email'], user['username'], request.host_url)

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


@admin_bp.route('/admin/analytics')
def admin_analytics():
    if session.get('role') != 'admin':
        return redirect('/login')
        
    conn = get_db()
    current_year = datetime.now().year
    
    # Monthly Logins for current year
    monthly_data = conn.execute("""
        SELECT strftime('%m', login_date) as month, COUNT(*) as count
        FROM login_history
        WHERE strftime('%Y', login_date) = ?
        GROUP BY month
        ORDER BY month ASC
    """, (str(current_year),)).fetchall()
    
    # Convert month numbers to names
    month_names = {
        '01': 'January', '02': 'February', '03': 'March', '04': 'April',
        '05': 'May', '06': 'June', '07': 'July', '08': 'August',
        '09': 'September', '10': 'October', '11': 'November', '12': 'December'
    }
    
    stats = []
    total_this_year = 0
    for row in monthly_data:
        m_name = month_names.get(row['month'], row['month'])
        stats.append({'name': m_name, 'count': row['count']})
        total_this_year += row['count']
        
    # Simple prediction logic: 
    # Average logins per month * 12 for next year + 15% estimated growth
    avg_per_month = total_this_year / len(stats) if stats else 0
    predicted_next_year = int((avg_per_month * 12) * 1.15)
    
    # Lifetime stats from old data
    total_lifetime_logins = conn.execute("SELECT SUM(login_count) FROM users").fetchone()[0] or 0
    total_users = conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]
    
    conn.close()
    
    return render_template_string(CSS + SIDEBAR + """
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h4 class="mb-0">User Analytics & Insights</h4>
      <div class="d-flex gap-2">
        <div class="badge bg-dark px-3 py-2">Total Historical Logins: {{ lifetime }}</div>
        <div class="badge bg-primary px-3 py-2">Year: {{ year }}</div>
      </div>
    </div>

    <div class="row g-4 mb-4">
       <div class="col-md-4">
          <div class="card p-3 shadow-sm border-0 bg-white">
             <small class="text-muted fw-bold">TOTAL REGISTERED USERS</small>
             <h3 class="mb-0">{{ total_u }}</h3>
          </div>
       </div>
       <div class="col-md-4">
          <div class="card p-3 shadow-sm border-0 bg-white text-primary">
             <small class="text-muted fw-bold">TOTAL LOGINS (LIFETIME)</small>
             <h3 class="mb-0">{{ lifetime }}</h3>
          </div>
       </div>
       <div class="col-md-4">
          <div class="card p-3 shadow-sm border-0 bg-white text-success">
             <small class="text-muted fw-bold">CURRENT YEAR LOGINS</small>
             <h3 class="mb-0">{{ total_this_year }}</h3>
          </div>
       </div>
    </div>

    <div class="row g-4 mb-5">
      <div class="col-md-6">
        <div class="card h-100 shadow-sm border-0 p-4">
          <h6 class="text-muted fw-bold mb-4">LOGINS BY MONTH ({{ year }})</h6>
          <div class="table-responsive">
            <table class="table table-hover align-middle">
              <thead class="table-light">
                <tr><th>Month</th><th>Login Count</th><th style="width:150px;">Trend</th></tr>
              </thead>
              <tbody>
                {% for s in stats %}
                <tr>
                  <td><b>{{ s.name }}</b></td>
                  <td><span class="badge bg-info text-dark px-3">{{ s.count }}</span></td>
                  <td>
                    <div class="progress" style="height:8px;">
                      <div class="progress-bar bg-success" style="width: {{ (s.count/max_count*100) if max_count > 0 else 0 }}%"></div>
                    </div>
                  </td>
                </tr>
                {% else %}
                <tr><td colspan="3" class="text-center py-4 text-muted">No login data recorded for this year yet.</td></tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      
      <div class="col-md-6">
        <div class="card h-100 shadow-sm border-0 p-4 bg-dark text-white">
          <h6 class="text-white-50 fw-bold mb-4">FUTURE PREDICTIONS</h6>
          <div class="mb-5">
            <h1 class="display-4 fw-bold text-success">{{ predicted }}</h1>
            <p class="text-white-50">Estimated Logins for {{ year + 1 }}</p>
            <hr class="border-secondary">
            <small class="text-white-50">
              * Based on current monthly average ({{ avg|int }} logins/mo) with a 15% projected growth in user engagement.
            </small>
          </div>
          
          <div class="alert alert-info bg-opacity-10 border-info text-info small">
             <strong>Idea:</strong> To increase next year's numbers, consider sending automated email reminders to users who haven't logged in for 30 days.
          </div>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0 p-4">
       <h6 class="text-muted fw-bold mb-3">DATA INTEGRITY NOTICE</h6>
       <p class="small text-muted mb-0">
          Historical data before today is not available because tracking was just enabled. 
          The system will now record every login event to build accurate monthly reports going forward.
       </p>
    </div>
    """, year=current_year, stats=stats, 
       max_count=max([s['count'] for s in stats]) if stats else 0,
       predicted=predicted_next_year, avg=avg_per_month, 
       lifetime=total_lifetime_logins, total_u=total_users, 
       total_this_year=total_this_year,
       active='analytics')


@admin_bp.route('/admin/quizzes')
def admin_quizzes():
    if session.get('role') != 'admin':
        return redirect('/login')
    conn = get_db()
    quizzes = conn.execute("""
        SELECT q.*, c.name as cat_name, c.type as cat_type,
        (SELECT COUNT(*) FROM quiz_topics WHERE quiz_id = q.id) + 
        (SELECT COUNT(*) FROM quiz_manual_questions WHERE quiz_id = q.id) as q_count
        FROM quizzes q
        JOIN categories c ON q.category_id = c.id
        ORDER BY q.id DESC
    """).fetchall()
    active_quizzes = []
    for q in quizzes:
        q_dict = dict(q)
        if q_dict['cat_type'] == 'mixed':
            mcq_time = f"{q_dict.get('mcq_time_limit', 0)}m" if q_dict.get('mcq_time_limit', 0) > 0 else "Unltd"
            coding_time = f"{q_dict.get('coding_time_limit', 0)}m" if q_dict.get('coding_time_limit', 0) > 0 else "Unltd"
            q_dict['display_time'] = f"M:{mcq_time}|C:{coding_time}"
        elif q_dict['cat_type'] == 'mcq':
            t = q_dict.get('mcq_time_limit') or q_dict['time_limit']
            q_dict['display_time'] = f"{t}m" if t > 0 else "Unltd"
        else:
            t = q_dict.get('coding_time_limit') or q_dict['time_limit']
            q_dict['display_time'] = f"{t}m" if t > 0 else "Unltd"
        active_quizzes.append(q_dict)
    conn.close()
    return render_template_string(CSS + SIDEBAR + """
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h4 class="mb-0">Manage Quizzes</h4>
      <a href="/admin/quiz/create" class="btn btn-primary">+ Create New Quiz</a>
    </div>
    <div class="card p-3 shadow-sm border-0">
      <table class="table table-hover align-middle mb-0">
        <thead class="table-dark">
          <tr><th>Quiz Name</th><th>Category</th><th>Type</th><th>Duration</th><th>Questions</th><th>Action</th></tr>
        </thead>
        <tbody>
        {% for q in active_quizzes %}
          <tr>
            <td><b class="text-primary">{{ q.name }}</b></td>
            <td>{{ q.cat_name }}</td>
            <td><span class="badge {{ 'bg-primary' if q.cat_type == 'mcq' else ('bg-success' if q.cat_type == 'coding' else 'bg-purple') }}" {% if q.cat_type == 'mixed' %}style="background:#7c3aed;"{% endif %}>{{ q.cat_type|upper }}</span></td>
            <td>{{ q.display_time }}</td>
            <td>{{ q.q_count }}</td>
            <td>
              <a href="/admin/quiz/delete/{{ q.id }}" class="btn btn-sm btn-outline-danger" onclick="return confirm('Delete this quiz permanently?')">Delete</a>
            </td>
          </tr>
        {% else %}
          <tr><td colspan="6" class="text-center py-4 text-muted">No quizzes found. Click the button above to create one.</td></tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    """, active_quizzes=active_quizzes, active='quizzes')


@admin_bp.route('/admin/quiz/delete/<int:qid>')
def delete_quiz(qid):
    if session.get('role') != 'admin':
        return redirect('/login')
    with get_db() as conn:
        conn.execute("DELETE FROM quiz_topics WHERE quiz_id=?", (qid,))
        conn.execute("DELETE FROM quiz_manual_questions WHERE quiz_id=?", (qid,))
        conn.execute("DELETE FROM quizzes WHERE id=?", (qid,))
        conn.commit()
    return redirect('/admin/quizzes')


@admin_bp.route('/admin/categories', methods=['GET', 'POST'])
def categories():
    if session.get('role') != 'admin':
        return redirect('/login')
    
    if request.method == 'POST':
        name = request.form.get('name')
        ctype = request.form.get('type')
        if name and ctype in ['mcq', 'coding', 'mixed']:
            with get_db() as conn:
                conn.execute("INSERT INTO categories (name, type) VALUES (?, ?)", (name, ctype))
                conn.commit()
            return redirect('/admin/categories')

    conn = get_db()
    categories = conn.execute("SELECT * FROM categories").fetchall()
    conn.close()
    
    return render_template_string(CSS + SIDEBAR + """
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h4 class="mb-0">Select Category</h4>
      <button class="btn btn-primary" onclick="document.getElementById('createCategoryForm').classList.toggle('d-none')">+ New Category</button>
    </div>
    
    <div id="createCategoryForm" class="card p-3 mb-4 d-none shadow-sm border-0">
      <form method="post" class="row g-3 align-items-end">
        <div class="col-md-5">
          <label class="form-label fw-bold">Category Name</label>
          <input type="text" name="name" class="form-control" placeholder="e.g. Python Advanced" required>
        </div>
        <div class="col-md-4">
          <label class="form-label fw-bold">Type</label>
          <select name="type" class="form-select" required>
            <option value="mcq">Multiple Choice Questions</option>
            <option value="coding">Programming Tasks</option>
            <option value="mixed">Mixed (MCQ + Coding)</option>
          </select>
        </div>
        <div class="col-md-3">
          <button type="submit" class="btn btn-success w-100">Create</button>
        </div>
      </form>
    </div>

    <div class="row g-4">
      {% for cat in categories %}
      <div class="col-md-6">
        <div class="card h-100 shadow-sm border-0 transition-transform hover-scale" 
             style="cursor:pointer;" onclick="location.href='/admin/category/{{ cat.id }}'">
          <div class="card-body p-4 text-center">
            <div class="display-4 mb-3">
              {% if cat.type == 'mcq' %}📚{% elif cat.type == 'coding' %}💻{% else %}🔀{% endif %}
            </div>
            <h5 class="card-title">{{ cat.name }}</h5>
            <p class="text-muted">{{ 'Multiple Choice Questions' if cat.type == 'mcq' else ('Programming Tasks' if cat.type == 'coding' else 'Mixed (MCQ + Coding)') }}</p>
            <div class="mt-3">
               <span class="badge bg-primary px-3 py-2">Manage Topics</span>
            </div>
          </div>
        </div>
      </div>
      {% endfor %}
    </div>
    <style>
      .hover-scale:hover { transform: scale(1.02); transition: all 0.2s; }
    </style>
    """, categories=categories, active='categories')


@admin_bp.route('/admin/category/<int:cat_id>')
def category_topics(cat_id):
    if session.get('role') != 'admin':
        return redirect('/login')
    
    conn = get_db()
    category = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    
    if category['type'] == 'mixed':
        # For mixed categories, show topics from ALL categories (both mcq and coding)
        topics = conn.execute("SELECT t.*, c.type as src_type, c.name as src_cat FROM topics t JOIN categories c ON t.category_id = c.id WHERE c.type IN ('mcq', 'coding')").fetchall()
    else:
        topics = conn.execute("SELECT * FROM topics WHERE category_id=?", (cat_id,)).fetchall()
    
    topic_data = []
    for t in topics:
        if category['type'] == 'mixed':
            src_type = t['src_type']
        else:
            src_type = category['type']
        q_table = 'questions' if src_type == 'mcq' else 'coding_questions'
        count = conn.execute(f"SELECT COUNT(*) FROM {q_table} WHERE topic_id=?", (t['id'],)).fetchone()[0]
        topic_data.append({'id': t['id'], 'name': t['name'], 'count': count, 'src_type': src_type, 'src_cat': dict(t).get('src_cat', '')})
    
    conn.close()
    
    return render_template_string(CSS + SIDEBAR + """
    <div class="d-flex justify-content-between align-items-center mb-4">
      <div>
        <h4 class="mb-1">{{ category.name }} - Topics</h4>
        <p class="text-muted small mb-0">Manage questions for each topic</p>
      </div>
      <a href="/admin/categories" class="btn btn-outline-secondary btn-sm">&larr; Back</a>
    </div>

    <div class="row g-4">
      {% for topic in topic_data %}
      <div class="col-md-6 col-lg-4">
        <div class="card h-100 shadow-sm border-0">
          <div class="card-body p-4">
            <div class="d-flex justify-content-between align-items-start mb-3">
              <div>
                <h5 class="mb-0 fw-bold">{{ topic.name }}</h5>
                {% if category.type == 'mixed' %}
                  <span class="badge {{ 'bg-primary' if topic.src_type == 'mcq' else 'bg-success' }} mt-1">{{ topic.src_type|upper }}</span>
                  <small class="text-muted ms-1">from {{ topic.src_cat }}</small>
                {% endif %}
              </div>
              <span class="badge bg-light text-primary border">{{ topic.count }} Qs</span>
            </div>
            <p class="text-muted small">Bulk upload questions or manage existing ones for this topic.</p>
            <hr>
            <div class="d-grid gap-2">
              <button class="btn btn-primary btn-sm" onclick="showUploadModal({{ topic.id }}, '{{ topic.name }}')">
                Bulk Upload (CSV)
              </button>
              <a href="/admin/topic/{{ topic.id }}/manage" class="btn btn-info btn-sm text-white">View Questions</a>
              <a href="/admin/quiz/create?topic_id={{ topic.id }}" class="btn btn-outline-success btn-sm">Create Quiz</a>
              <form action="/admin/topic/{{ topic.id }}/clear" method="POST" class="d-inline" onsubmit="return confirm('Are you sure you want to delete ALL questions in this topic? This cannot be undone.');">
                <input type="hidden" name="cat_id" value="{{ category.id }}">
                <button type="submit" class="btn btn-outline-danger btn-sm w-100 mt-1">Clear All Questions</button>
              </form>
            </div>
          </div>
        </div>
      </div>
      {% endfor %}
    </div>

    <!-- Upload Modal -->
    <div class="modal fade" id="uploadModal" tabindex="-1">
      <div class="modal-dialog">
        <form class="modal-content" method="post" action="/admin/topic/upload" enctype="multipart/form-data">
          <div class="modal-header">
            <h5 class="modal-title">Bulk Upload: <span id="modalTopicName"></span></h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <input type="hidden" name="topic_id" id="modalTopicId">
            <input type="hidden" name="cat_type" value="{{ category.type }}">
            
            <div class="alert alert-info small mb-3">
              <h6 class="fw-bold mb-1">Required CSV Headers:</h6>
              {% if category.type == 'mcq' %}
                <code class="d-block mb-1 p-2 bg-light border rounded">question, a, b, c, d, answer</code>
                <span class="text-muted">Note: 'answer' should be a, b, c, or d.</span>
              {% else %}
                <code class="d-block mb-1 p-2 bg-light border rounded">question, sample_input, sample_output</code>
              {% endif %}
            </div>

            <div class="mb-3">
              <label class="form-label fw-bold">Select CSV/JSON File</label>
              <input type="file" name="file" class="form-control" accept=".csv,.json" required>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="submit" class="btn btn-primary px-4">Upload Questions</button>
          </div>
        </form>
      </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
      function showUploadModal(id, name) {
        document.getElementById('modalTopicId').value = id;
        document.getElementById('modalTopicName').innerText = name;
        new bootstrap.Modal(document.getElementById('uploadModal')).show();
      }
    </script>
    """, category=category, topic_data=topic_data, active='categories')


@admin_bp.route('/admin/topic/upload', methods=['POST'])
def topic_upload():
    if session.get('role') != 'admin':
        return redirect('/login')
    
    topic_id = request.form.get('topic_id')
    cat_type = request.form.get('cat_type')
    f = request.files.get('file')
    
    if not f or not f.filename:
        return redirect(request.referrer or '/admin/categories')

    content = f.read().decode('utf-8', errors='ignore')
    ext = f.filename.rsplit('.', 1)[-1].lower()
    imported = 0
    
    try:
        rows = json.loads(content) if ext == 'json' else list(csv.DictReader(io.StringIO(content)))
        with get_db() as conn:
            for raw in rows:
                r = normalize_row(raw)
                if cat_type == 'mcq':
                    q = find_col(r, 'question', 'q', 'ques')
                    oa = find_col(r, 'a', 'option_a', 'opt_a', 'opt1')
                    ob = find_col(r, 'b', 'option_b', 'opt_b', 'opt2')
                    oc = find_col(r, 'c', 'option_c', 'opt_c', 'opt3')
                    od = find_col(r, 'd', 'option_d', 'opt_d', 'opt4')
                    ans = find_col(r, 'answer', 'ans', 'correct')
                    if q:
                        # Check if question already exists in this topic
                        exists = conn.execute("SELECT id FROM questions WHERE topic_id=? AND question=?", (topic_id, q)).fetchone()
                        if not exists:
                            conn.execute(
                                "INSERT INTO questions(question,a,b,c,d,answer,published,topic_id) VALUES(?,?,?,?,?,?,1,?)",
                                (q, oa, ob, oc, od, ans.lower(), topic_id)
                            )
                            imported += 1
                else:
                    q = find_col(r, 'question', 'q', 'ques')
                    si = find_col(r, 'sample_input', 'input')
                    so = find_col(r, 'sample_output', 'output')
                    if q:
                        # Check if question already exists in this topic
                        exists = conn.execute("SELECT id FROM coding_questions WHERE topic_id=? AND question=?", (topic_id, q)).fetchone()
                        if not exists:
                            conn.execute(
                                "INSERT INTO coding_questions(question,sample_input,sample_output,published,topic_id) VALUES(?,?,?,1,?)",
                                (q, si, so, topic_id)
                            )
                            imported += 1
            conn.commit()
    except Exception as e:
        print(f"Upload error: {e}")
        
    return redirect(f"/admin/topic/{topic_id}/manage?msg=uploaded")


@admin_bp.route('/admin/topic/<int:topic_id>/clear', methods=['POST'])
def clear_topic_questions(topic_id):
    if session.get('role') != 'admin':
        return redirect('/login')
        
    cat_id = request.form.get('cat_id')
    
    with get_db() as conn:
        # Check category type to know which table to clear
        topic = conn.execute("SELECT c.type FROM topics t JOIN categories c ON t.category_id = c.id WHERE t.id=?", (topic_id,)).fetchone()
        if topic:
            if topic['type'] == 'mcq':
                conn.execute("DELETE FROM questions WHERE topic_id=?", (topic_id,))
            else:
                conn.execute("DELETE FROM coding_questions WHERE topic_id=?", (topic_id,))
            conn.commit()
            
    return redirect(f'/admin/category/{cat_id}')


@admin_bp.route('/admin/topic/<int:topic_id>/manage')
def admin_manage_topic_questions(topic_id):
    if session.get('role') != 'admin':
        return redirect('/login')
    
    conn = get_db()
    topic = conn.execute("SELECT t.*, c.type as cat_type, c.name as cat_name FROM topics t JOIN categories c ON t.category_id = c.id WHERE t.id = ?", (topic_id,)).fetchone()
    
    if not topic:
        return redirect('/admin/categories')

    if topic['cat_type'] == 'mcq':
        questions = conn.execute("SELECT * FROM questions WHERE topic_id = ?", (topic_id,)).fetchall()
    else:
        questions = conn.execute("SELECT * FROM coding_questions WHERE topic_id = ?", (topic_id,)).fetchall()
    
    conn.close()
    
    msg = request.args.get('msg')
    
    return render_template_string(CSS + SIDEBAR + """
    <div class="d-flex justify-content-between align-items-center mb-4">
      <div>
        <h4 class="mb-0">{{ topic.name }} - Manage Questions</h4>
        <p class="text-muted small mb-0">{{ topic.cat_name }} ({{ topic.cat_type|upper }})</p>
      </div>
      <div class="d-flex gap-2">
        <a href="/admin/topic/{{ topic.id }}/bulk_publish?action=publish" class="btn btn-success btn-sm">Publish All</a>
        <a href="/admin/topic/{{ topic.id }}/bulk_publish?action=unpublish" class="btn btn-outline-secondary btn-sm">Unpublish All</a>
        <a href="/admin/category/{{ topic.category_id }}" class="btn btn-outline-secondary btn-sm">Back to Topics</a>
      </div>
    </div>

    {% if msg == 'uploaded' %}
    <div class="alert alert-success">Bulk upload successful! Questions are listed below.</div>
    {% endif %}

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th style="width: 50px;">ID</th>
                <th>Question Content</th>
                {% if topic.cat_type == 'mcq' %}
                  <th>Options</th>
                  <th>Answer</th>
                {% else %}
                  <th>Sample Input</th>
                  <th>Sample Output</th>
                {% endif %}
                <th>Status</th>
                <th class="text-end" style="width: 150px;">Actions</th>
              </tr>
            </thead>
            <tbody>
              {% for q in questions %}
              <tr>
                <td>{{ q.id }}</td>
                <td>
                  <div style="max-width: 350px;" class="text-truncate" title="{{ q.question }}">
                    {{ q.question }}
                  </div>
                </td>
                {% if topic.cat_type == 'mcq' %}
                  <td>
                    <small class="text-muted">
                      A: {{ q.a }} | B: {{ q.b }} | C: {{ q.c }} | D: {{ q.d }}
                    </small>
                  </td>
                  <td><span class="badge bg-primary">{{ q.answer|upper }}</span></td>
                {% else %}
                  <td><code>{{ q.sample_input }}</code></td>
                  <td><code>{{ q.sample_output }}</code></td>
                {% endif %}
                <td>
                  {% if q.published %}
                    <span class="badge bg-success">Published</span>
                  {% else %}
                    <span class="badge bg-secondary">Draft</span>
                  {% endif %}
                </td>
                <td class="text-end">
                  <div class="dropdown">
                    <button class="btn btn-sm btn-light border dropdown-toggle" type="button" data-bs-toggle="dropdown">
                      Manage
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end">
                      <li>
                        <a class="dropdown-item" href="/admin/question/edit/{{ q.id }}?topic_id={{ topic.id }}" {% if topic.cat_type == 'coding' %}hidden{% endif %}>
                          Edit MCQ
                        </a>
                        <a class="dropdown-item" href="/admin/coding_question/edit/{{ q.id }}?topic_id={{ topic.id }}" {% if topic.cat_type == 'mcq' %}hidden{% endif %}>
                          Edit Coding
                        </a>
                      </li>
                      <li>
                        <a class="dropdown-item" href="/admin/topic/{{ topic.id }}/toggle/{{ q.id }}?type={{ topic.cat_type }}">
                          {{ 'Unpublish' if q.published else 'Publish' }}
                        </a>
                      </li>
                      <li><hr class="dropdown-divider"></li>
                      <li>
                        <a class="dropdown-item text-danger" href="/admin/topic/{{ topic.id }}/delete/{{ q.id }}?type={{ topic.cat_type }}" onclick="return confirm('Are you sure?')">
                          Delete
                        </a>
                      </li>
                    </ul>
                  </div>
                </td>
              </tr>
              {% else %}
              <tr>
                <td colspan="6" class="text-center py-4 text-muted">
                  No questions found for this topic. Use "Bulk Upload" to add some.
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    """, topic=topic, questions=questions, msg=msg, active='categories')


@admin_bp.route('/admin/topic/<int:topic_id>/toggle/<int:q_id>')
def toggle_question_status(topic_id, q_id):
    if session.get('role') != 'admin': return redirect('/login')
    qtype = request.args.get('type', 'mcq')
    table = 'questions' if qtype == 'mcq' else 'coding_questions'
    
    with get_db() as conn:
        conn.execute(f"UPDATE {table} SET published = 1 - published WHERE id = ?", (q_id,))
        conn.commit()
    return redirect(f"/admin/topic/{topic_id}/manage")


@admin_bp.route('/admin/topic/<int:topic_id>/delete/<int:q_id>')
def delete_topic_question(topic_id, q_id):
    if session.get('role') != 'admin': return redirect('/login')
    qtype = request.args.get('type', 'mcq')
    table = 'questions' if qtype == 'mcq' else 'coding_questions'
    
    with get_db() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (q_id,))
        conn.commit()
    return redirect(f"/admin/topic/{topic_id}/manage")

@admin_bp.route('/admin/topic/<int:topic_id>/bulk_publish')
def bulk_publish_topic(topic_id):
    if session.get('role') != 'admin': return redirect('/login')
    action = request.args.get('action', 'publish')
    val = 1 if action == 'publish' else 0
    
    conn = get_db()
    topic = conn.execute("SELECT t.*, c.type as cat_type FROM topics t JOIN categories c ON t.category_id = c.id WHERE t.id = ?", (topic_id,)).fetchone()
    if topic:
        table = 'questions' if topic['cat_type'] == 'mcq' else 'coding_questions'
        conn.execute(f"UPDATE {table} SET published = ? WHERE topic_id = ?", (val, topic_id))
        conn.commit()
    conn.close()
    return redirect(f"/admin/topic/{topic_id}/manage")

@admin_bp.route('/admin/question/edit/<int:qid>', methods=['GET', 'POST'])
def edit_mcq(qid):
    if session.get('role') != 'admin': return redirect('/login')
    topic_id = request.args.get('topic_id')
    
    conn = get_db()
    if request.method == 'POST':
        conn.execute("""
            UPDATE questions SET question=?, a=?, b=?, c=?, d=?, answer=? WHERE id=?
        """, (request.form['q'], request.form['a'], request.form['b'], 
              request.form['c'], request.form['d'], request.form['ans'], qid))
        conn.commit()
        conn.close()
        return redirect(f"/admin/topic/{topic_id}/manage" if topic_id else "/admin/categories")

    q = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
    conn.close()
    
    return render_template_string(CSS + SIDEBAR + """
    <h4 class="mb-4">Edit MCQ Question</h4>
    <form method="post" class="card p-4 shadow-sm border-0">
      <div class="mb-3">
        <label class="form-label">Question</label>
        <textarea name="q" class="form-control" rows="3" required>{{ q.question }}</textarea>
      </div>
      <div class="row g-3">
        <div class="col-md-6"><label>Option A</label><input name="a" class="form-control" value="{{ q.a }}" required></div>
        <div class="col-md-6"><label>Option B</label><input name="b" class="form-control" value="{{ q.b }}" required></div>
        <div class="col-md-6"><label>Option C</label><input name="c" class="form-control" value="{{ q.c }}" required></div>
        <div class="col-md-6"><label>Option D</label><input name="d" class="form-control" value="{{ q.d }}" required></div>
      </div>
      <div class="mt-3 mb-4">
        <label class="form-label">Correct Answer</label>
        <select name="ans" class="form-select">
          <option value="a" {% if q.answer=='a' %}selected{% endif %}>A</option>
          <option value="b" {% if q.answer=='b' %}selected{% endif %}>B</option>
          <option value="c" {% if q.answer=='c' %}selected{% endif %}>C</option>
          <option value="d" {% if q.answer=='d' %}selected{% endif %}>D</option>
        </select>
      </div>
      <div class="d-flex gap-2">
        <button class="btn btn-primary">Update Question</button>
        <a href="javascript:history.back()" class="btn btn-outline-secondary">Cancel</a>
      </div>
    </form>
    """, q=q, active='categories')


@admin_bp.route('/admin/coding_question/edit/<int:qid>', methods=['GET', 'POST'])
def edit_coding(qid):
    if session.get('role') != 'admin': return redirect('/login')
    topic_id = request.args.get('topic_id')
    
    conn = get_db()
    if request.method == 'POST':
        conn.execute("""
            UPDATE coding_questions SET question=?, sample_input=?, sample_output=? WHERE id=?
        """, (request.form['q'], request.form['si'], request.form['so'], qid))
        conn.commit()
        conn.close()
        return redirect(f"/admin/topic/{topic_id}/manage" if topic_id else "/admin/categories")

    q = conn.execute("SELECT * FROM coding_questions WHERE id=?", (qid,)).fetchone()
    conn.close()
    
    return render_template_string(CSS + SIDEBAR + """
    <h4 class="mb-4">Edit Coding Question</h4>
    <form method="post" class="card p-4 shadow-sm border-0">
      <div class="mb-3">
        <label class="form-label">Question Description</label>
        <textarea name="q" class="form-control" rows="5" required>{{ q.question }}</textarea>
      </div>
      <div class="mb-3">
        <label class="form-label">Sample Input</label>
        <input name="si" class="form-control" value="{{ q.sample_input }}">
      </div>
      <div class="mb-3">
        <label class="form-label">Sample Output</label>
        <input name="so" class="form-control" value="{{ q.sample_output }}">
      </div>
      <div class="d-flex gap-2">
        <button class="btn btn-success">Update Question</button>
        <a href="javascript:history.back()" class="btn btn-outline-secondary">Cancel</a>
      </div>
    </form>
    """, q=q, active='categories')

@admin_bp.route('/admin/quiz/create', methods=['GET', 'POST'])
def quiz_create():
    if session.get('role') != 'admin':
        return redirect('/login')
    
    conn = get_db()
    
    if request.method == 'POST':
        name = request.form.get('quiz_name')
        cat_id = request.form.get('category_id')
        def safe_int(v, default=0):
            try: return int(v) if str(v).strip() != '' else default
            except (ValueError, TypeError): return default

        def safe_float(v, default=1.0):
            try:
                val = float(v) if str(v).strip() != '' else default
                return int(val) if val.is_integer() else val
            except (ValueError, TypeError): return default

        time_limit = safe_int(request.form.get('time_limit'), 0)
        pos_marks = safe_float(request.form.get('pos_marks'), 1)
        neg_marks = safe_float(request.form.get('neg_marks'), 0)
        
        mcq_time_limit = safe_int(request.form.get('mcq_time_limit'), time_limit)
        coding_time_limit = safe_int(request.form.get('coding_time_limit'), time_limit)
        mcq_marks = safe_float(request.form.get('mcq_marks'), pos_marks)
        coding_marks = safe_float(request.form.get('coding_marks'), pos_marks)

        shuffle = 1 if request.form.get('shuffle') else 0
        attempts = safe_int(request.form.get('attempts'), 1)
        
        # Save Quiz
        cur = conn.execute("""
            INSERT INTO quizzes (name, category_id, time_limit, positive_marks, negative_marks, shuffle_questions, attempt_limit, created_at, mcq_time_limit, coding_time_limit, mcq_marks, coding_marks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, cat_id, time_limit, pos_marks, neg_marks, shuffle, attempts, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mcq_time_limit, coding_time_limit, mcq_marks, coding_marks))
        quiz_id = cur.lastrowid
        
        selection_mode = request.form.get('selection_mode') # 'random' or 'manual'
        
        if selection_mode == 'random':
            topic_ids = request.form.getlist('topic_ids')
            for tid in topic_ids:
                count = request.form.get(f'count_{tid}', 0)
                qtype = request.form.get(f'qtype_{tid}', 'mcq')
                if int(count) > 0:
                    conn.execute("INSERT INTO quiz_topics (quiz_id, topic_id, question_count, question_type) VALUES (?, ?, ?, ?)", (quiz_id, tid, count, qtype))
        else:
            q_ids = request.form.getlist('manual_q_ids')
            cat_type = conn.execute("SELECT type FROM categories WHERE id=?", (cat_id,)).fetchone()[0]
            for qid in q_ids:
                conn.execute("INSERT INTO quiz_manual_questions (quiz_id, question_id, type) VALUES (?, ?, ?)", (quiz_id, qid, cat_type))
        
        conn.commit()
        conn.close()
        return redirect('/admin/categories')

    categories = conn.execute("SELECT * FROM categories").fetchall()
    selected_topic_id = request.args.get('topic_id')
    
    # Fetch topics with their source category type for mixed quiz support
    topics = conn.execute("SELECT t.*, c.name as cat_name, c.type as cat_type FROM topics t JOIN categories c ON t.category_id = c.id").fetchall()
    
    conn.close()
    
    return render_template_string(CSS + SIDEBAR + """
    <h4 class="mb-4">Create New Quiz</h4>
    <form method="post" class="card shadow-sm border-0 p-4">
      <div class="row g-4">
        <!-- Section 1: Basic Info -->
        <div class="col-md-6">
          <label class="form-label fw-bold">Quiz Name</label>
          <input name="quiz_name" class="form-control" placeholder="e.g. Python Basics Midterm" required>
        </div>
        <div class="col-md-6">
          <label class="form-label fw-bold">Category</label>
          <select name="category_id" id="cat_select" class="form-select" required onchange="filterTopics()">
            <option value="">-- Select Category --</option>
            {% for cat in categories %}
            <option value="{{ cat.id }}" data-type="{{ cat.type }}">{{ cat.name }}</option>
            {% endfor %}
          </select>
        </div>

        <!-- Section 2: Rules -->
        <div class="col-12"><hr></div>
        <!-- MCQ Rules -->
        <div class="col-md-3 rule-mcq d-none">
          <label class="form-label fw-bold text-primary">MCQ Time Limit (mins)</label>
          <input type="number" name="mcq_time_limit" class="form-control" value="30">
          <small class="text-muted">0 for no limit</small>
        </div>
        <div class="col-md-3 rule-mcq d-none">
          <label class="form-label fw-bold text-primary">MCQ Positive Marks</label>
          <input type="number" step="0.1" name="mcq_marks" class="form-control" value="1">
        </div>

        <!-- Coding Rules -->
        <div class="col-md-3 rule-coding d-none">
          <label class="form-label fw-bold text-success">Coding Time Limit (mins)</label>
          <input type="number" name="coding_time_limit" class="form-control" value="45">
          <small class="text-muted">0 for no limit</small>
        </div>
        <div class="col-md-3 rule-coding d-none">
          <label class="form-label fw-bold text-success">Coding Positive Marks</label>
          <input type="number" step="0.1" name="coding_marks" class="form-control" value="15">
        </div>
        <div class="col-md-3">
          <label class="form-label fw-bold">Negative Marks</label>
          <input type="number" step="0.1" name="neg_marks" class="form-control" value="0">
        </div>
        <div class="col-md-3">
          <label class="form-label fw-bold">Attempt Limit</label>
          <input type="number" name="attempts" class="form-control" value="1">
        </div>
        <div class="col-md-3 mt-4">
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" name="shuffle" id="shuffle" checked>
            <label class="form-check-label fw-bold" for="shuffle">Shuffle Questions</label>
          </div>
        </div>

        <!-- Section 3: Question Selection -->
        <div class="col-12"><hr></div>
        <div class="col-12">
          <h6 class="fw-bold mb-3">Question Selection Mode</h6>
          <div class="btn-group w-100" role="group">
            <input type="radio" class="btn-check" name="selection_mode" id="mode_random" value="random" checked onclick="toggleMode('random')">
            <label class="btn btn-outline-primary" for="mode_random">Randomly generate from topics</label>
            <input type="radio" class="btn-check" name="selection_mode" id="mode_manual" value="manual" onclick="toggleMode('manual')">
            <label class="btn btn-outline-primary" for="mode_manual">Manually select questions</label>
          </div>
        </div>

        <!-- Random Mode: Topic List -->
        <div id="random_config" class="col-12">
          <table class="table table-sm mt-3">
            <thead>
              <tr><th>Select Topic</th><th>Questions to include</th></tr>
            </thead>
            <tbody id="topic_list_body">
              {% for t in topics %}
              <tr class="topic-row" data-cat="{{ t.category_id }}" data-type="{{ t.cat_type }}">
                <td class="align-middle">
                  <strong>{{ t.name }}</strong>
                  <span class="badge {{ 'bg-primary' if t.cat_type == 'mcq' else 'bg-success' }} ms-2">{{ t.cat_type|upper }}</span>
                  <small class="text-muted ms-1">({{ t.cat_name }})</small>
                  <input type="hidden" name="topic_ids" value="{{ t.id }}">
                  <input type="hidden" name="qtype_{{ t.id }}" value="{{ t.cat_type }}">
                </td>
                <td>
                  <input type="number" name="count_{{ t.id }}" class="form-control form-control-sm" style="width:100px;" value="0" min="0">
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>

        <!-- Manual Mode Placeholder -->
        <div id="manual_config" class="col-12 d-none">
          <div class="alert alert-secondary text-center py-4">
             Manual selection UI will appear here after selecting a category.
             <br><small>(Coming soon: AJAX search for questions)</small>
          </div>
        </div>

        <div class="col-12 mt-4 text-end">
          <button type="submit" class="btn btn-success px-5">Save Quiz Configuration</button>
        </div>
      </div>
    </form>

    <script>
      function filterTopics() {
        const catSel = document.getElementById('cat_select');
        const catId = catSel.value;
        const selectedOpt = catSel.options[catSel.selectedIndex];
        const catType = selectedOpt ? selectedOpt.dataset.type : '';
        
        document.querySelectorAll('.rule-mcq').forEach(el => el.classList.toggle('d-none', !(catType === 'mcq' || catType === 'mixed')));
        document.querySelectorAll('.rule-coding').forEach(el => el.classList.toggle('d-none', !(catType === 'coding' || catType === 'mixed')));

        
        document.querySelectorAll('.topic-row').forEach(row => {
          if (catType === 'mixed') {
            // For mixed categories, show topics from both mcq and coding categories
            const topicType = row.dataset.type;
            if (topicType === 'mcq' || topicType === 'coding') {
              row.classList.remove('d-none');
            } else {
              row.classList.add('d-none');
            }
          } else if (row.dataset.cat == catId || catId == "") {
            row.classList.remove('d-none');
          } else {
            row.classList.add('d-none');
          }
        });
      }

      function toggleMode(mode) {
        if (mode === 'random') {
          document.getElementById('random_config').classList.remove('d-none');
          document.getElementById('manual_config').classList.add('d-none');
        } else {
          document.getElementById('random_config').classList.add('d-none');
          document.getElementById('manual_config').classList.remove('d-none');
        }
      }
    </script>
    <style>
      .topic-row:hover { background-color: #f8f9fa; }
      .topic-row td { vertical-align: middle; }
      .btn-check:checked + .btn-outline-primary {
        background-color: #0d6efd;
        color: white;
      }
    </style>
    """, categories=categories, topics=topics, active='categories')




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



