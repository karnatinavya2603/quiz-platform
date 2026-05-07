import secrets
from datetime import datetime
from flask import Blueprint, request, redirect, session, render_template_string
from database import get_db
from services.email_service import (
    notify_admin_login, notify_user_login,
    notify_admin_registration
)

auth_bp = Blueprint('auth', __name__)

CSS = '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">'


@auth_bp.route('/')
def index():
    return redirect('/login')


@auth_bp.route('/login', methods=['GET', 'POST'])
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
            session.clear()
            session['username'] = user['username']
            session['email']    = user['email']
            session['role']     = user['role']

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET login_count=login_count+1, last_login=? WHERE username=?",
                    (now, user['username'])
                )
                conn.execute(
                    "INSERT INTO login_history (username, login_date) VALUES (?, ?)",
                    (user['username'], now)
                )
                conn.commit()

            notify_admin_login(user['username'], user['email'], user['role'], now)
            if user['role'] == 'user':
                notify_user_login(user['email'], user['username'])

            return redirect('/admin' if user['role'] == 'admin' else '/dashboard')

    return render_template_string(CSS + """
    <style>body{background:#f0f2f5;} .card{border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,.1);}</style>
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


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    import sqlite3
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
                notify_admin_registration(username, email, role, token, request.host_url)
                return render_template_string(CSS + """
                <div class="container mt-5 d-flex justify-content-center">
                  <div class="card p-4 text-center" style="width:380px">
                    <h5>Registration Submitted!</h5>
                    <p>Navya (admin) will review and approve your account.</p>
                    <a href="/login" class="btn btn-primary">Back to Login</a>
                  </div>
                </div>""")
            except sqlite3.IntegrityError:
                msg = "Username already taken."

    return render_template_string(CSS + """
    <style>body{background:#f0f2f5;} .card{border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,.1);}</style>
    <div class="container mt-5 d-flex justify-content-center">
      <div class="card p-4" style="width:380px">
        <h4 class="mb-3 text-center">Register</h4>
        {% if msg %}<div class="alert alert-danger py-2">{{ msg }}</div>{% endif %}
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


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect('/login')
