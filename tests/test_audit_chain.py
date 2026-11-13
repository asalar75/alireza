import sqlite3

import pytest

from core.audit import GENESIS, LEGACY_ACTOR
from core.database import Database, DatabaseError
from legacy_v02 import build_v02_db


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "a.sqlite3", actor="alice")
    pid = d.create_project("P", "https://example.com", "AUTH")
    d.add_asset(pid, "https://api.example.com")
    d.add_finding(pid, "t1", "Low", "Low", "", "Needs review", "", "")
    d.add_finding(pid, "t2", "High", "High", "", "Needs review", "", "")
    return d


def raw_unprotected(db):
    """Simulates a privileged attacker: separate connection, triggers removed."""
    c = sqlite3.connect(db.path, isolation_level=None)
    c.execute("DROP TRIGGER IF EXISTS audit_no_update")
    c.execute("DROP TRIGGER IF EXISTS audit_no_delete")
    return c


def test_entries_record_actor_time_action_and_details(db):
    rows = db.audit_entries()
    assert [r["action"] for r in rows] == ["PROJECT_CREATED", "ASSET_ADDED", "FINDING_ADDED", "FINDING_ADDED"]
    assert all(r["actor"] == "alice" and r["created_at"] for r in rows)
    assert rows[0]["prev_hash"] == GENESIS
    assert all(rows[i]["prev_hash"] == rows[i - 1]["entry_hash"] for i in range(1, len(rows)))


def test_intact_chain_verifies(db):
    v = db.verify_audit()
    assert v.ok and v.checked == 4 and v.problems == []


def test_default_actor_is_local_user(tmp_path):
    from core.audit import local_actor
    d = Database(tmp_path / "x.sqlite3")
    d.create_project("P", "https://example.com", "A")
    assert d.audit_entries()[0]["actor"] == local_actor() != ""


def test_triggers_block_update_and_delete(db):
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.conn.execute("UPDATE audit SET details='x' WHERE id=1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.conn.execute("DELETE FROM audit WHERE id=1")
    assert db.verify_audit().ok


def test_modified_entry_detected(db):
    c = raw_unprotected(db)
    c.execute("UPDATE audit SET details='https://evil.example' WHERE id=2")
    c.close()
    v = db.verify_audit()
    assert not v.ok and v.first_bad_id == 2
    assert any("modified" in p for p in v.problems)


def test_deleted_middle_entry_detected(db):
    c = raw_unprotected(db)
    c.execute("DELETE FROM audit WHERE id=2")
    c.close()
    v = db.verify_audit()
    assert not v.ok and v.first_bad_id == 3
    assert any("chain broken" in p for p in v.problems)


def test_inserted_entry_detected(db):
    c = raw_unprotected(db)
    c.execute("INSERT INTO audit(id,project_id,action,details,created_at,actor,prev_hash,entry_hash) "
              "VALUES(99,1,'FAKE','x','2026-01-01','mallory',?,?)", (GENESIS, "f" * 64))
    c.close()
    assert not db.verify_audit().ok


def test_tail_truncation_needs_external_head(db):
    ref = db.audit_head()
    c = raw_unprotected(db)
    c.execute("DELETE FROM audit WHERE id=4")
    c.close()
    assert db.verify_audit().ok                       # documented limitation: chain alone is fine
    v = db.verify_audit(expected_head=ref["head"], expected_count=ref["count"])
    assert not v.ok                                   # ... but the external record catches it


def test_privileged_rewrite_is_NOT_detected_documented_limit(db):
    """An admin who recomputes the hashes defeats the (unkeyed) chain. Documented, not hidden."""
    from core.audit import entry_hash
    c = raw_unprotected(db)
    c.row_factory = sqlite3.Row
    c.execute("UPDATE audit SET details='rewritten' WHERE id=2")
    prev = GENESIS
    for r in c.execute("SELECT * FROM audit ORDER BY id").fetchall():
        h = entry_hash(prev, r["project_id"], r["action"], r["details"], r["created_at"], r["actor"])
        c.execute("UPDATE audit SET prev_hash=?, entry_hash=? WHERE id=?", (prev, h, r["id"]))
        prev = h
    c.close()
    assert db.verify_audit().ok


def test_audit_write_is_atomic_with_the_operation(db):
    n = len(db.audit_entries())
    with pytest.raises(DatabaseError):
        db.add_findings(1, [dict(title="ok", severity="Low", confidence="Low", url="",
                                 status="s", evidence="", remediation=""),
                            dict(title=None, severity="Low", confidence="Low", url="",
                                 status="s", evidence="", remediation="")])
    assert len(db.audit_entries()) == n and db.verify_audit().ok


def test_v02_audit_rows_are_backfilled_into_chain(tmp_path):
    p = tmp_path / "v02.sqlite3"
    build_v02_db(p)
    d = Database(p, actor="bob")
    d.create_project("New", "https://new.example", "A")
    rows = d.audit_entries()
    legacy = [r for r in rows if r["actor"] == LEGACY_ACTOR]
    assert len(legacy) == 4          # 2 PROJECT_CREATED + 2 ASSET_RESTORED_BY_MIGRATION
    assert rows[-1]["actor"] == "bob"
    assert d.verify_audit().ok


def test_chain_survives_backup_restore(db, tmp_path):
    bak = db.backup_to(tmp_path / "b.bak")
    db.restore_from(bak)
    assert db.verify_audit().ok
    assert db.audit_entries()[-1]["action"] == "BACKUP_RESTORED"
