"""SQLite storage (WAL mode). One file, no server. Path comes from FCA_DATA_DIR."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS_PATH = ROOT / "config" / "defaults.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS students(
  id INTEGER PRIMARY KEY, alias TEXT UNIQUE NOT NULL, program TEXT, year INTEGER, semester INTEGER,
  tier TEXT, required TEXT NOT NULL DEFAULT '[]', backlog TEXT NOT NULL DEFAULT '[]',
  code_hash TEXT UNIQUE, code_expires TEXT, synthetic INTEGER NOT NULL DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS preferences(
  student_id INTEGER PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
  electives TEXT NOT NULL DEFAULT '[]', pins TEXT NOT NULL DEFAULT '[]',
  ranking TEXT NOT NULL DEFAULT '[]', never TEXT NOT NULL DEFAULT '[]',
  submitted_at TEXT, updated_at TEXT, submit_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS capacity(offering_id TEXT PRIMARY KEY, seats INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, round INTEGER NOT NULL, seed TEXT NOT NULL,
  created TEXT NOT NULL, report TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS allocations(
  run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE, student_id INTEGER NOT NULL,
  status TEXT NOT NULL, combo TEXT NOT NULL DEFAULT '[]', archetype TEXT, choice_rank INTEGER,
  position INTEGER, explanation TEXT, PRIMARY KEY(run_id, student_id));
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, student_id INTEGER, type TEXT NOT NULL, detail TEXT);
CREATE INDEX IF NOT EXISTS events_student ON events(student_id, ts);
CREATE TABLE IF NOT EXISTS feedback(
  student_id INTEGER PRIMARY KEY, ts TEXT NOT NULL, sus TEXT NOT NULL, ease INTEGER,
  confused TEXT, comments TEXT);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, student_id INTEGER, is_admin INTEGER NOT NULL DEFAULT 0,
  csrf TEXT NOT NULL, expires TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS add_drop(
  id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, ts TEXT NOT NULL, before TEXT, after TEXT);
"""


def data_dir() -> Path:
    d = Path(os.environ.get("FCA_DATA_DIR", ROOT.parent / "var"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "fca.db"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    con = sqlite3.connect(db_path(), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def init() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
        for k, v in defaults.items():
            if not k.startswith("_"):
                con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, json.dumps(v)))


def get_settings(con) -> dict:
    return {r["key"]: json.loads(r["value"]) for r in con.execute("SELECT key, value FROM settings")}


def set_settings(con, values: dict) -> None:
    for k, v in values.items():
        con.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, json.dumps(v)))


def log_event(con, student_id, etype: str, detail=None) -> None:
    con.execute("INSERT INTO events(ts, student_id, type, detail) VALUES(?, ?, ?, ?)",
                (now(), student_id, etype, json.dumps(detail) if detail is not None else None))
