"""Runs live in SQLite as one JSON document each. The live view and the dashboard both read from here."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db():
    config.DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DB, timeout=10)
    c.execute("create table if not exists runs (id text primary key, created text, doc text)")
    return c


def create(inp, mode):
    run = {"id": uuid.uuid4().hex[:10], "created": now(), "updated": now(), "input": inp, "mode": mode,
           "status": "running", "stages": [], "events": [], "credits": 0.0, "calls": [],
           "company": None, "person": None, "signals": [], "hook": None, "draft": None,
           "checks": [], "question": None, "review": None, "outcome": None, "version": 0}
    save(run)
    return run


def save(run):
    run["updated"] = now()
    run["version"] = run.get("version", 0) + 1
    with _lock, _db() as c:
        c.execute("insert or replace into runs values (?,?,?)", (run["id"], run["created"], json.dumps(run)))


def get(run_id):
    with _db() as c:
        row = c.execute("select doc from runs where id=?", (run_id,)).fetchone()
    return json.loads(row[0]) if row else None


def all_runs(limit=500):
    with _db() as c:
        rows = c.execute("select doc from runs order by created desc limit ?", (limit,)).fetchall()
    return [json.loads(r[0]) for r in rows]
