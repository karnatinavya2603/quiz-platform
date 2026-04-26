# Quiz Platform

A full-stack web application for conducting online exams with MCQ and coding sections. Built with Python Flask, SQLite, and Bootstrap 5.

---

## How to Run the Project (Step-by-Step)

### Step 1 — Make sure Python 3 is installed

Open your terminal and check:

```bash
python3 --version
```

You should see something like `Python 3.9.6` or higher. If not, download Python from https://www.python.org/downloads/

---

### Step 2 — Go into the project folder

```bash
cd quiz-platform
```

---

### Step 3 — Install required packages

```bash
pip3 install -r requirements.txt
```

This installs:
- `flask` — the web framework
- `reportlab` — for generating PDF result reports

---

### Step 4 — Set your Gmail App Password

The app sends emails using Gmail. You need a **Gmail App Password** (not your regular Gmail password).

**How to get one:**
1. Go to your Google Account → **Security**
2. Enable **2-Step Verification** (if not already on)
3. Go to **App Passwords**
4. Select app: **Mail**, device: **Other** → click **Generate**
5. Copy the 16-character password shown

**Set it in your terminal before running:**

```bash
# macOS / Linux
export GMAIL_APP_PASSWORD="ugmh qngp oyse orpr"

# Windows (Command Prompt)
set GMAIL_APP_PASSWORD=ugmh qngp oyse orpr
```

> If you skip this step the app still runs, but emails will not be sent.

---

### Step 5 — Run the app

```bash
python3 run.py
```

You will see output like:

```
 * Running on http://127.0.0.1:5000
 * Debug mode: on
```

---

### Step 6 — Open in your browser

```
http://127.0.0.1:5000
```

The app opens the login page. The database (`quiz.db`) and all tables are created automatically on first run.

---

### Quick Summary (all commands in one go)

```bash
cd quiz-platform
pip3 install -r requirements.txt
export GMAIL_APP_PASSWORD="ugmh qngp oyse orpr"
python3 run.py
```

Then open: **http://127.0.0.1:5000**

---

### Login as Admin

| Username | Password |
|---|---|
| `navya` | `navya@admin` |

After login you are taken to the **Admin Dashboard** where you can add questions, manage users, and approve registrations.

---

### First Time User Flow

1. A new user goes to `http://127.0.0.1:5000/register` and fills in the form
2. Navya receives an approval email with a green **Approve** button
3. Navya clicks the button — the user is approved instantly
4. The user logs in and can take the exam

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python 3 + Flask | Web framework, routing, session management |
| **Database** | SQLite 3 | Lightweight file-based database (`quiz.db`) |
| **Frontend** | Bootstrap 5 (CDN) | UI components and responsive layout |
| **Email** | Gmail SMTP + Python `smtplib` | Login alerts, approval emails, result emails |
| **PDF** | ReportLab | Generate result PDF reports |
| **Code Editor** | Ace Editor (CDN) | In-browser Python code editor for coding exam |
| **Code Runner** | Python `subprocess` | Execute user-submitted Python code safely |

---

## Project Structure

```
quiz-platform/
├── run.py                   # Entry point — starts the Flask app
├── config.py                # App settings: secret key, DB path, SMTP credentials
├── database.py              # DB connection (get_db) and table setup (init_db)
│
├── routes/
│   ├── auth.py              # /login  /register  /logout
│   ├── admin.py             # /admin  /approve  /add_mcq  /add_coding  /upload  publish/unpublish/delete
│   ├── user.py              # /dashboard  (user home page)
│   └── exam.py              # /quiz  /coding  /result  /run_code  /download_result
│
├── services/
│   ├── email_service.py     # All email sending functions (async threads)
│   └── pdf_service.py       # PDF result report generation
│
├── utils/
│   └── runner.py            # run_code() — executes Python code via subprocess
│                            # generate_testcases() — keyword-based test case generator
│
└── quiz.db                  # SQLite database (auto-created on first run)
```

---

## Prerequisites

Make sure Python 3.8 or higher is installed.

Install required packages:

```bash
pip install flask reportlab
```

---

## How to Run

**Step 1 — Set Gmail App Password (required for email notifications)**

> You must use a Gmail App Password, not your regular Gmail password.
> Go to: Google Account → Security → 2-Step Verification → App Passwords → Generate one.

Set it as an environment variable before running:

```bash
# macOS / Linux
export GMAIL_APP_PASSWORD="your app password here"

# Windows (Command Prompt)
set GMAIL_APP_PASSWORD=your app password here
```

If you skip this step, the app uses the default password in `config.py` directly.

**Step 2 — Start the app**

```bash
python3 run.py
```

**Step 3 — Open in browser**

```
http://127.0.0.1:5000
```

The database (`quiz.db`) and all tables are created automatically on first run. The admin account (Navya) is also pre-created.

---

## Default Admin Account

| Field | Value |
|---|---|
| Username | `navya` |
| Password | `navya@admin` |
| Email | `navyakarnati2603@gmail.com` |
| Role | Admin |

---

## User Roles

### Admin (Navya)
- Logs in at `/login` → redirected to `/admin`
- Sees full dashboard: registered users, quiz progress, login counts
- Approves new user registrations (via email button or admin panel)
- Adds MCQ and coding questions manually or by uploading CSV/JSON
- Publishes / unpublishes / deletes questions
- Receives email alerts on every login and exam completion

### User (e.g. Raghu)
- Registers at `/register` → waits for Navya's approval
- Once approved, logs in at `/login` → redirected to `/dashboard`
- Takes MCQ exam (10 seconds per question, up to 20 questions)
- Takes coding exam (30-minute timer, Ace editor, Python only)
- Receives result email with PDF attachment after completing the exam

---

## Key Features

### One-Click User Approval
When a new user registers, Navya receives an email with a green **Approve** button. Clicking it approves the user instantly — no admin login required. The token is single-use and expires after approval.

### Email Notifications
| Event | Who receives it |
|---|---|
| Any user logs in | Admin (Navya) |
| User logs in | The user themselves (welcome email) |
| New registration | Admin (approve button in email) |
| User account approved | The user (login link in email) |
| Exam completed | User (score summary + PDF attachment) and Admin |

### Question Upload (CSV / JSON)
Both MCQ and coding questions can be bulk-uploaded via CSV or JSON.

**MCQ CSV format** — any of these column names are accepted:

```
question, a / opt1 / option1, b / opt2, c / opt3, d / opt4, answer
```

Example:
```csv
question,a,b,c,d,answer
"What is the output of print(2**3)?","6","8","9","4","b"
```

**Coding CSV format:**
```csv
question,sample_input,sample_output
"Reverse a string","hello","olleh"
```

After uploading, questions are saved as **Draft** by default. You must click **Publish** to make them visible to users.

### MCQ Exam
- Up to 20 questions randomly selected from published questions
- 10-second countdown timer per question — auto-submits on timeout
- Score tracked in session

### Coding Exam
- All published coding questions shown one at a time
- 30-minute global countdown timer — auto-submits when time runs out
- Ace editor (Python mode, Monokai theme)
- **Run** button tests custom input live
- **Submit & Next** runs automated test cases and scores the answer
- Full marks (15 points) awarded only if ALL test cases pass

### PDF Result Report
Generated using ReportLab after exam completion:
- Score summary table (MCQ / Coding / Total)
- Per-question coding test case results (green PASS / red FAIL)
- Saved to `/tmp/result_{username}.pdf`
- Emailed as attachment and available for download at `/download_result`

---

## URL Reference

| URL | Method | Access | Description |
|---|---|---|---|
| `/` | GET | Public | Redirects to `/login` |
| `/login` | GET, POST | Public | Login page |
| `/register` | GET, POST | Public | Registration page |
| `/logout` | GET | Any | Clears session, redirects to login |
| `/dashboard` | GET | User | User home page with exam access |
| `/quiz` | GET, POST | User | MCQ exam |
| `/coding` | GET, POST | User | Coding exam |
| `/run_code` | POST | User | Live code execution (AJAX) |
| `/result` | GET | User | Exam result page |
| `/download_result` | GET | User | Download PDF report |
| `/admin` | GET | Admin | Admin dashboard |
| `/admin/users` | GET | Admin | Redirects to `/admin` |
| `/admin/add_mcq` | GET, POST | Admin | Add / upload / manage MCQ questions |
| `/admin/add_coding` | GET, POST | Admin | Add / upload / manage coding questions |
| `/admin/upload` | GET, POST | Admin | Bulk upload page |
| `/approve/<id>` | GET | Admin | Approve user by ID |
| `/approve_token/<token>` | GET | Public | One-click approval from email |
| `/revoke/<id>` | GET | Admin | Revoke user access |
| `/admin/publish/mcq/<id>` | GET | Admin | Publish single MCQ |
| `/admin/unpublish/mcq/<id>` | GET | Admin | Unpublish single MCQ |
| `/admin/publish/coding/<id>` | GET | Admin | Publish single coding question |
| `/admin/unpublish/coding/<id>` | GET | Admin | Unpublish single coding question |
| `/admin/publish_all/<type>` | GET | Admin | Publish all (`mcq` or `coding`) |
| `/admin/unpublish_all/<type>` | GET | Admin | Unpublish all |
| `/admin/delete_mcq/<id>` | GET | Admin | Delete MCQ question |
| `/admin/delete_coding/<id>` | GET | Admin | Delete coding question |
| `/admin/sample/<kind>` | GET | Admin | Download sample CSV/JSON files |

---

## Database Tables

### `users`
| Column | Type | Description |
|---|---|---|
| id | INTEGER | Primary key |
| username | TEXT | Unique login name |
| email | TEXT | Email address |
| password | TEXT | Plain text password |
| role | TEXT | `admin` or `user` |
| approved | INTEGER | `0` = pending, `1` = approved |
| token | TEXT | One-time approval token (cleared after use) |
| last_login | TEXT | Timestamp of last login |
| login_count | INTEGER | Total number of logins |
| quiz_status | TEXT | `not_started` / `in_progress` / `completed` |
| quiz_score | INTEGER | Final total score |

### `questions` (MCQ)
| Column | Type | Description |
|---|---|---|
| id | INTEGER | Primary key |
| question | TEXT | Question text |
| a, b, c, d | TEXT | Answer options |
| answer | TEXT | Correct option (`a`, `b`, `c`, or `d`) |
| published | INTEGER | `0` = draft, `1` = live |

### `coding_questions`
| Column | Type | Description |
|---|---|---|
| id | INTEGER | Primary key |
| question | TEXT | Problem description |
| sample_input | TEXT | Example input shown to user |
| sample_output | TEXT | Expected output shown to user |
| published | INTEGER | `0` = draft, `1` = live |

---

## Configuration

All configuration is in `config.py`:

```python
SECRET_KEY    = "quiz_secret_2026"          # Flask session secret
DB_FILE       = "quiz.db"                   # SQLite database path
SMTP_SENDER   = "navyakarnati2603@gmail.com" # Gmail address used to send emails
SMTP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "...")  # Gmail App Password
ADMIN_EMAIL   = "navyakarnati2603@gmail.com" # Where admin alerts are sent
```

To change the admin email or sender address, edit `config.py` directly.

---

## Known Limitations

- Passwords are stored in plain text — suitable for internal/test use only
- Code execution runs directly on the host machine via `subprocess` — no sandboxing
- Session-based exam state is lost if the browser is closed mid-exam
- Only Python 3 is supported for the coding exam
