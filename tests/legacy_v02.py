"""Builds a genuine AegisSec v0.2 database, including the v0.2 bug, for migration tests.

The DDL and the ``create_project`` statements are copied verbatim from v0.2
(core/database.py) so the fixture reproduces what real v0.2 installations contain.
"""
import sqlite3
from datetime import datetime, timezone

V02_DDL = """
CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, target TEXT NOT NULL,
  authorized_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
  origin TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'Web origin',
  notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
  UNIQUE(project_id, origin),
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS findings(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
  title TEXT NOT NULL, severity TEXT NOT NULL, confidence TEXT NOT NULL DEFAULT 'Medium',
  url TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Needs review',
  evidence TEXT NOT NULL DEFAULT '', remediation TEXT NOT NULL DEFAULT '',
  reference TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, project_id INTEGER, action TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def v02_create_project(conn, name, target, authorized_by):
    """v0.2 ``Database.create_project`` verbatim (note the buggy INSERT OR IGNORE)."""
    cur = conn.execute(
        "INSERT INTO projects(name,target,authorized_by,created_at) VALUES(?,?,?,?)",
        (name, target, authorized_by, _now()))
    pid = cur.lastrowid
    conn.execute("INSERT OR IGNORE INTO assets(project_id,origin) VALUES(?,?)", (pid, target))
    conn.commit()
    conn.execute("INSERT INTO audit(project_id,action,details,created_at) VALUES(?,?,?,?)",
                 (pid, "PROJECT_CREATED", target, _now()))
    conn.commit()
    return pid


def build_v02_db(path, projects=(("P1", "https://example.com", "AUTH-1"),
                                  ("P2", "https://example.org:8443", "AUTH-2"))):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(V02_DDL)
    pids = [v02_create_project(conn, *p) for p in projects]
    conn.commit()
    conn.close()
    return pids
