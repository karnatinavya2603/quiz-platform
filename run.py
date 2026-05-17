from flask import Flask, jsonify
import os
import threading
import time
import requests as http_requests
from config import SECRET_KEY
from database import init_db
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.user import user_bp
from routes.exam import exam_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)
app.register_blueprint(exam_bp)

# ── Health-check endpoint (for UptimeRobot / self-ping) ──────────────
@app.route('/health')
def health_check():
    return jsonify(status='alive'), 200

# ── Background self-ping to prevent Render free-tier sleep ───────────
def keep_alive():
    """Pings our own /health endpoint every 10 minutes."""
    url = os.environ.get("RENDER_EXTERNAL_URL")  # Render sets this automatically
    if not url:
        print(" * RENDER_EXTERNAL_URL not set – self-ping disabled (local mode)")
        return
    url = url.rstrip('/') + '/health'
    print(f" * Keep-alive thread started → pinging {url} every 10 min")
    while True:
        time.sleep(600)  # 10 minutes
        try:
            r = http_requests.get(url, timeout=15)
            print(f" * Keep-alive ping: {r.status_code}")
        except Exception as e:
            print(f" * Keep-alive ping failed: {e}")

import traceback
@app.errorhandler(Exception)
def handle_exception(e):
    with open("error_log.txt", "a") as f:
        f.write(traceback.format_exc() + "\n")
    return "Internal Server Error", 500

# ── Initialise DB and start keep-alive on import ────────────────────
init_db()
_keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
_keep_alive_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    print(f" * Quiz Platform Server starting on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)

