import os

SECRET_KEY    = "quiz_secret_2026"
DB_FILE       = os.path.join(os.path.dirname(__file__), "quiz.db")
SMTP_SENDER   = "navyakarnati2603@gmail.com"
SMTP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "ugmh qngp oyse orpr")
ADMIN_EMAIL   = "navyakarnati2603@gmail.com"
