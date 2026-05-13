import random
import os
from datetime import datetime
from flask import Blueprint, request, redirect, session, render_template_string, send_file, jsonify
from database import get_db
from utils.runner import run_code, generate_testcases
from services.pdf_service import generate_result_pdf
from services.email_service import send_result_email, notify_admin_login

exam_bp = Blueprint('exam', __name__)

def is_quiz_locked(conn, quiz_id, username):
    settings = {row['key']: row['value'] for row in conn.execute("SELECT * FROM settings").fetchall()}
    wait_days = int(settings.get('retake_wait_days', 7))
    pass_per = float(settings.get('pass_percentage', 60))

    last_attempt = conn.execute("""
        SELECT attempt_date, percentage FROM user_quiz_attempts 
        WHERE username=? AND quiz_id=? 
        ORDER BY attempt_date DESC LIMIT 1
    """, (username, quiz_id)).fetchone()

    if last_attempt and last_attempt['percentage'] < pass_per:
        last_date = datetime.strptime(last_attempt['attempt_date'], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - last_date).total_seconds() < wait_days * 24 * 3600:
            return True, wait_days
    return False, wait_days

@exam_bp.route('/instructions')
def instructions():
    if session.get('role') != 'user':
        return redirect('/login')
    
    # Clear previous quiz state
    for key in ['q_list', 'c_list', 'q_index', 'c_index', 'score', 'coding_score', 'answered', 'skipped', 'cheated', 'test_results', 'all_results', 'pdf_path']:
        session.pop(key, None)
    
    quiz_id = request.args.get('quiz_id')
    if not quiz_id:
        return redirect('/dashboard')
    
    conn = get_db()
    quiz = conn.execute("""
        SELECT q.*, c.name as cat_name, c.type as cat_type 
        FROM quizzes q 
        JOIN categories c ON q.category_id = c.id 
        WHERE q.id = ?
    """, (quiz_id,)).fetchone()
    
    if not quiz:
        conn.close()
        return redirect('/dashboard')
        
    settings = {row['key']: row['value'] for row in conn.execute("SELECT * FROM settings").fetchall()}
    
    # Check for per-quiz lockout
    locked, wait_days = is_quiz_locked(conn, quiz_id, session['username'])
    if locked:
        conn.close()
        return render_template_string("""
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <div class="container mt-5 text-center">
                <div class="alert alert-warning">
                    <h4>Quiz Locked</h4>
                    <p>try again user after {{ wait_days }} days.</p>
                    <a href="/dashboard" class="btn btn-primary">Back to Dashboard</a>
                </div>
            </div>
        """, wait_days=wait_days)

    if quiz['created_at']:
        expiry_h = int(settings.get('quiz_expiry_hours', 48))
        created = datetime.strptime(quiz['created_at'], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - created).total_seconds() >= expiry_h * 3600:
            conn.close()
            return redirect('/dashboard')
    conn.close()


    title = quiz['name']
    duration = f"{quiz['time_limit']} Minutes" if quiz['time_limit'] > 0 else "Unlimited"
    qtype = quiz['cat_type']
    
    # For mixed quizzes, start with MCQ phase first
    if quiz['cat_type'] == 'mixed':
        next_url = f"/quiz?quiz_id={quiz_id}"
    elif quiz['cat_type'] == 'mcq':
        next_url = f"/quiz?quiz_id={quiz_id}"
    else:
        next_url = f"/coding?quiz_id={quiz_id}"

    return render_template_string("""
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body { background: #f0f2f5; }
      .instruction-card { border-radius: 16px; border: none; box-shadow: 0 10px 30px rgba(0,0,0,0.08); }
      .icon-circle { width: 60px; height: 60px; background: #e8f0fe; color: #0d6efd; 
                     border-radius: 50%; display: flex; align-items: center; justify-content: center;
                     font-size: 1.5rem; margin-bottom: 20px; }
      .rule-item { display: flex; gap: 15px; margin-bottom: 20px; }
      .rule-dot { width: 10px; height: 10px; background: #0d6efd; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }
      .warning-box { background: #fff3cd; border-left: 5px solid #ffc107; padding: 15px; border-radius: 8px; }
    </style>

    <div class="container py-5">
      <div class="row justify-content-center">
        <div class="col-md-8 col-lg-6">
          <div class="card instruction-card p-4 p-md-5">
            <div class="text-center">
              <div class="icon-circle mx-auto">📋</div>
              <h3 class="fw-bold mb-1">Exam Instructions</h3>
              <p class="text-muted mb-4">{{ title }} | Duration: {{ duration }}</p>
            </div>

            <div class="mb-4">
              <div class="rule-item">
                <div class="rule-dot"></div>
                <div>
                  <h6 class="fw-bold mb-1">Proctoring Rules</h6>
                  <p class="text-muted small mb-0">Switching tabs or windows will be detected as cheating and will terminate your exam immediately.</p>
                </div>
              </div>
              
              <div class="rule-item">
                <div class="rule-dot"></div>
                <div>
                  <h6 class="fw-bold mb-1">Navigation Restriction</h6>
                  <p class="text-muted small mb-0">Do not refresh the page or use the browser's back/forward buttons during the exam.</p>
                </div>
              </div>

              <div class="rule-item">
                <div class="rule-dot"></div>
                <div>
                  <h6 class="fw-bold mb-1">Automatic Submission</h6>
                  <p class="text-muted small mb-0">The exam will be automatically submitted once the timer reaches zero.</p>
                </div>
              </div>

              {% if qtype == 'coding' %}
              <div class="rule-item">
                <div class="rule-dot"></div>
                <div>
                  <h6 class="fw-bold mb-1">Coding Requirements</h6>
                  <p class="text-muted small mb-0">Ensure your code passes all provided test cases to receive full marks.</p>
                </div>
              </div>
              {% endif %}

              {% if qtype == 'mixed' %}
              <div class="rule-item">
                <div class="rule-dot"></div>
                <div>
                  <h6 class="fw-bold mb-1">Mixed Assessment</h6>
                  <p class="text-muted small mb-0">This quiz contains both MCQ and Coding questions. You will complete the MCQ section first, then move to the Coding section automatically. One shared timer covers both sections.</p>
                </div>
              </div>
              {% endif %}
            </div>

            <div class="warning-box mb-4">
              <p class="mb-0 small text-dark">
                <strong>Attention:</strong> By clicking the button below, you acknowledge that you have read and understood the rules. The timer will start immediately.
              </p>
            </div>

            <div class="d-grid">
              <a href="{{ next_url }}" class="btn btn-primary btn-lg fw-bold py-3 shadow-sm">
                Start Exam &rarr;
              </a>
              <a href="/dashboard" class="btn btn-link text-muted mt-2 small">Back to Dashboard</a>
            </div>
          </div>
        </div>
      </div>
    </div>
    """, title=title, duration=duration, next_url=next_url, qtype=qtype)


@exam_bp.route('/quiz', methods=['GET', 'POST'])
def quiz():
    if session.get('role') != 'user':
        return redirect('/login')

    quiz_id = request.args.get('quiz_id')
    if not quiz_id and 'quiz_id' not in session:
        return redirect('/dashboard')
    
    if quiz_id:
        session['quiz_id'] = quiz_id

    quiz_id = session['quiz_id']

    conn = get_db()
    locked, wait_days = is_quiz_locked(conn, quiz_id, session['username'])
    if locked:
        conn.close()
        return redirect('/dashboard')
    quiz = conn.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()

    if not quiz:
        conn.close()
        return redirect('/dashboard')

    if quiz['created_at']:
        settings = {row['key']: row['value'] for row in conn.execute("SELECT * FROM settings").fetchall()}
        expiry_h = int(settings.get('quiz_expiry_hours', 48))
        created = datetime.strptime(quiz['created_at'], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - created).total_seconds() >= expiry_h * 3600:
            conn.close()
            return redirect('/dashboard')
    conn.close()

    if 'q_list' not in session:
        conn = get_db()
        cat_type = conn.execute("SELECT c.type FROM quizzes q JOIN categories c ON q.category_id = c.id WHERE q.id=?", (quiz_id,)).fetchone()
        is_mixed = cat_type and cat_type[0] == 'mixed'
        session['is_mixed'] = is_mixed
        
        if is_mixed:
            # For mixed quizzes, only load MCQ topics (question_type='mcq')
            quiz_topics = conn.execute("SELECT * FROM quiz_topics WHERE quiz_id=? AND question_type='mcq'", (quiz_id,)).fetchall()
        else:
            quiz_topics = conn.execute("SELECT * FROM quiz_topics WHERE quiz_id=?", (quiz_id,)).fetchall()
        
        q_ids = []
        if quiz_topics:
            for qt in quiz_topics:
                qs = conn.execute("SELECT id FROM questions WHERE topic_id=? AND published=1", (qt['topic_id'],)).fetchall()
                available_ids = [q['id'] for q in qs if q['id'] not in q_ids]
                if available_ids:
                    count = min(len(available_ids), qt['question_count'])
                    q_ids.extend(random.sample(available_ids, count))
        else:
            qs = conn.execute("SELECT question_id FROM quiz_manual_questions WHERE quiz_id=? AND type='mcq'", (quiz_id,)).fetchall()
            q_ids = [q['question_id'] for q in qs]
            if not q_ids:
                qs = conn.execute("SELECT id FROM questions WHERE published=1").fetchall()
                q_ids = [q['id'] for q in qs]

        conn.close()
        
        if not q_ids:
            if is_mixed:
                # No MCQ questions in mixed quiz, skip directly to coding
                conn.close()
                return redirect(f'/coding?quiz_id={quiz_id}')
            return render_template_string("""
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <div class="container mt-5 d-flex justify-content-center">
              <div class="card p-4 text-center" style="width:400px">
                <h5>No questions available for this quiz</h5>
                <a href="/dashboard" class="btn btn-primary">Back to Dashboard</a>
              </div>
            </div>""")

        if quiz['shuffle_questions']:
            random.shuffle(q_ids)

        session['q_list']  = q_ids
        session['q_index'] = 0
        session['score']   = 0
        session['answered'] = 0
        session['skipped']  = 0
        limit = quiz['time_limit'] if quiz['time_limit'] > 0 else 10
        session['mcq_end_time'] = datetime.now().timestamp() + (limit * 60)
        
        with get_db() as conn:
            conn.execute("UPDATE users SET quiz_status='in_progress' WHERE username=?", (session['username'],))
            conn.commit()

    now = datetime.now().timestamp()
    if session.get('mcq_end_time') and now > session['mcq_end_time']:
        if session.get('is_mixed'):
            return redirect(f'/coding?quiz_id={session["quiz_id"]}')
        return redirect('/result')

    if session.get('q_index', 0) >= len(session.get('q_list', [])):
        if session.get('is_mixed'):
            return redirect(f'/coding?quiz_id={session["quiz_id"]}')
        return redirect('/result')

    if request.method == 'POST':
        action = request.form.get('action', 'next')
        q_id = session['q_list'][session['q_index']]
        
        mcq_answers = session.get('mcq_answers', {})
        mcq_points = session.get('mcq_points', {})
        
        if action in ['next', 'submit', 'previous']:
            ans = request.form.get('opt', '').lower()
            if ans:
                with get_db() as conn:
                    q = dict(conn.execute("SELECT * FROM questions WHERE id=?", (q_id,)).fetchone())
                    quiz_data = conn.execute("SELECT positive_marks, negative_marks FROM quizzes WHERE id=?", (session['quiz_id'],)).fetchone()
                
                expected_ans = str(q['answer']).lower().strip()
                selected_text = str(q.get(ans, '')).lower().strip()
                
                if ans == expected_ans or selected_text == expected_ans:
                    points = quiz_data['positive_marks']
                else:
                    points = -quiz_data['negative_marks']
                    
                mcq_answers[str(q_id)] = ans
                mcq_points[str(q_id)] = points
                
        session['mcq_answers'] = mcq_answers
        session['mcq_points'] = mcq_points
        
        if action == 'previous':
            session['q_index'] = max(0, session['q_index'] - 1)
        else:
            session['q_index'] += 1
            
        session['score'] = sum(session.get('mcq_points', {}).values())
        session['answered'] = len(session.get('mcq_answers', {}))

    if session['q_index'] >= len(session['q_list']):
        if session.get('is_mixed'):
            return redirect(f'/coding?quiz_id={session["quiz_id"]}')
        return redirect('/result')

    q_id = session['q_list'][session['q_index']]
    with get_db() as conn:
        q = dict(conn.execute("SELECT * FROM questions WHERE id=?", (q_id,)).fetchone())
        
    num = session['q_index'] + 1
    tot = len(session['q_list'])
    rem_time = max(0, int(session['mcq_end_time'] - datetime.now().timestamp()))

    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Assessment Pro - MCQ</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --primary: #4f46e5;
                --bg: #f8fafc;
                --text: #1e293b;
            }
            body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; }
            .header-bar { background: #1e293b; color: #fff; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
            .timer-badge { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); padding: 0.5rem 1.25rem; border-radius: 8px; font-weight: 700; font-family: monospace; font-size: 1.1rem; }
            .progress-container { height: 6px; background: #e2e8f0; }
            .progress-fill { height: 100%; background: var(--primary); transition: width 0.4s ease; }
            .quiz-card { background: #fff; border-radius: 16px; border: 1px solid #e2e8f0; padding: 2.5rem; margin-top: 2rem; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
            .question-text { font-size: 1.25rem; font-weight: 600; line-height: 1.6; margin-bottom: 2rem; white-space: pre-wrap; word-wrap: break-word; color: #0f172a; }
            .option-item { margin-bottom: 1rem; position: relative; }
            .option-input { display: none; }
            .option-label { 
                display: flex; 
                align-items: center; 
                padding: 1.25rem 1.5rem; 
                background: #fff; 
                border: 2px solid #e2e8f0; 
                border-radius: 12px; 
                cursor: pointer; 
                transition: all 0.2s ease;
                font-weight: 500;
                position: relative;
                min-height: 64px;
            }
            .option-content {
                flex: 1;
                white-space: pre-wrap;
                word-break: break-word;
            }
            .option-label:hover { border-color: var(--primary); background: #f5f3ff; }
            .option-input:checked + .option-label { border-color: var(--primary); background: #eef2ff; color: var(--primary); box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.1); }
            .option-prefix { 
                width: 32px; 
                height: 32px; 
                background: #f1f5f9; 
                border-radius: 8px; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                margin-right: 1rem; 
                font-weight: 700; 
                font-size: 0.85rem;
                flex-shrink: 0;
                transition: all 0.2s ease;
            }
            .option-input:checked + .option-label .option-prefix { background: var(--primary); color: #fff; }
            .nav-btn { padding: 0.75rem 2rem; border-radius: 10px; font-weight: 700; transition: all 0.2s ease; }
            .btn-next { background: var(--primary); color: #fff; border: none; }
            .btn-next:hover { background: #4338ca; transform: translateY(-1px); }
            .btn-prev { background: #fff; border: 1px solid #cbd5e1; color: #64748b; }
            .btn-prev:hover { background: #f8fafc; }
            .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
            .dot-answered { background: #22c55e; }
            .dot-pending { background: #e2e8f0; }
        </style>
    </head>
    <body>

    <div class="header-bar">
        <div class="d-flex align-items-center gap-3">
            <span class="fw-bold fs-5">MCQ Assessment</span>
            <div class="vr mx-2 opacity-20" style="height: 20px;"></div>
            <div class="small opacity-75">
                <span class="me-3"><span class="status-dot dot-answered"></span>{{ answered }} Answered</span>
                <span>Question {{ num }} of {{ tot }}</span>
            </div>
        </div>
        <div class="timer-badge" id="timer-display">--:--</div>
    </div>
    
    <div class="progress-container">
        <div class="progress-fill" style="width: {{ (num/tot*100)|int }}%"></div>
    </div>

    <div class="container" style="max-width: 800px;">
        <div class="quiz-card">
            <div class="question-text">{{ q['question'] }}</div>
            
            <form method="post" id="quiz-form">
                <div class="option-item">
                    <input type="radio" name="opt" value="a" id="opt-a" class="option-input" {% if saved_ans == 'a' %}checked{% endif %}>
                    <label for="opt-a" class="option-label">
                        <div class="option-prefix">A</div>
                        <div class="option-content">{{ q['a'] }}</div>
                    </label>
                </div>
                <div class="option-item">
                    <input type="radio" name="opt" value="b" id="opt-b" class="option-input" {% if saved_ans == 'b' %}checked{% endif %}>
                    <label for="opt-b" class="option-label">
                        <div class="option-prefix">B</div>
                        <div class="option-content">{{ q['b'] }}</div>
                    </label>
                </div>
                <div class="option-item">
                    <input type="radio" name="opt" value="c" id="opt-c" class="option-input" {% if saved_ans == 'c' %}checked{% endif %}>
                    <label for="opt-c" class="option-label">
                        <div class="option-prefix">C</div>
                        <div class="option-content">{{ q['c'] }}</div>
                    </label>
                </div>
                <div class="option-item">
                    <input type="radio" name="opt" value="d" id="opt-d" class="option-input" {% if saved_ans == 'd' %}checked{% endif %}>
                    <label for="opt-d" class="option-label">
                        <div class="option-prefix">D</div>
                        <div class="option-content">{{ q['d'] }}</div>
                    </label>
                </div>

                <div class="d-flex justify-content-between align-items-center mt-5">
                    <div class="text-muted small fw-bold">PROGRESS: {{ num }} / {{ tot }}</div>
                    <div class="d-flex gap-2">
                        {% if num > 1 %}
                        <button type="submit" name="action" value="previous" class="nav-btn btn-prev">Previous</button>
                        {% endif %}
                        <button type="submit" name="action" value="skip" class="nav-btn btn-prev">Skip</button>
                        <button type="submit" name="action" value="next" class="nav-btn btn-next">
                            {% if num == tot %}Finish Exam{% else %}Submit & Next{% endif %}
                        </button>
                    </div>
                </div>
            </form>
        </div>
        <p class="text-center mt-4 text-muted small">ID: Q-{{ q['id'] }} | Secured Assessment Environment</p>
    </div>

    <script>
        let timeLeft = {{ rem_time }};
        const timerEl = document.getElementById('timer-display');
        
        function updateTimer() {
            const m = Math.floor(timeLeft / 60);
            const s = timeLeft % 60;
            timerEl.innerText = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
            if (timeLeft <= 60) timerEl.style.color = '#ef4444';
        }

        updateTimer();
        const timerIv = setInterval(() => {
            timeLeft--;
            if (timeLeft <= 0) {
                clearInterval(timerIv);
                document.getElementById('quiz-form').submit();
            }
            updateTimer();
        }, 1000);

        // Proctoring
        document.addEventListener('visibilitychange', () => { if(document.hidden) terminate(); });
        window.onblur = () => terminate();
        
        function terminate() {
            alert("Security Breach: Activity outside exam window detected. Terminating session.");
            window.location.href = "/terminate_exam";
        }
    </script>
    </body>
    </html>
    """
    saved_ans = session.get('mcq_answers', {}).get(str(q_id), '')
    return render_template_string(html, q=q, num=num, tot=tot, score=session.get('score', 0), 
                                  answered=session.get('answered', 0), skipped=session.get('skipped', 0), rem_time=rem_time, saved_ans=saved_ans)
    saved_ans = session.get('mcq_answers', {}).get(str(q_id), '')
    return render_template_string(html, q=q, num=num, tot=tot, score=session.get('score', 0), 
                                  answered=session.get('answered', 0), skipped=session.get('skipped', 0), rem_time=rem_time, saved_ans=saved_ans)


@exam_bp.route('/coding', methods=['GET', 'POST'])
def coding():
    if session.get('role') != 'user':
        return redirect('/login')

    quiz_id = request.args.get('quiz_id')
    if not quiz_id and 'quiz_id' not in session:
        return redirect('/dashboard')
    
    if quiz_id:
        session['quiz_id'] = quiz_id

    quiz_id = session['quiz_id']

    conn = get_db()
    locked, wait_days = is_quiz_locked(conn, quiz_id, session['username'])
    if locked:
        conn.close()
        return redirect('/dashboard')
    quiz = conn.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()

    if not quiz:
        conn.close()
        return redirect('/dashboard')

    if quiz['created_at']:
        settings = {row['key']: row['value'] for row in conn.execute("SELECT * FROM settings").fetchall()}
        expiry_h = int(settings.get('quiz_expiry_hours', 48))
        created = datetime.strptime(quiz['created_at'], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - created).total_seconds() >= expiry_h * 3600:
            conn.close()
            return redirect('/dashboard')
    conn.close()

    if 'c_list' not in session:
        conn = get_db()
        is_mixed = session.get('is_mixed', False)
        
        if is_mixed:
            # For mixed quizzes, only load coding topics (question_type='coding')
            quiz_topics = conn.execute("SELECT * FROM quiz_topics WHERE quiz_id=? AND question_type='coding'", (quiz_id,)).fetchall()
        else:
            quiz_topics = conn.execute("SELECT * FROM quiz_topics WHERE quiz_id=?", (quiz_id,)).fetchall()
        
        c_ids = []
        if quiz_topics:
            for qt in quiz_topics:
                qs = conn.execute("SELECT id FROM coding_questions WHERE topic_id=? AND published=1", (qt['topic_id'],)).fetchall()
                available_ids = [q['id'] for q in qs if q['id'] not in c_ids]
                if available_ids:
                    count = min(len(available_ids), qt['question_count'])
                    c_ids.extend(random.sample(available_ids, count))
        else:
            qs = conn.execute("SELECT question_id FROM quiz_manual_questions WHERE quiz_id=? AND type='coding'", (quiz_id,)).fetchall()
            c_ids = [q['question_id'] for q in qs]
            if not c_ids:
                qs = conn.execute("SELECT id FROM coding_questions WHERE published=1").fetchall()
                c_ids = [q['id'] for q in qs]

        conn.close()
        
        if not c_ids:
            if session.get('is_mixed'):
                # No coding questions in mixed quiz, go to result
                return redirect('/result')
            return render_template_string("""
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <div class="container mt-5 d-flex justify-content-center">
              <div class="card p-4 text-center" style="width:400px">
                <h5>No coding questions available for this quiz</h5>
                <a href="/dashboard" class="btn btn-primary">Back to Dashboard</a>
              </div>
            </div>""")

        session['c_list']       = c_ids
        session['c_index']      = 0
        session['coding_score'] = 0
        session['test_results'] = []
        session['all_results']  = []
        session.setdefault('score', 0)
        
        if session.get('is_mixed') and session.get('mcq_end_time'):
            # For mixed quizzes, reuse the shared timer from MCQ phase
            session['coding_end_time'] = session['mcq_end_time']
        else:
            limit = quiz['time_limit'] if quiz['time_limit'] > 0 else 30
            session['coding_end_time'] = datetime.now().timestamp() + (limit * 60)

    if session.get('c_index', 0) >= len(session.get('c_list', [])):
        return redirect('/result')

    if request.method == 'POST':
        action = request.form.get('action', 'submit')
        c_id = session['c_list'][session['c_index']]
        code = request.form.get('code', '')
        user_input = request.form.get('user_input', '')
        
        coding_points = session.get('coding_points', {})
        coding_drafts = session.get('coding_drafts', {})
        all_results_dict = session.get('all_results_dict', {})
        
        if action in ['submit', 'next', 'previous']:
            coding_drafts[str(c_id)] = code
            if code.strip():
                with get_db() as conn:
                    q = dict(conn.execute("SELECT * FROM coding_questions WHERE id=?", (c_id,)).fetchone())
                    quiz_data = conn.execute("SELECT positive_marks FROM quizzes WHERE id=?", (session['quiz_id'],)).fetchone()
                    points_max = quiz_data['positive_marks'] if quiz_data else 15
        
                tests   = generate_testcases(q['question'])
                results = []
                passed  = 0
                for inp, expected in tests:
                    output = run_code(code, inp)
                    ok     = output.strip() == expected.strip()
                    if ok: passed += 1
                    results.append({'input': inp, 'expected': expected, 'output': output, 'status': 'PASS' if ok else 'FAIL'})
        
                if passed == len(tests) and len(tests) > 0:
                    coding_points[str(c_id)] = points_max
                else:
                    coding_points[str(c_id)] = 0
                    
                session['test_results'] = results
                all_results_dict[str(c_id)] = {'question': q['question'], 'results': results}
                session['output']  = run_code(code, user_input)

        session['coding_drafts'] = coding_drafts
        session['coding_points'] = coding_points
        session['all_results_dict'] = all_results_dict
        session['coding_score'] = sum(coding_points.values())
        session['all_results'] = list(all_results_dict.values())

        if action == 'previous':
            session['c_index'] = max(0, session['c_index'] - 1)
        else:
            session['c_index'] += 1

    if session['c_index'] >= len(session['c_list']):
        return redirect('/result')

    c_id = session['c_list'][session['c_index']]
    with get_db() as conn:
        q = dict(conn.execute("SELECT * FROM coding_questions WHERE id=?", (c_id,)).fetchone())

    rem_time = max(0, int(session['coding_end_time'] - datetime.now().timestamp()))
    saved_code = session.get('coding_drafts', {}).get(str(c_id), '')

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Assessment Pro IDE</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
        <style>
            :root {
                --primary: #4f46e5;
                --bg-main: #0f172a;
                --bg-card: #1e293b;
                --border: #334155;
                --success: #22c55e;
                --danger: #ef4444;
            }
            body { background: var(--bg-main); color: #f8fafc; font-family: 'Inter', sans-serif; height: 100vh; margin: 0; display: flex; flex-direction: column; overflow: hidden; }
            .top-nav { background: #1e293b; border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem; display: flex; justify-content: space-between; align-items: center; }
            .main-content { display: flex; flex: 1; overflow: hidden; }
            .question-panel { width: 420px; min-width: 420px; background: var(--bg-card); border-right: 1px solid var(--border); padding: 1.5rem; overflow-y: auto; }
            .editor-panel { flex: 1; display: flex; flex-direction: column; background: #000000; }
            .editor-header { background: #1e293b; padding: 0.75rem 1.25rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); }
            #editor { flex: 1; width: 100%; border: none; }
            .bottom-panel { height: 380px; background: #0f172a; border-top: 1px solid var(--border); display: flex; flex-direction: column; }
            .panel-tabs { background: #1e293b; display: flex; }
            .tab { padding: 0.8rem 1.5rem; cursor: pointer; border-bottom: 3px solid transparent; color: #64748b; font-size: 0.8rem; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }
            .tab.active { color: #fff; border-bottom-color: var(--primary); background: rgba(79, 70, 229, 0.1); }
            .panel-content { flex: 1; overflow-y: auto; padding: 1.5rem; background: #020617; }
            .console-out { font-family: 'Fira Code', monospace; font-size: 1rem; color: #e2e8f0; margin: 0; line-height: 1.6; }
            .test-case { background: #1e293b; border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem; }
            .test-case.pass { border-left: 6px solid var(--success); }
            .test-case.fail { border-left: 6px solid var(--danger); }
            .btn-check-main { background: var(--success); color: white; border: none; padding: 0.6rem 2rem; border-radius: 8px; font-weight: 800; display: flex; align-items: center; gap: 0.8rem; transition: 0.2s; box-shadow: 0 4px 15px rgba(34, 197, 94, 0.3); }
            .btn-check-main:hover { transform: translateY(-2px); filter: brightness(1.1); }
            .python-big-badge { background: #ffd43b; color: #306998; padding: 0.5rem 1.25rem; border-radius: 8px; font-weight: 900; font-size: 0.9rem; display: inline-flex; align-items: center; gap: 0.6rem; border: 2px solid #306998; }
            .summary-card { background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem; display: flex; justify-content: space-around; text-align: center; }
            .summary-item h1 { margin: 0; font-size: 2.5rem; font-weight: 900; }
            .summary-item span { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; font-weight: 800; }
            .sample-status-badge { padding: 0.5rem 1rem; border-radius: 6px; font-weight: 800; font-size: 0.8rem; display: inline-block; margin-top: 1rem; }
            .sample-pass { background: rgba(34, 197, 94, 0.2); color: #22c55e; border: 1px solid #22c55e; }
            .sample-fail { background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
        </style>
    </head>
    <body>

    <nav class="top-nav">
        <div class="d-flex align-items-center gap-3">
            <span class="fw-bold fs-4">QUIZ<span class="text-primary">PLATFORM</span></span>
            <span class="badge bg-primary bg-opacity-20 text-primary border border-primary border-opacity-30">PYTHON ASSESSMENT</span>
        </div>
        <div class="d-flex align-items-center gap-4">
            <div id="timer-display" class="fs-5 fw-bold text-warning font-monospace">--:--</div>
            <div class="d-flex gap-2">
                <button class="btn btn-outline-light btn-sm fw-bold px-3" onclick="navigate('previous')">Previous</button>
                <button class="btn btn-primary btn-sm fw-bold px-4" onclick="navigate('next')">
                    {% if cidx == ctot %}Finish Exam{% else %}Submit & Next{% endif %}
                </button>
            </div>
        </div>
    </nav>

    <div class="main-content">
        <div class="question-panel">
            <div class="mb-4">
                <span class="text-primary small fw-bold text-uppercase">Question {{ cidx }} of {{ ctot }}</span>
                <h3 class="mt-2 fw-bold">{{ q['question'] }}</h3>
            </div>
            
            <div class="mb-4">
                <label class="text-muted small fw-bold text-uppercase mb-2 d-block">Sample Input</label>
                <div class="bg-black p-3 rounded border border-secondary border-opacity-20 position-relative">
                    <pre class="m-0 text-success fw-bold"><code id="sample-input-text">{{ q['sample_input'] }}</code></pre>
                    <button class="btn btn-xs btn-outline-secondary position-absolute top-0 end-0 m-2" onclick="copyToInput({{ q['sample_input']|tojson }})">COPY</button>
                </div>
            </div>
            
            <div class="mb-4">
                <label class="text-muted small fw-bold text-uppercase mb-2 d-block">Expected Output</label>
                <div class="bg-black p-3 rounded border border-secondary border-opacity-20">
                    <pre class="m-0 text-info fw-bold"><code id="sample-output-text">{{ q['sample_output'] }}</code></pre>
                </div>
            </div>
        </div>

        <div class="editor-panel">
            <div class="editor-header">
                <div class="d-flex align-items-center gap-3">
                    <div class="python-big-badge">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M14.25.18l.9.2.73.26.59.33.45.38.34.44.25.51.15.58.08.64.03.71v6.92l-.02.39-.06.39-.1.38-.14.38-.19.34-.23.32-.26.26-.3.23-.33.17-.35.13-.37.07-.4.02H6.15l-.41-.02-.4-.08-.4-.15-.35-.2-.3-.27-.24-.32-.18-.38-.11-.42-.05-.44-.01-.48V8.92l.01-.48.05-.44.11-.42.18-.38.24-.32.3-.27.35-.2.4-.15.4-.08.41-.02H10.61v3.31h3.32V1.5c0-.13-.02-.26-.05-.39l-.1-.38-.14-.38-.19-.34-.23-.32-.26-.26-.3-.23-.33-.17-.35-.13-.37-.07L10.75.03l-.4-.02H6.15L5.73.03l-.42.07-.41.13-.38.19-.34.25-.3.31-.23.36-.17.41-.1.46-.04.5V4.6c0 .13.02.26.05.39l.1.38.14.38.19.34.23.32.26.26.3.23.33.17.35.13.37.07.39.02h7.35l.41-.02.4-.08.4-.15.35-.2.3-.27.24-.32.18-.38.11-.42.05-.44.01-.48V1.5c0-.13-.02-.26-.05-.39l-.1-.38-.14-.38-.19-.34-.23-.32-.26-.26-.3-.23-.33-.17-.35-.13-.37-.07-.39-.02H10.75l-.41.02z"/></svg>
                        PYTHON 3
                    </div>
                    <span id="save-status" class="text-muted small fw-bold">IDLE: READY</span>
                </div>
                <button class="btn btn-check-main" onclick="checkAllTestCases()">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    Check All TestCases
                </button>
            </div>

            <div id="editor"></div>

            <div class="bottom-panel">
                <div class="panel-tabs">
                    <div class="tab active" data-tab="custom">1. Try Sample</div>
                    <div class="tab" data-tab="console">2. Execution Console</div>
                    <div class="tab" data-tab="tests">3. Final Test Results</div>
                </div>

                <div class="panel-content" id="tab-custom">
                    <div class="mb-2 d-flex justify-content-between align-items-center">
                        <label class="text-muted small fw-bold text-uppercase">Enter Custom Input</label>
                        <button class="btn btn-xs btn-outline-primary" onclick="copyToInput(document.getElementById('sample-input-text').innerText)">Load Sample Input</button>
                    </div>
                    <textarea id="custom-stdin" class="form-control bg-black border-secondary text-white font-monospace p-3 flex-grow-1 mb-3" style="font-size: 1.1rem; border-radius: 12px; min-height: 120px;" placeholder="Paste sample input here to test your logic..."></textarea>
                    <button class="btn btn-primary w-100 py-3 fw-bold fs-5" onclick="runCustomCode()">Run & Compare with Sample</button>
                    <div id="sample-result-area" class="text-center"></div>
                </div>

                <div class="panel-content d-none" id="tab-console">
                    <pre class="console-out" id="terminal-out">Terminal output will appear here.</pre>
                </div>

                <div class="panel-content d-none" id="tab-tests">
                    <div id="test-summary-card" class="summary-card d-none">
                        <div class="summary-item"><h1 class="text-success" id="passed-count">0</h1><span>Passed</span></div>
                        <div class="summary-item"><h1 class="text-danger" id="failed-count">0</h1><span>Failed</span></div>
                    </div>
                    <div id="test-case-list">
                        <div class="text-center text-muted py-5">
                            <p class="mb-2">Run all test cases after you've verified the sample.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <form id="nav-form" method="POST" class="hidden-form">
        <input type="hidden" name="code" id="hidden-code">
        <input type="hidden" name="action" id="hidden-action">
    </form>

    <script src="https://cdn.jsdelivr.net/npm/ace-builds@1.32.3/src-min-noconflict/ace.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/ace-builds@1.32.3/src-min-noconflict/ext-language_tools.js"></script>
    <script>
        let editor;
        const q_id = "{{ q['id'] }}";
        const rem_time = parseInt("{{ rem_time }}") || 0;

        window.onload = function() {
            if (typeof ace === 'undefined') { alert("Editor Error. Refresh page."); return; }
            editor = ace.edit("editor");
            ace.require("ace/ext/language_tools");
            editor.setTheme("ace/theme/tomorrow_night_eighties");
            editor.session.setMode("ace/mode/python");
            editor.setOptions({
                fontSize: "16px",
                enableBasicAutocompletion: true,
                enableLiveAutocompletion: true,
                showPrintMargin: false,
                useSoftTabs: true,
                tabSize: 4,
                wrap: true
            });
            const saved = {{ saved_code|tojson|safe }};
            editor.setValue(saved || "# Solution\\n", -1);
            editor.focus();

            document.querySelectorAll('.tab').forEach(t => {
                t.onclick = () => {
                    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
                    t.classList.add('active');
                    document.querySelectorAll('.panel-content').forEach(p => p.classList.add('d-none'));
                    document.getElementById(`tab-${t.dataset.tab}`).classList.remove('d-none');
                };
            });

            let t = rem_time;
            const iv = setInterval(() => {
                if (t <= 0) { clearInterval(iv); navigate('next'); return; }
                t--;
                document.getElementById('timer-display').innerText = `${Math.floor(t/60)}:${(t%60).toString().padStart(2,'0')}`;
            }, 1000);

            document.addEventListener('visibilitychange', () => { if(document.hidden) terminate(); });
            window.onblur = () => terminate();
        };

        function copyToInput(val) {
            document.getElementById('custom-stdin').value = val;
            document.querySelector('[data-tab="custom"]').click();
        }

        function runCustomCode() {
            const code = editor.getValue();
            const input = document.getElementById('custom-stdin').value;
            const term = document.getElementById('terminal-out');
            const resultArea = document.getElementById('sample-result-area');
            
            resultArea.innerHTML = '<div class="spinner-border text-primary mt-3"></div>';
            document.getElementById('save-status').innerText = 'IDLE: RUNNING...';

            const fd = new FormData();
            fd.append('code', code);
            fd.append('input', input);

            fetch('/run_code', { method: 'POST', body: fd })
            .then(r => r.text())
            .then(out => {
                document.getElementById('save-status').innerText = 'IDLE: READY';
                term.innerText = out || '[No Output]';
                
                const expected = document.getElementById('sample-output-text').innerText.trim();
                const actual = (out || "").trim();
                
                if (actual === expected && expected !== "") {
                    resultArea.innerHTML = '<div class="sample-status-badge sample-pass">✓ SAMPLE OUTPUT MATCHED</div>';
                } else if (expected !== "") {
                    resultArea.innerHTML = '<div class="sample-status-badge sample-fail">✗ SAMPLE MISMATCH (Check Console)</div>';
                } else {
                    resultArea.innerHTML = '';
                }
            })
            .catch(e => {
                resultArea.innerHTML = '<div class="text-danger mt-2">Error: ' + e.message + '</div>';
            });
        }

        function checkAllTestCases() {
            const code = editor.getValue();
            if(!code.trim()) { alert("Code area is empty!"); return; }

            document.getElementById('save-status').innerText = 'IDLE: TESTING...';
            document.querySelector('[data-tab="tests"]').click();
            document.getElementById('test-case-list').innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary"></div><p class="mt-3">Validating against all hidden test cases...</p></div>';

            const formData = new FormData();
            formData.append('code', code);
            formData.append('c_id', q_id);

            fetch('/run_all_tests', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                document.getElementById('save-status').innerText = 'IDLE: READY';
                document.getElementById('test-summary-card').classList.remove('d-none');
                document.getElementById('passed-count').innerText = data.passed;
                document.getElementById('failed-count').innerText = data.total - data.passed;
                
                document.getElementById('test-summary').innerText = `(${data.passed}/${data.total})`;
                document.getElementById('test-summary').className = 'ms-1 small ' + (data.all_passed ? 'text-success' : 'text-danger');

                document.getElementById('test-case-list').innerHTML = data.results.map((r, i) => `
                    <div class="test-case ${r.status.toLowerCase()}">
                        <div class="d-flex justify-content-between mb-2">
                            <span class="fw-bold">Hidden Case #${i+1}</span>
                            <span class="badge ${r.status === 'PASS' ? 'bg-success' : 'bg-danger'}">${r.status}</span>
                        </div>
                        <div class="row g-2 small">
                            <div class="col-4">Input: <code>${r.input}</code></div>
                            <div class="col-4">Expected: <code>${r.expected}</code></div>
                            <div class="col-4">Output: <code>${r.output}</code></div>
                        </div>
                    </div>
                `).join('');
            });
        }

        function navigate(act) {
            document.getElementById('hidden-code').value = editor.getValue();
            document.getElementById('hidden-action').value = act;
            document.getElementById('nav-form').submit();
        }

        function terminate() {
            alert("Security Breach: Tab switching detected. Exam Terminated.");
            window.location.href = "/terminate_exam";
        }
    </script>
    </body>
    </html>
    """, q=q, cidx=session['c_index'] + 1, ctot=len(session['c_list']), test_results=session.get('test_results', []), output=session.get('output', ''), rem_time=rem_time, saved_code=saved_code)


@exam_bp.route('/run_code', methods=['POST'])
def run_code_api():
    return run_code(request.form.get('code', ''), request.form.get('input', ''))

@exam_bp.route('/run_all_tests', methods=['POST'])
def run_all_tests():
    if session.get('role') != 'user':
        return jsonify({'error': 'Unauthorized'}), 401
    
    code = request.form.get('code', '')
    c_id = request.form.get('c_id')
    
    if not code or not c_id:
        return jsonify({'error': 'Missing parameters'}), 400
        
    conn = get_db()
    q = conn.execute("SELECT * FROM coding_questions WHERE id=?", (c_id,)).fetchone()
    conn.close()
    
    if not q:
        return jsonify({'error': 'Question not found'}), 404
        
    tests = generate_testcases(q['question'])
    results = []
    passed = 0
    for inp, expected in tests:
        output = run_code(code, inp)
        ok = output.strip() == expected.strip()
        if ok: passed += 1
        results.append({
            'input': inp, 
            'expected': expected, 
            'output': output, 
            'status': 'PASS' if ok else 'FAIL'
        })
        
    return jsonify({
        'results': results,
        'passed': passed,
        'total': len(tests),
        'all_passed': passed == len(tests) and len(tests) > 0
    })

@exam_bp.route('/terminate_exam')
def terminate_exam():
    if session.get('role') != 'user': return redirect('/login')
    session['cheated'] = True
    return redirect('/result')

@exam_bp.route('/result')
def result():
    if session.get('role') != 'user': return redirect('/login')
    
    # Calculate scores from points dictionary instead of naive counter
    mcq_score = sum(session.get('mcq_points', {}).values())
    coding_score = sum(session.get('coding_points', {}).values())
    total_score = mcq_score + coding_score
    
    # Calculate Max Score for percentage
    max_mcq = 0
    max_coding = 0
    with get_db() as conn:
        quiz = conn.execute("SELECT * FROM quizzes WHERE id=?", (session.get('quiz_id'),)).fetchone()
        if quiz:
            pos_marks = quiz['positive_marks']
            max_mcq = len(session.get('q_list', [])) * pos_marks
            max_coding = len(session.get('c_list', [])) * pos_marks
    
    max_total = max_mcq + max_coding
    percentage = (total_score / max_total * 100) if max_total > 0 else 0
    
    with get_db() as conn:
        settings = {row['key']: row['value'] for row in conn.execute("SELECT * FROM settings").fetchall()}
        pass_per = float(settings.get('pass_percentage', 60))
        wait_days = int(settings.get('retake_wait_days', 7))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        conn.execute("""
            UPDATE users 
            SET quiz_status='completed', quiz_score=?, quiz_percentage=?, last_quiz_date=? 
            WHERE username=?
        """, (total_score, percentage, now, session['username']))
        
        # Track per-quiz attempt
        quiz_id = session.get('quiz_id')
        if quiz_id:
            conn.execute("""
                INSERT INTO user_quiz_attempts (username, quiz_id, score, percentage, status, attempt_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session['username'], quiz_id, total_score, percentage, 'completed', now))
            
        conn.commit()
    pdf_path = generate_result_pdf(session.get('username'), mcq_score, max_mcq, coding_score, session.get('all_results', []))
    session['pdf_path'] = pdf_path
    email = session.get('email')
    if email:
        send_result_email(email, session.get('username'), mcq_score, max_mcq, coding_score, pdf_path)
        notify_admin_login(session.get('username'), email, 'user — exam completed', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return render_template_string("""
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>body{background:#f0f2f5;}</style>
    <div class="container mt-5" style="max-width:520px;">
      <div class="card p-4 text-center shadow">
        <div style="font-size:3rem;">{% if cheated %}&#9888;{% else %}&#127881;{% endif %}</div>
        <h3 class="mt-2">
          {% if cheated %}Exam Terminated!
          {% elif percentage >= pass_per %}Well done! You passed!
          {% else %}You failed the exam.
          {% endif %}
        </h3>
        {% if cheated %}
          <div class="alert alert-danger"><b>Warning:</b> Your exam was terminated because you switched tabs or left the browser window.</div>
        {% elif percentage < pass_per %}
          <div class="alert alert-warning"><b>Retake Policy:</b> try again user after <b>{{ wait_days }} days</b>.</div>
        {% else %}
          <div class="alert alert-success">Congratulations! You have successfully passed the assessment.</div>
        {% endif %}
        <p class="text-muted">{% if cheated %}Submission recorded for <b>{{ username }}</b>.{% else %}Result recorded for <b>{{ username }}</b>.{% endif %}</p>
        <hr>
        <div class="row g-3 mt-1">
          <div class="col-4"><div class="p-3 bg-light rounded"><h4 class="text-primary mb-0">{{ mcq_score }} / {{ max_mcq }}</h4><small class="text-muted">MCQ Score</small></div></div>
          <div class="col-4"><div class="p-3 bg-light rounded"><h4 class="text-success mb-0">{{ coding_score }} / {{ max_coding }}</h4><small class="text-muted">Coding Score</small></div></div>
          <div class="col-4"><div class="p-3 rounded" style="background:#667eea;color:#fff;"><h4 class="mb-0">{{ total_score }} / {{ max_total }}</h4><small>Total Score</small></div></div>
        </div>
        <a href="/download_result" class="btn btn-success mt-2 w-100">Download PDF Report</a>
        <a href="/dashboard" class="btn btn-outline-primary mt-2 w-100">Back to Dashboard</a>
      </div>
    </div>
    """, username=session.get('username'), mcq_score=mcq_score, max_mcq=max_mcq, coding_score=coding_score, max_coding=max_coding, total_score=total_score, max_total=max_total, percentage=percentage, pass_per=pass_per, wait_days=wait_days, cheated=session.get('cheated'))

@exam_bp.route('/download_result')
def download_result():
    path = session.get('pdf_path')
    if path and os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=f"result_{session.get('username')}.pdf")
    return redirect('/dashboard')
