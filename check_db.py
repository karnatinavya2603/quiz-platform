import sqlite3
conn = sqlite3.connect('quiz.db')
conn.row_factory = sqlite3.Row

print("=== SCHEMA ===")
for r in conn.execute("PRAGMA table_info(users)").fetchall():
    print(dict(r))

print("\n=== USERS ===")
for r in conn.execute("SELECT * FROM users").fetchall():
    print(dict(r))

conn.close()
