import subprocess
import sqlite3
import sys
import textwrap
from pathlib import Path

import pytest

from core.database import Database, DatabaseError

ROOT = Path(__file__).resolve().parents[1]


def test_transaction_rolls_back_everything_on_error(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("P", "https://example.com", "A")
    before = (len(db.findings(pid)), db.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0])
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.add_finding(pid, "t", "Low", "Low", "", "Needs review", "", "")
            raise RuntimeError("boom")
    after = (len(db.findings(pid)), db.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0])
    assert after == before
    assert not db.conn.in_transaction


def test_bulk_findings_are_all_or_nothing(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("P", "https://example.com", "A")
    good = dict(title="a", severity="Low", confidence="Low", url="", status="Needs review",
                evidence="", remediation="")
    bad = dict(good, title=None)                 # NOT NULL violation on the 2nd item
    with pytest.raises(DatabaseError):
        db.add_findings(pid, [good, bad])
    assert db.findings(pid) == []                # first item rolled back too


def test_project_creation_is_atomic(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    with pytest.raises(ValueError):
        db.create_project("P", "ftp://example.com", "A")
    assert db.projects() == []


def test_foreign_keys_enforced_and_cascade(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    with pytest.raises(DatabaseError):
        db.add_finding(424242, "t", "Low", "Low", "", "Needs review", "", "")
    pid = db.create_project("P", "https://example.com", "A")
    db.add_finding(pid, "t", "Low", "Low", "", "Needs review", "", "")
    with db.transaction():
        db.conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    assert db.conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0


def test_nested_transaction_joins_outer(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("P", "https://example.com", "A")
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.add_asset(pid, "https://a.example.com")     # own transaction() inside
            raise RuntimeError("outer fails")
    assert len(db.assets(pid)) == 1                         # inner work rolled back too


# ------------------------------------------------------------------ crash safety
def test_hard_kill_mid_transaction_leaves_no_partial_data(tmp_path):
    """A real process is killed (os._exit, no cleanup) in the middle of a transaction."""
    path = tmp_path / "crash.sqlite3"
    db = Database(path)
    pid = db.create_project("P", "https://example.com", "A")
    db.close()
    script = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(ROOT)!r})
        from core.database import Database
        db = Database({str(path)!r})
        db.conn.execute("BEGIN IMMEDIATE")
        for i in range(200):
            db.conn.execute("INSERT INTO findings(project_id,title,severity,created_at) "
                            "VALUES(?,?,?,?)", ({pid}, f"half-{{i}}", "Low", "now"))
        os._exit(137)          # simulated crash / power loss before COMMIT
    """)
    proc = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True)
    assert proc.returncode == 137, proc.stderr
    db = Database(path)
    assert db.findings(pid) == []
    assert db.integrity_check() == []


def test_committed_data_survives_hard_kill(tmp_path):
    path = tmp_path / "crash2.sqlite3"
    script = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(ROOT)!r})
        from core.database import Database
        db = Database({str(path)!r})
        pid = db.create_project("P", "https://example.com", "A")
        db.add_finding(pid, "kept", "Low", "Low", "", "Needs review", "", "")
        os._exit(137)          # killed right after COMMIT, no close()
    """)
    assert subprocess.run([sys.executable, "-I", "-c", script]).returncode == 137
    db = Database(path)
    assert [f["title"] for f in db.findings(db.projects()[0]["id"])] == ["kept"]
    assert db.integrity_check() == []


# ------------------------------------------------------------------ backup / restore
def test_backup_and_restore_roundtrip(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("P", "https://example.com", "A")
    db.add_finding(pid, "before", "Low", "Low", "", "Needs review", "", "")
    bak = db.backup_to(tmp_path / "snap" / "b.bak")
    assert db.verify_backup(bak)["integrity"] == "ok"
    db.add_finding(pid, "after", "High", "High", "", "Needs review", "", "")
    info = db.restore_from(bak)
    assert [f["title"] for f in db.findings(pid)] == ["before"]
    assert Path(info["safety_copy"]).exists()              # current data was preserved first
    assert db.integrity_check() == []
    safe = Database(info["safety_copy"])                   # ... and contains "after"
    assert {f["title"] for f in safe.findings(pid)} == {"before", "after"}


def test_restore_rejects_corrupt_and_foreign_files(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("P", "https://example.com", "A")
    garbage = tmp_path / "garbage.bak"
    garbage.write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(DatabaseError):
        db.restore_from(garbage)
    other = tmp_path / "other.db"
    c = sqlite3.connect(other); c.execute("CREATE TABLE x(a)"); c.commit(); c.close()
    with pytest.raises(DatabaseError):
        db.restore_from(other)
    with pytest.raises(DatabaseError):
        db.restore_from(tmp_path / "missing.bak")
    assert len(db.projects()) == 1 and db.assets(pid)       # live data untouched


def test_restore_of_v02_backup_is_migrated_forward(tmp_path):
    from legacy_v02 import build_v02_db
    old = tmp_path / "old_v02.sqlite3"
    pids = build_v02_db(old)
    db = Database(tmp_path / "live.sqlite3")
    db.restore_from(old)
    assert db.schema_version >= 2
    assert [a["origin"] for a in db.assets(pids[0])] == ["https://example.com"]
    assert db.integrity_check() == []


def test_restore_rejects_backup_from_newer_schema(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    bak = db.backup_to(tmp_path / "b.bak")
    c = sqlite3.connect(bak); c.execute("PRAGMA user_version=99"); c.close()
    with pytest.raises(DatabaseError):
        db.restore_from(bak)
