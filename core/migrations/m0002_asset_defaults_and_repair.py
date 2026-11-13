"""Migration 2: root-cause fix of the v0.2 target-asset bug + data repair.

Root cause (v0.2 ``Database.create_project``)::

    INSERT OR IGNORE INTO assets(project_id, origin) VALUES(?, ?)

``assets.created_at`` is ``NOT NULL`` with no default. ``OR IGNORE`` makes SQLite skip the
row *silently* on a NOT NULL violation, so a project's own target was never recorded and
the first passive scan always failed with "not in the approved scope".

Fix, in two layers:
1. Schema: ``assets.created_at`` gets a default (table rebuild, 12-step SQLite procedure),
   so an omitted value can never produce a silent skip again.
2. Code (``Database``): no ``OR IGNORE`` any more; conflicts are handled with
   ``ON CONFLICT(project_id, origin) DO NOTHING`` which only covers the UNIQUE case.

Data repair for existing v0.2 projects: for every project whose normalised target origin
is missing from ``assets`` the origin is inserted with a note saying it was restored. The
target is the origin the analyst named together with the written-authorisation reference
at project creation, so restoring it re-establishes the original intent; it does not
widen scope. Targets that cannot be normalised are NOT inserted and are reported in the
migration notes (and audited) for manual review.
"""
import sqlite3
from datetime import datetime, timezone

from ..scope import normalize_origin

REPAIR_NOTE = "restored by migration 0002 (v0.2 target-asset bug)"


def up(conn: sqlite3.Connection) -> dict:
    conn.execute("""CREATE TABLE assets_new(
      id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
      origin TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'Web origin',
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      UNIQUE(project_id, origin),
      FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
    conn.execute("""INSERT INTO assets_new(id,project_id,origin,asset_type,notes,created_at)
                    SELECT id,project_id,origin,asset_type,notes,created_at FROM assets""")
    conn.execute("DROP TABLE assets")
    conn.execute("ALTER TABLE assets_new RENAME TO assets")

    now = datetime.now(timezone.utc).isoformat()
    restored, skipped = [], []
    for pid, target in conn.execute("SELECT id, target FROM projects ORDER BY id").fetchall():
        try:
            origin = normalize_origin(target)
        except ValueError:
            skipped.append({"project_id": pid, "target": target})
            conn.execute("INSERT INTO audit(project_id,action,details,created_at) VALUES(?,?,?,?)",
                         (pid, "MIGRATION_TARGET_SKIPPED", f"invalid target needs review: {target!r}", now))
            continue
        cur = conn.execute(
            """INSERT INTO assets(project_id,origin,asset_type,notes,created_at)
               VALUES(?,?, 'Web origin', ?, ?)
               ON CONFLICT(project_id, origin) DO NOTHING""",
            (pid, origin, REPAIR_NOTE, now))
        if cur.rowcount:
            restored.append({"project_id": pid, "origin": origin})
            conn.execute("INSERT INTO audit(project_id,action,details,created_at) VALUES(?,?,?,?)",
                         (pid, "ASSET_RESTORED_BY_MIGRATION", origin, now))
    return {"restored_target_assets": restored, "skipped_invalid_targets": skipped}
