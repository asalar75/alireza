"""SQLite persistence for AegisSec Enterprise.

Guarantees
----------
* Schema is created/upgraded only through ``core.migrations`` (versioned, transactional).
* Every write goes through ``Database.transaction()`` (``BEGIN IMMEDIATE`` ... ``COMMIT``,
  ``ROLLBACK`` on any error). A business operation and its audit record commit together
  or not at all.
* WAL journal + ``synchronous=FULL``: a crash or power loss can lose neither a committed
  transaction nor leave a half-written one.
* Foreign keys are enforced on every connection.
* Consistent online backup (SQLite backup API) with integrity verification, and a
  verified, refuse-if-newer restore that first takes a safety copy of the current data.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .audit import GENESIS, AuditVerification, entry_hash, local_actor, verify_chain
from .migrations import LATEST_VERSION, MigrationError, current_version, migrate
from .scope import normalize_origin

DB_PATH = Path.home() / ".aegissec" / "aegissec.sqlite3"


class DatabaseError(Exception):
    """A database operation failed and was rolled back."""


class Database:
    def __init__(self, path=DB_PATH, *, backup_dir=None, actor=None):
        self.actor = actor or local_actor()
        self.in_memory = str(path) == ":memory:"
        self.path = Path(path)
        if not self.in_memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir = Path(backup_dir) if backup_dir else self.path.parent / "backups"
        self._depth = 0
        self.conn = self._connect(":memory:" if self.in_memory else self.path)
        self.applied_migrations = migrate(
            self.conn, db_path=None if self.in_memory else self.path, backup_dir=self.backup_dir)
        self.interrupted_operations = self.mark_interrupted_operations()

    # ------------------------------------------------------------------ connection
    @staticmethod
    def _connect(target) -> sqlite3.Connection:
        conn = sqlite3.connect(target, isolation_level=None)  # explicit transactions only
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        if str(target) != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    @property
    def schema_version(self) -> int:
        return current_version(self.conn)

    # ------------------------------------------------------------------ transactions
    @contextmanager
    def transaction(self):
        """Atomic unit of work. Nested use joins the outer transaction."""
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        try:
            self.conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise DatabaseError(f"cannot start transaction: {exc}") from exc
        self._depth = 1
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException as exc:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            if isinstance(exc, sqlite3.Error):
                raise DatabaseError(str(exc)) from exc
            raise
        finally:
            self._depth = 0

    # ------------------------------------------------------------------ audit
    def _log(self, project_id, action, details=""):
        """Append a hash-chained entry. Must run inside a transaction (BEGIN IMMEDIATE
        serialises writers, so reading the previous hash here is race-free)."""
        row = self.conn.execute("SELECT entry_hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        prev = row[0] if row else GENESIS
        created = self.now()
        digest = entry_hash(prev, project_id, action, details, created, self.actor)
        self.conn.execute(
            "INSERT INTO audit(project_id,action,details,created_at,actor,prev_hash,entry_hash) "
            "VALUES(?,?,?,?,?,?,?)", (project_id, action, details, created, self.actor, prev, digest))

    def log(self, project_id, action, details=""):
        with self.transaction():
            self._log(project_id, action, details)

    def audit_entries(self, project_id=None):
        if project_id is None:
            return self.conn.execute("SELECT * FROM audit ORDER BY id").fetchall()
        return self.conn.execute("SELECT * FROM audit WHERE project_id=? ORDER BY id",
                                 (project_id,)).fetchall()

    def verify_audit(self, *, expected_head=None, expected_count=None) -> AuditVerification:
        return verify_chain(self.conn, expected_head=expected_head, expected_count=expected_count)

    def audit_head(self) -> dict:
        """Head hash + count; record it outside the database to detect tail truncation."""
        v = verify_chain(self.conn)
        return {"head": v.head, "count": v.checked}

    # ------------------------------------------------------------------ projects
    def create_project(self, name, target, authorized_by):
        origin = normalize_origin(target)  # raises ValueError on a malformed origin
        with self.transaction():
            cur = self.conn.execute(
                "INSERT INTO projects(name,target,authorized_by,created_at) VALUES(?,?,?,?)",
                (name, origin, authorized_by, self.now()))
            pid = cur.lastrowid
            # No OR IGNORE: only a UNIQUE conflict may be skipped, any other error must surface.
            self.conn.execute(
                """INSERT INTO assets(project_id,origin,asset_type,notes,created_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(project_id,origin) DO NOTHING""",
                (pid, origin, "Web origin", "project target", self.now()))
            self._log(pid, "PROJECT_CREATED", origin)
        return pid

    def projects(self):
        return self.conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()

    # ------------------------------------------------------------------ assets
    def add_asset(self, project_id, origin, asset_type="Web origin", notes=""):
        origin = normalize_origin(origin)
        with self.transaction():
            cur = self.conn.execute(
                """INSERT INTO assets(project_id,origin,asset_type,notes,created_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(project_id,origin) DO NOTHING""",
                (project_id, origin, asset_type, notes, self.now()))
            if cur.rowcount:
                self._log(project_id, "ASSET_ADDED", origin)
            return bool(cur.rowcount)

    def assets(self, project_id):
        return self.conn.execute("SELECT * FROM assets WHERE project_id=? ORDER BY id",
                                 (project_id,)).fetchall()

    # ------------------------------------------------------------------ findings
    def add_finding(self, project_id, title, severity, confidence, url, status,
                    evidence, remediation, reference=""):
        with self.transaction():
            cur = self.conn.execute(
                """INSERT INTO findings
                   (project_id,title,severity,confidence,url,status,evidence,remediation,reference,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (project_id, title, severity, confidence, url, status,
                 evidence, remediation, reference, self.now()))
            self._log(project_id, "FINDING_ADDED", f"{severity}/{confidence}: {title}")
            return cur.lastrowid

    def add_findings(self, project_id, findings):
        """Insert many findings atomically (all or none) - used by scans."""
        with self.transaction():
            for f in findings:
                self.add_finding(project_id, f["title"], f["severity"], f["confidence"], f["url"],
                                 f["status"], f["evidence"], f["remediation"], f.get("reference", ""))

    def findings(self, project_id):
        return self.conn.execute("SELECT * FROM findings WHERE project_id=? ORDER BY id DESC",
                                 (project_id,)).fetchall()

    # ------------------------------------------------------------------ operations
    def start_operation(self, project_id, op_id, name, details=""):
        with self.transaction():
            self.conn.execute(
                "INSERT INTO operations(id,project_id,name,state,started_at) VALUES(?,?,?, 'RUNNING', ?)",
                (op_id, project_id, name, self.now()))
            self._log(project_id, "OPERATION_STARTED", f"{name} [{op_id}] {details}".strip())

    def finish_operation(self, op_id, state, *, duration_ms=None, error="", summary=""):
        with self.transaction():
            row = self.conn.execute("SELECT project_id,name FROM operations WHERE id=?",
                                    (op_id,)).fetchone()
            if row is None:
                raise DatabaseError(f"unknown operation {op_id}")
            self.conn.execute(
                "UPDATE operations SET state=?,finished_at=?,duration_ms=?,error=?,summary=? WHERE id=?",
                (state, self.now(), duration_ms, error, summary, op_id))
            self._log(row["project_id"], f"OPERATION_{state}",
                      f"{row['name']} [{op_id}] {duration_ms}ms {error or summary}".strip())

    def operations(self, project_id):
        return self.conn.execute("SELECT * FROM operations WHERE project_id=? ORDER BY started_at DESC",
                                 (project_id,)).fetchall()

    def mark_interrupted_operations(self):
        """Called at startup: operations left RUNNING by a crash/kill are marked INTERRUPTED."""
        with self.transaction():
            rows = self.conn.execute("SELECT id,project_id,name FROM operations WHERE state='RUNNING'").fetchall()
            for r in rows:
                self.conn.execute("UPDATE operations SET state='INTERRUPTED',finished_at=?,"
                                  "error='application stopped while running' WHERE id=?",
                                  (self.now(), r["id"]))
                self._log(r["project_id"], "OPERATION_INTERRUPTED", f"{r['name']} [{r['id']}]")
            return len(rows)

    # ------------------------------------------------------------------ integrity
    def integrity_check(self) -> list[str]:
        """Empty list == healthy (integrity_check and foreign_key_check both clean)."""
        problems = [r[0] for r in self.conn.execute("PRAGMA integrity_check").fetchall()
                    if r[0] != "ok"]
        problems += [f"foreign key violation in {r[0]} rowid={r[1]}"
                     for r in self.conn.execute("PRAGMA foreign_key_check").fetchall()]
        return problems

    # ------------------------------------------------------------------ backup / restore
    @staticmethod
    def verify_backup(path) -> dict:
        """Open a backup read-only and check it. Raises DatabaseError if unusable."""
        path = Path(path)
        if not path.is_file():
            raise DatabaseError(f"backup not found: {path}")
        try:
            src = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise DatabaseError(f"cannot open backup: {exc}") from exc
        try:
            try:
                result = src.execute("PRAGMA integrity_check").fetchone()[0]
                version = current_version(src)
                tables = {r[0] for r in src.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            except sqlite3.Error as exc:
                raise DatabaseError(f"backup is not a valid database: {exc}") from exc
        finally:
            src.close()
        if result != "ok":
            raise DatabaseError(f"backup failed integrity check: {result}")
        if not {"projects", "assets", "findings", "audit"} <= tables:
            raise DatabaseError("file is not an AegisSec database (core tables missing)")
        if version > LATEST_VERSION:
            raise DatabaseError(
                f"backup schema v{version} is newer than this application (v{LATEST_VERSION})")
        return {"schema_version": version, "integrity": result}

    def backup_to(self, dest) -> Path:
        """Write a consistent, verified copy of the live database to ``dest`` atomically."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        dst = sqlite3.connect(tmp)
        try:
            self.conn.backup(dst)
        finally:
            dst.close()
        try:
            self.verify_backup(tmp)
        except DatabaseError:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(tmp, dest)
        with self.transaction():
            self._log(None, "BACKUP_CREATED", str(dest))
        return dest

    def restore_from(self, src) -> dict:
        """Replace the live data with a verified backup.

        The backup is verified first; the current data is saved to ``backup_dir`` as a safety
        copy; the restore itself is a single SQLite backup-API copy (atomic for readers);
        an older-schema backup is migrated forward afterwards.
        """
        info = self.verify_backup(src)
        if self._depth:
            raise DatabaseError("cannot restore inside a transaction")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safety = self.backup_to(self.backup_dir / f"pre-restore.{stamp}.bak")
        source = sqlite3.connect(f"{Path(src).resolve().as_uri()}?mode=ro", uri=True)
        try:
            source.backup(self.conn)
        except sqlite3.Error as exc:
            raise DatabaseError(f"restore failed; previous data kept in {safety}: {exc}") from exc
        finally:
            source.close()
        self.conn.execute("PRAGMA foreign_keys=ON")
        try:
            migrate(self.conn, db_path=None if self.in_memory else self.path,
                    backup_dir=self.backup_dir)
        except MigrationError as exc:
            raise DatabaseError(f"restored data could not be upgraded: {exc}") from exc
        problems = self.integrity_check()
        if problems:
            raise DatabaseError(f"restored database is inconsistent: {problems[:3]}; "
                                f"previous data kept in {safety}")
        with self.transaction():
            self._log(None, "BACKUP_RESTORED", str(src))
        return {"restored_schema_version": info["schema_version"], "safety_copy": str(safety)}
