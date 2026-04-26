import sqlite3
from config import DB_FILE


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT    UNIQUE NOT NULL,
            email        TEXT    NOT NULL,
            password     TEXT    NOT NULL,
            role         TEXT    NOT NULL DEFAULT 'user',
            approved     INTEGER NOT NULL DEFAULT 0,
            token        TEXT,
            last_login   TEXT,
            login_count  INTEGER DEFAULT 0,
            quiz_status  TEXT    DEFAULT 'not_started',
            quiz_score   INTEGER DEFAULT 0
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            question  TEXT,
            a TEXT, b TEXT, c TEXT, d TEXT,
            answer    TEXT,
            published INTEGER DEFAULT 0
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS coding_questions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            question       TEXT,
            sample_input   TEXT,
            sample_output  TEXT,
            published      INTEGER DEFAULT 0
        )""")
        # Pre-create admin account (Navya)
        conn.execute("""
        INSERT OR IGNORE INTO users(id,username,email,password,role,approved)
        VALUES (1,'navya','navyakarnati2603@gmail.com','navya@admin','admin',1)
        """)
        conn.commit()
