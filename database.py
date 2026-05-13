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
            quiz_score   INTEGER DEFAULT 0,
            quiz_percentage REAL DEFAULT 0,
            last_quiz_date TEXT
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            type        TEXT NOT NULL DEFAULT 'mcq', -- 'mcq', 'coding', or 'mixed'
            description TEXT
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name        TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )""")
        
        # Add topic_id to questions if not exists
        try:
            conn.execute("ALTER TABLE questions ADD COLUMN topic_id INTEGER")
        except sqlite3.OperationalError:
            pass # Already exists
            
        # Add topic_id to coding_questions if not exists
        try:
            conn.execute("ALTER TABLE coding_questions ADD COLUMN topic_id INTEGER")
        except sqlite3.OperationalError:
            pass # Already exists

        try:
            conn.execute("ALTER TABLE users ADD COLUMN quiz_percentage REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN last_quiz_date TEXT")
        except sqlite3.OperationalError:
            pass

        conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            question  TEXT,
            a TEXT, b TEXT, c TEXT, d TEXT,
            answer    TEXT,
            published INTEGER DEFAULT 0,
            topic_id  INTEGER
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS coding_questions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            question       TEXT,
            sample_input   TEXT,
            sample_output  TEXT,
            published      INTEGER DEFAULT 0,
            topic_id       INTEGER
        )""")
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT NOT NULL,
            category_id       INTEGER,
            time_limit        INTEGER DEFAULT 0, -- in minutes
            positive_marks    REAL DEFAULT 1,
            negative_marks    REAL DEFAULT 0,
            shuffle_questions INTEGER DEFAULT 0,
            attempt_limit     INTEGER DEFAULT 1,
            is_active         INTEGER DEFAULT 1,
            created_at        TEXT,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )""")
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_topics (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id        INTEGER,
            topic_id       INTEGER,
            question_count INTEGER DEFAULT 0,
            question_type  TEXT DEFAULT 'mcq',
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id),
            FOREIGN KEY (topic_id) REFERENCES topics(id)
        )""")

        # Add question_type to quiz_topics if not exists
        try:
            conn.execute("ALTER TABLE quiz_topics ADD COLUMN question_type TEXT DEFAULT 'mcq'")
        except sqlite3.OperationalError:
            pass
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_manual_questions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id     INTEGER,
            question_id INTEGER,
            type        TEXT, -- 'mcq' or 'coding'
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
        )""")
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_quiz_attempts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT NOT NULL,
            quiz_id      INTEGER NOT NULL,
            score        INTEGER DEFAULT 0,
            percentage   REAL DEFAULT 0,
            status       TEXT DEFAULT 'completed',
            attempt_date TEXT,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
        )""")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS login_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT NOT NULL,
            login_date   TEXT NOT NULL
        )""")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )""")
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES('exam_started', '0')")
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES('pass_percentage', '60')")
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES('retake_wait_days', '7')")
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES('quiz_expiry_hours', '8760')")
        
        # Seed initial data
        conn.execute("INSERT OR REPLACE INTO categories(id, name, type) VALUES(1, 'Python Programming MCQs', 'mcq')")
        conn.execute("INSERT OR REPLACE INTO categories(id, name, type) VALUES(2, 'Python Coding', 'coding')")
        conn.execute("INSERT OR REPLACE INTO categories(id, name, type) VALUES(3, 'Mixed Assessment', 'mixed')")
        
        python_topics = ['list', 'dict', 'functions', 'regx']
        for i, topic in enumerate(python_topics, 1):
            # For MCQs
            conn.execute("INSERT OR REPLACE INTO topics(id, category_id, name) VALUES(?, 1, ?)", (i, topic))
            # For Coding
            conn.execute("INSERT OR REPLACE INTO topics(id, category_id, name) VALUES(?, 2, ?)", (i + 100, topic))
        
        # Pre-create admin account (Navya)
        conn.execute("""
        INSERT OR IGNORE INTO users(id,username,email,password,role,approved)
        VALUES (1,'navya','navyakarnati2603@gmail.com','navya@admin','admin',1)
        """)
        conn.commit()
