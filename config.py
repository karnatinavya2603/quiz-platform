import os

SECRET_KEY    = "quiz_secret_2026"
DB_FILE       = os.path.join(os.path.dirname(__file__), "quiz.db")
SMTP_SENDER   = os.environ.get("SMTP_SENDER", "navyakarnati2603@gmail.com")
SMTP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "ugmh qngp oyse orpr")
ADMIN_EMAIL   = os.environ.get("ADMIN_EMAIL", "navyakarnati2603@gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", 465))
SMTP_USE_SSL  = os.environ.get("SMTP_USE_SSL", "True").lower() == "true"
