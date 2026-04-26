import random
import os
from datetime import datetime
from flask import Blueprint, request, redirect, session, render_template_string, send_file
from database import get_db
from utils.runner import run_code, generate_testcases
from services.pdf_service import generate_result_pdf
from services.email_service import send_result_email, notify_admin_login

exam_bp = Blueprint('exam', __name__)

CSS = '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">'


@exam_bp.route('/quiz', methods=['GET', 'POST'])
def quiz():
    if session.get('role') != 'user':
        return redirect('/login')

    if 'q_list' not in session:
        conn = get_db()
        try:
            qs = conn.execute("SELECT * FROM questions WHERE published=1").fetchall()
        except Exception:
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

    if request.method == 'POST':
        ans = request.form.get('opt', '')
        q   = session['q_list'][session['q_index']]
        if ans.lower() == q['answer'].lower():
            session['score'] += 1
        session['total']   += 1
        session['q_index'] += 1

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

    <div style="background:#1e2a3a;color:#fff;padding:12px 28px;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-weight:600;">MCQ Exam</span>
      <span>Question {{ num }} of {{ tot }}</span>
      <span style="font-size:1.1rem;">&#9201; <span id="timer" style="font-weight:700;color:#ffd200;">10</span>s</span>
    </div>
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
            <button class="btn btn-primary px-4">Next &rarr;</button>
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


@exam_bp.route('/coding', methods=['GET', 'POST'])
def coding():
    if session.get('role') != 'user':
        return redirect('/login')

    if 'c_list' not in session:
        conn = get_db()
        try:
            qs = conn.execute("SELECT * FROM coding_questions WHERE published=1").fetchall()
        except Exception:
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
        session['c_list']       = [dict(q) for q in qs]
        session['c_index']      = 0
        session['coding_score'] = 0
        session['test_results'] = []
        session['all_results']  = []
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
            if ok:
                passed += 1
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

    <div style="background:#1e2a3a;color:#fff;padding:12px 28px;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-weight:600;">Coding Exam — Question {{ cidx }} of {{ ctot }}</span>
      <span>&#9201; <span id="timer" style="font-weight:700;color:#ffd200;"></span></span>
    </div>
    <div class="progress" style="height:6px;border-radius:0;">
      <div class="progress-bar bg-success" style="width:{{ (cidx/ctot*100)|int }}%"></div>
    </div>

    <div class="container mt-3" style="max-width:960px;">
      <div class="row g-3">
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

        <div class="col-md-8">
          <div class="card p-3">
            <form method="post" id="cform">
              <div id="editor" style="height:320px;border-radius:6px;"></div>
              <textarea name="code" id="code_ta" hidden></textarea>
              <div class="mt-2 d-flex gap-2">
                <input name="user_input" class="form-control" placeholder="Custom input (optional)" style="max-width:280px;">
                <button type="button" class="btn btn-warning" onclick="runCode()">Run</button>
                <button type="submit" class="btn btn-success" onclick="sync()">Submit &amp; Next &rarr;</button>
              </div>
            </form>
            <pre id="live_out" class="mt-2 p-2 bg-dark text-white rounded" style="min-height:48px;font-size:.85rem;">{{ output }}</pre>
          </div>
        </div>
      </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/ace/1.32.3/ace.js"></script>
    <script>
    var editor = ace.edit("editor");
    editor.setTheme("ace/theme/monokai");
    editor.session.setMode("ace/mode/python");
    editor.setValue("# Write your Python solution here\\n");
    editor.clearSelection();

    function sync(){ document.getElementById('code_ta').value = editor.getValue(); }

    function runCode(){
      sync();
      fetch('/run_code', {
        method:'POST',
        headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:'code='+encodeURIComponent(editor.getValue())+'&input='+encodeURIComponent(document.querySelector('[name=user_input]').value)
      }).then(r=>r.text()).then(d=>{ document.getElementById('live_out').innerText=d; });
    }

    let secs = 1800;
    const tel = document.getElementById('timer');
    setInterval(()=>{
      secs--;
      let m=Math.floor(secs/60), s=secs%60;
      tel.innerText = m+'m '+String(s).padStart(2,'0')+'s';
      if(secs<=0){ sync(); document.getElementById('cform').submit(); }
    },1000);
    </script>
    """, q=q, cidx=session['c_index'] + 1, ctot=len(session['c_list']),
    test_results=session.get('test_results', []),
    output=session.get('output', ''))


@exam_bp.route('/run_code', methods=['POST'])
def run_code_api():
    return run_code(request.form.get('code', ''), request.form.get('input', ''))


@exam_bp.route('/result')
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

    pdf_path = generate_result_pdf(
        session.get('username'), mcq_score, mcq_total,
        coding_score, session.get('all_results', [])
    )
    session['pdf_path'] = pdf_path

    email = session.get('email')
    if email:
        send_result_email(email, session.get('username'), mcq_score, mcq_total, coding_score, pdf_path)
        notify_admin_login(
            session.get('username'), email, 'user — exam completed',
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    return render_template_string(CSS + """
    <style>body{background:#f0f2f5;}</style>
    <div class="container mt-5" style="max-width:520px;">
      <div class="card p-4 text-center shadow">
        <div style="font-size:3rem;">&#127881;</div>
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


@exam_bp.route('/download_result')
def download_result():
    path = session.get('pdf_path')
    if path and os.path.exists(path):
        return send_file(path, as_attachment=True,
                         download_name=f"result_{session.get('username')}.pdf")
    return redirect('/dashboard')
