"""SQLite schema + demo users."""
import sqlite3
from werkzeug.security import generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('reporter','developer','lead')), skills TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS issues(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
  reporter_id INTEGER NOT NULL REFERENCES users(id), assignee_id INTEGER REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'New', type TEXT, severity TEXT, priority TEXT, component TEXT,
  confidence REAL, duplicate_of INTEGER, duplicate_score REAL, triage_ms INTEGER,
  sla_due TEXT, escalated INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT, resolved_at TEXT,
  predicted_type TEXT, predicted_severity TEXT, predicted_component TEXT);
CREATE TABLE IF NOT EXISTS comments(
  id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES issues(id), user_id INTEGER NOT NULL REFERENCES users(id),
  text TEXT NOT NULL, created_at TEXT);
CREATE TABLE IF NOT EXISTS history(
  id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES issues(id), user_id INTEGER, action TEXT, detail TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS notifications(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), issue_id INTEGER, message TEXT,
  channel TEXT DEFAULT 'in-app', created_at TEXT, is_read INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY, issue_id INTEGER, field TEXT, predicted TEXT, corrected TEXT, created_at TEXT);
"""

DEMO_PASSWORD = "demo123"
DEMO_USERS = [  # name, email, role, skills
    ("Priya Sharma", "lead@demo.com", "lead", ""),
    ("Ravi Kumar", "ravi@demo.com", "developer", "backend,database,payments"),
    ("Anita Rao", "anita@demo.com", "developer", "ui"),
    ("Kiran Reddy", "kiran@demo.com", "developer", "backend,database"),
    ("Meera Nair", "meera@demo.com", "developer", "auth,backend"),
    ("Arjun Das", "arjun@demo.com", "developer", "payments,ui"),
    ("Tester Tina", "tester@demo.com", "reporter", ""),
]


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        for n, e, r, s in DEMO_USERS:
            conn.execute("INSERT INTO users(name,email,password_hash,role,skills) VALUES(?,?,?,?,?)",
                         (n, e, generate_password_hash(DEMO_PASSWORD), r, s))
        conn.commit()
    conn.close()
