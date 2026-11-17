"""SQLite access layer."""
import json
import os
import sqlite3
from datetime import datetime, timezone

from . import config


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = connect()
    with open(config.SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def start_run(conn, kind, company_id=None):
    cur = conn.execute(
        "INSERT INTO runs(kind, company_id, started_at, status) VALUES (?,?,?, 'running')",
        (kind, company_id, now_iso()))
    conn.commit()
    return cur.lastrowid


def finish_run(conn, run_id, status, log):
    conn.execute("UPDATE runs SET finished_at=?, status=?, log=? WHERE id=?",
                 (now_iso(), status, log, run_id))
    conn.commit()


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def get_company(conn, company_id):
    c = row(conn, "SELECT * FROM companies WHERE id=?", (company_id,))
    if c:
        try:
            c["profile"] = json.loads(c.get("profile_json") or "{}")
        except Exception:
            c["profile"] = {}
    return c
