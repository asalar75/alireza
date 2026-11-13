"""Migration 3: tamper-evident audit log (hash chain) + append-only triggers + indexes.

Rebuilds ``audit`` with ``actor``, ``prev_hash`` and ``entry_hash`` columns, back-fills the
chain over the existing rows in id order (actor ``legacy-v0.2``), installs triggers that
reject UPDATE/DELETE, and adds indexes on the project foreign keys. ``audit.project_id``
deliberately has no foreign key: audit history must outlive a deleted project.
See ``core/audit.py`` for the limits of this protection.
"""
import sqlite3

from ..audit import GENESIS, LEGACY_ACTOR, entry_hash

TRIGGERS = (
    """CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit
       BEGIN SELECT RAISE(ABORT,'audit log is append-only'); END""",
    """CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit
       BEGIN SELECT RAISE(ABORT,'audit log is append-only'); END""",
)


def up(conn: sqlite3.Connection) -> dict:
    conn.execute("""CREATE TABLE audit_new(
      id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,
      action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL, actor TEXT NOT NULL,
      prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL UNIQUE)""")
    prev = GENESIS
    n = 0
    for r in conn.execute("SELECT id,project_id,action,details,created_at FROM audit ORDER BY id").fetchall():
        h = entry_hash(prev, r[1], r[2], r[3], r[4], LEGACY_ACTOR)
        conn.execute("INSERT INTO audit_new(id,project_id,action,details,created_at,actor,prev_hash,entry_hash) "
                     "VALUES(?,?,?,?,?,?,?,?)", (r[0], r[1], r[2], r[3], r[4], LEGACY_ACTOR, prev, h))
        prev = h
        n += 1
    conn.execute("DROP TABLE audit")
    conn.execute("ALTER TABLE audit_new RENAME TO audit")
    for t in TRIGGERS:
        conn.execute(t)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_project ON audit(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_project ON findings(project_id)")
    return {"audit_entries_chained": n}
