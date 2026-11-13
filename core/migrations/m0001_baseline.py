"""Migration 1: baseline = the exact v0.2 schema (idempotent) + schema_migrations.

A v0.2 database already has these tables, so every statement is IF NOT EXISTS and the
migration is a no-op for them. NOTE: the v0.2 ``assets.created_at`` column has no default;
that is repaired by migration 2.
"""
import sqlite3

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS projects(
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, target TEXT NOT NULL,
      authorized_by TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS assets(
      id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
      origin TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'Web origin',
      notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
      UNIQUE(project_id, origin),
      FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS findings(
      id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
      title TEXT NOT NULL, severity TEXT NOT NULL, confidence TEXT NOT NULL DEFAULT 'Medium',
      url TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Needs review',
      evidence TEXT NOT NULL DEFAULT '', remediation TEXT NOT NULL DEFAULT '',
      reference TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
      FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS audit(
      id INTEGER PRIMARY KEY, project_id INTEGER, action TEXT NOT NULL,
      details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS schema_migrations(
      version INTEGER PRIMARY KEY, name TEXT NOT NULL,
      applied_at TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '{}')""",
)


def up(conn: sqlite3.Connection) -> dict:
    for stmt in STATEMENTS:
        conn.execute(stmt)
    return {}
