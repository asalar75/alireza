"""Migration 4: operations table (status, timing and outcome of long-running operations)."""
import sqlite3


def up(conn: sqlite3.Connection) -> dict:
    conn.execute("""CREATE TABLE operations(
      id TEXT PRIMARY KEY, project_id INTEGER NOT NULL, name TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED','INTERRUPTED')),
      started_at TEXT NOT NULL, finished_at TEXT, duration_ms INTEGER,
      error TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
      FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
    conn.execute("CREATE INDEX idx_operations_project ON operations(project_id)")
    return {}
