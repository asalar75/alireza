"""Versioned, transactional SQLite migrations.

Design rules
------------
* The schema version lives in ``PRAGMA user_version`` (an integer in the DB header).
  A database created by AegisSec v0.2 has ``user_version == 0`` and the v0.2 tables;
  migration 1 (baseline) is idempotent so it is a no-op on such a database.
* Every migration runs inside ONE ``BEGIN IMMEDIATE`` transaction together with the
  ``user_version`` bump. SQLite DDL is transactional, so a failure rolls the schema,
  the data and the version back together.
* Foreign keys are switched off for the duration of a migration (required by the
  SQLite table-rebuild procedure) and ``PRAGMA foreign_key_check`` must be clean before
  commit.
* Before the first pending migration is applied to an existing, non-empty file, a
  consistent backup is written next to it (``*.pre-vN-to-vM.<timestamp>.bak``). That
  backup is the documented rollback path: restore it with the previous app version.
* A database whose version is NEWER than the application knows is refused, never
  modified (downgrade protection).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import m0001_baseline, m0002_asset_defaults_and_repair, m0003_audit_hash_chain, m0004_operations


class MigrationError(Exception):
    """Raised when a migration cannot be applied safely."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up: Callable[[sqlite3.Connection], Optional[dict]]


@dataclass(frozen=True)
class AppliedMigration:
    version: int
    name: str
    notes: dict


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "baseline_v0_2_schema", m0001_baseline.up),
    Migration(2, "asset_defaults_and_target_repair", m0002_asset_defaults_and_repair.up),
    Migration(3, "audit_hash_chain", m0003_audit_hash_chain.up),
    Migration(4, "operations", m0004_operations.up),
)

LATEST_VERSION = MIGRATIONS[-1].version


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _has_user_tables(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
    ).fetchone()
    return row is not None


def _make_backup(conn: sqlite3.Connection, db_path: Path, backup_dir: Path,
                 from_v: int, to_v: int) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = backup_dir / f"{db_path.stem}.pre-v{from_v}-to-v{to_v}.{stamp}.bak"
    tmp = dest.with_suffix(".tmp")
    dst = sqlite3.connect(tmp)
    try:
        conn.backup(dst)
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise MigrationError(f"pre-migration backup failed integrity check: {ok}")
    finally:
        dst.close()
    tmp.replace(dest)
    return dest


def migrate(conn: sqlite3.Connection, *, db_path: Optional[Path] = None,
            backup_dir: Optional[Path] = None,
            migrations: tuple[Migration, ...] = MIGRATIONS) -> list[AppliedMigration]:
    """Apply all pending migrations. ``conn`` must be in autocommit mode
    (``isolation_level=None``). Returns what was applied (empty if up to date)."""
    if conn.in_transaction:
        raise MigrationError("migrate() must not be called inside a transaction")
    latest = migrations[-1].version
    cur = current_version(conn)
    if cur > latest:
        raise MigrationError(
            f"Database schema v{cur} is newer than this application (v{latest}). "
            "Refusing to open it; upgrade AegisSec instead.")
    pending = [m for m in migrations if m.version > cur]
    if not pending:
        return []

    if db_path is not None and _has_user_tables(conn):
        _make_backup(conn, Path(db_path), Path(backup_dir or Path(db_path).parent / "backups"),
                     cur, pending[-1].version)

    applied: list[AppliedMigration] = []
    for m in pending:
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                notes = m.up(conn) or {}
                violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise MigrationError(
                        f"migration {m.version} left {len(violations)} foreign-key violation(s)")
                conn.execute(
                    "INSERT OR REPLACE INTO schema_migrations(version,name,applied_at,notes) "
                    "VALUES(?,?,?,?)",
                    (m.version, m.name, datetime.now(timezone.utc).isoformat(),
                     json.dumps(notes, ensure_ascii=False)))
                conn.execute(f"PRAGMA user_version={int(m.version)}")
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        applied.append(AppliedMigration(m.version, m.name, notes))
    return applied
