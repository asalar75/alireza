import sqlite3

import pytest

from core.database import Database, DatabaseError
from core.migrations import LATEST_VERSION, MigrationError, migrate
from legacy_v02 import build_v02_db


def raw(path):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


# ---------------------------------------------------------------- bug reproduction
def test_v02_fixture_really_has_the_bug(tmp_path):
    """Guards the fixture: the verbatim v0.2 code must lose the target asset."""
    p = tmp_path / "v02.sqlite3"
    build_v02_db(p)
    c = raw(p)
    assert c.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 2
    assert c.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0
    assert c.execute("PRAGMA user_version").fetchone()[0] == 0


# ---------------------------------------------------------------- regression (new DB)
def test_new_project_registers_target_asset(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("Demo", "https://Example.COM/", "AUTH-9")
    assets = db.assets(pid)
    assert [a["origin"] for a in assets] == ["https://example.com"]
    assert assets[0]["created_at"]


def test_scope_check_passes_for_fresh_project(tmp_path):
    from core.scope import is_in_scope
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("Demo", "https://example.com", "AUTH-9")
    origins = [a["origin"] for a in db.assets(pid)]
    assert is_in_scope("https://example.com", origins)


def test_omitting_created_at_can_no_longer_be_swallowed(tmp_path):
    """Schema-level fix: created_at has a default, so the old statement now inserts."""
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("Demo", "https://example.com", "A")
    db.conn.execute("INSERT INTO assets(project_id,origin) VALUES(?,?)", (pid, "https://x.example"))
    row = db.conn.execute("SELECT created_at FROM assets WHERE origin='https://x.example'").fetchone()
    assert row and row["created_at"]


def test_non_unique_errors_are_not_ignored(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    with pytest.raises(DatabaseError):
        with db.transaction():
            db.conn.execute("INSERT INTO assets(project_id,origin) VALUES(999,'https://x.example')")


def test_duplicate_asset_is_noop_not_error(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("Demo", "https://example.com", "A")
    assert db.add_asset(pid, "https://EXAMPLE.com") is False
    assert db.add_asset(pid, "https://api.example.com") is True
    assert len(db.assets(pid)) == 2


# ---------------------------------------------------------------- migration: fresh
def test_fresh_database_is_at_latest_version(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    assert db.schema_version == LATEST_VERSION
    assert [m.version for m in db.applied_migrations] == list(range(1, LATEST_VERSION + 1))
    assert db.integrity_check() == []
    # no backup for an empty new database
    assert not list((tmp_path / "backups").glob("*")) if (tmp_path / "backups").exists() else True


def test_reopen_is_idempotent(tmp_path):
    p = tmp_path / "a.sqlite3"
    Database(p).close()
    db = Database(p)
    assert db.applied_migrations == []


# ---------------------------------------------------------------- migration: v0.2 data
def test_v02_database_is_migrated_and_repaired(tmp_path):
    p = tmp_path / "v02.sqlite3"
    pids = build_v02_db(p)
    # add some user data that must survive untouched
    c = sqlite3.connect(p)
    c.execute("""INSERT INTO findings(project_id,title,severity,confidence,url,status,evidence,
                 remediation,reference,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (pids[0], "HSTS header not observed", "Low", "Low", "https://example.com",
               "Needs review", "ev", "rem", "ref", "2026-01-01T00:00:00+00:00"))
    c.commit()
    before_audit = c.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    c.close()

    db = Database(p)
    assert db.schema_version == LATEST_VERSION
    for pid, origin in zip(pids, ["https://example.com", "https://example.org:8443"]):
        assets = db.assets(pid)
        assert [a["origin"] for a in assets] == [origin]
        assert "migration 0002" in assets[0]["notes"]
    assert len(db.findings(pids[0])) == 1 and db.findings(pids[0])[0]["evidence"] == "ev"
    assert len(db.projects()) == 2
    assert db.integrity_check() == []
    n_audit = db.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    assert n_audit == before_audit + 2          # one ASSET_RESTORED_BY_MIGRATION per project
    notes = {m.version: m.notes for m in db.applied_migrations}
    assert len(notes[2]["restored_target_assets"]) == 2


def test_v02_migration_creates_backup_first(tmp_path):
    p = tmp_path / "v02.sqlite3"
    build_v02_db(p)
    Database(p).close()
    backups = list((tmp_path / "backups").glob("*.bak"))
    assert len(backups) == 1
    old = raw(backups[0])                       # backup = untouched v0.2 state (rollback path)
    assert old.execute("PRAGMA user_version").fetchone()[0] == 0
    assert old.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0
    assert old.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 2


def test_migrated_scan_scope_works_on_old_project(tmp_path):
    from core.scope import is_in_scope
    p = tmp_path / "v02.sqlite3"
    pids = build_v02_db(p)
    db = Database(p)
    assert is_in_scope("https://example.com", [a["origin"] for a in db.assets(pids[0])])


def test_existing_asset_not_duplicated_by_repair(tmp_path):
    p = tmp_path / "v02.sqlite3"
    pids = build_v02_db(p, projects=(("P1", "https://example.com", "A"),))
    c = sqlite3.connect(p)   # analyst had manually added the target in v0.2
    c.execute("INSERT INTO assets(project_id,origin,created_at) VALUES(?,?,?)",
              (pids[0], "https://example.com", "2026-01-01T00:00:00+00:00"))
    c.commit(); c.close()
    db = Database(p)
    assets = db.assets(pids[0])
    assert len(assets) == 1 and "migration 0002" not in assets[0]["notes"]


def test_invalid_legacy_target_is_reported_not_inserted(tmp_path):
    p = tmp_path / "v02.sqlite3"
    build_v02_db(p, projects=(("Bad", "not a valid url with spaces/path", "A"),
                              ("Good", "https://example.com", "A")))
    db = Database(p)
    notes = {m.version: m.notes for m in db.applied_migrations}[2]
    assert len(notes["skipped_invalid_targets"]) == 1
    assert len(notes["restored_target_assets"]) == 1
    bad_pid = notes["skipped_invalid_targets"][0]["project_id"]
    assert db.assets(bad_pid) == []
    assert db.conn.execute("SELECT 1 FROM audit WHERE action='MIGRATION_TARGET_SKIPPED'").fetchone()


# ---------------------------------------------------------------- migration safety
def test_failed_migration_rolls_back_schema_and_version(tmp_path):
    from core.migrations import MIGRATIONS, Migration
    p = tmp_path / "v02.sqlite3"
    build_v02_db(p)
    conn = sqlite3.connect(p, isolation_level=None)

    def broken(c):
        c.execute("ALTER TABLE projects ADD COLUMN extra TEXT")   # DDL succeeded ...
        c.execute("INSERT INTO nonexistent VALUES (1)")           # ... then failure
    migs = MIGRATIONS + (Migration(LATEST_VERSION + 1, "broken", broken),)
    with pytest.raises(sqlite3.OperationalError):
        migrate(conn, db_path=p, migrations=migs)
    # everything up to the broken one committed; the broken one left no trace
    assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
    cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)")]
    assert "extra" not in cols
    assert not conn.in_transaction


def test_foreign_key_violation_blocks_commit(tmp_path):
    from core.migrations import MIGRATIONS, Migration
    p = tmp_path / "a.sqlite3"
    Database(p).close()
    conn = sqlite3.connect(p, isolation_level=None)

    def orphan(c):
        c.execute("INSERT INTO findings(project_id,title,severity,created_at) "
                  "VALUES(12345,'x','Low','now')")
    migs = MIGRATIONS + (Migration(LATEST_VERSION + 1, "orphan", orphan),)
    with pytest.raises(MigrationError):
        migrate(conn, db_path=p, migrations=migs)
    assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0
    assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION


def test_newer_database_is_refused_and_untouched(tmp_path):
    p = tmp_path / "future.sqlite3"
    Database(p).close()
    c = sqlite3.connect(p)
    c.execute(f"PRAGMA user_version={LATEST_VERSION + 5}")
    c.close()
    with pytest.raises(MigrationError):
        Database(p)
    c = sqlite3.connect(p)
    assert c.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION + 5
