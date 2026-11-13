import threading
import time

import pytest

from core.database import Database
from core.operations import Operation, State, OperationCancelled
from core.passive_scan import Response, run_passive_check
from core.scan_service import PassiveScanService


def wait_done(op, t=5):
    assert op.wait(t), "operation did not finish"


# ------------------------------------------------------------- Operation
def test_success_records_result_and_timing():
    op = Operation("x", lambda o: 42).start()
    wait_done(op)
    assert op.status.state is State.SUCCEEDED and op.status.result == 42
    assert op.status.duration_ms is not None and op.status.finished_at


def test_failure_is_captured_not_raised():
    def boom(o): raise ValueError("bad")
    op = Operation("x", boom).start(); wait_done(op)
    assert op.status.state is State.FAILED and "ValueError: bad" in op.status.error


def test_cancel_returns_immediately_and_discards_late_result():
    release = threading.Event()
    def slow(o):
        release.wait(5)
        return "late"
    op = Operation("x", slow).start()
    t0 = time.monotonic()
    op.cancel()
    assert time.monotonic() - t0 < 0.5
    assert op.status.state is State.CANCELLED
    release.set(); time.sleep(0.1)
    assert op.status.state is State.CANCELLED and op.status.result is None


def test_cooperative_cancel_inside_worker():
    started = threading.Event()
    def loop(o):
        started.set()
        while True:
            o.token.raise_if_cancelled(); time.sleep(0.01)
    op = Operation("x", loop).start(); started.wait(1); op.cancel("stop"); wait_done(op)
    assert op.status.state is State.CANCELLED and op.status.error == "stop"


def test_time_limit_cancels():
    op = Operation("x", lambda o: time.sleep(2), time_limit_s=0.1).start(); wait_done(op)
    assert op.status.state is State.CANCELLED and "time limit" in op.status.error


def test_on_done_called_once_and_callback_errors_isolated():
    calls = []
    def cb(op): calls.append(op.status.state); raise RuntimeError("cb bug")
    op = Operation("x", lambda o: 1, on_done=cb).start(); wait_done(op); time.sleep(0.05)
    assert calls == [State.SUCCEEDED]


def test_cannot_start_twice_or_with_bad_limit():
    op = Operation("x", lambda o: 1).start()
    with pytest.raises(RuntimeError): op.start()
    with pytest.raises(ValueError): Operation("x", lambda o: 1, time_limit_s=0)


def test_ui_thread_not_blocked_while_worker_runs():
    release = threading.Event()
    op = Operation("x", lambda o: release.wait(5)).start()
    t0 = time.monotonic()
    for _ in range(1000):          # the "UI thread" stays free to do work
        pass
    assert time.monotonic() - t0 < 0.5 and op.status.state is State.RUNNING
    release.set(); wait_done(op)


# ------------------------------------------------------------- passive scan (no network)
def fake(headers, status=200, redirect=False):
    return lambda origin: Response(status, headers, redirect)


def test_scan_out_of_scope_never_calls_network():
    called = []
    with pytest.raises(PermissionError):
        run_passive_check("https://evil.example", ["https://example.com"],
                          fetch=lambda o: called.append(o))
    assert called == []


def test_scan_requires_https():
    with pytest.raises(ValueError):
        run_passive_check("http://example.com", ["http://example.com"], fetch=fake({}))


def test_scan_reports_missing_headers_and_redirect_without_following():
    seen = []
    def f(origin):
        seen.append(origin)
        return Response(301, {"Server": "nginx/1.2", "Location": "https://other.example/"}, True)
    out = run_passive_check("https://example.com/", ["https://example.com"], fetch=f)
    titles = {o["title"] for o in out}
    assert seen == ["https://example.com"]                       # exactly one request
    assert "HSTS header not observed" in titles
    assert "Server response header disclosed" in titles
    assert "Redirect observed; destination not followed" in titles
    redir = next(o for o in out if o["title"].startswith("Redirect"))
    assert "other.example" in redir["evidence"]


def test_scan_present_headers_not_reported():
    h = {"strict-transport-security": "x", "content-security-policy": "x",
         "x-content-type-options": "nosniff", "referrer-policy": "x", "permissions-policy": "x"}
    assert run_passive_check("https://example.com", ["https://example.com"], fetch=fake(h)) == []


def test_scan_honours_cancel_token():
    from core.operations import CancelToken
    t = CancelToken(); t.cancel()
    with pytest.raises(OperationCancelled):
        run_passive_check("https://example.com", ["https://example.com"], fetch=fake({}), cancel=t)


# ------------------------------------------------------------- service + persistence
@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / "a.sqlite3", actor="alice")
    pid = db.create_project("P", "https://example.com", "AUTH")
    return db, db.projects()[0]


def test_service_success_persists_findings_operation_and_audit(setup):
    db, proj = setup
    svc = PassiveScanService(db, fetch=fake({"server": "x"}))
    op = svc.start(proj); wait_done(op)
    n = svc.finalize(proj, op)
    assert n == len(db.findings(proj["id"])) > 0
    row = db.operations(proj["id"])[0]
    assert row["state"] == "SUCCEEDED" and row["duration_ms"] is not None
    actions = [a["action"] for a in db.audit_entries(proj["id"])]
    assert "OPERATION_STARTED" in actions and "OPERATION_SUCCEEDED" in actions
    assert db.verify_audit().ok


def test_service_refuses_out_of_scope_and_audits(setup):
    db, proj = setup
    with db.transaction():
        db.conn.execute("DELETE FROM assets WHERE project_id=?", (proj["id"],))
    svc = PassiveScanService(db, fetch=fake({}))
    with pytest.raises(PermissionError):
        svc.start(proj)
    assert db.operations(proj["id"]) == []
    assert any(a["action"] == "PASSIVE_CHECK_REFUSED" for a in db.audit_entries(proj["id"]))


def test_service_cancel_leaves_no_findings(setup):
    db, proj = setup
    release = threading.Event()
    svc = PassiveScanService(db, fetch=lambda o: (release.wait(5), Response(200, {}, False))[1])
    op = svc.start(proj); op.cancel(); wait_done(op)
    assert svc.finalize(proj, op) == 0
    release.set(); time.sleep(0.1)
    assert db.findings(proj["id"]) == []
    assert db.operations(proj["id"])[0]["state"] == "CANCELLED"


def test_service_failure_is_recorded(setup):
    db, proj = setup
    def bad(o): raise ConnectionError("tls handshake failed")
    svc = PassiveScanService(db, fetch=bad)
    op = svc.start(proj); wait_done(op); svc.finalize(proj, op)
    row = db.operations(proj["id"])[0]
    assert row["state"] == "FAILED" and "tls handshake failed" in row["error"]


def test_running_operation_is_marked_interrupted_after_crash(tmp_path):
    p = tmp_path / "a.sqlite3"
    db = Database(p)
    pid = db.create_project("P", "https://example.com", "A")
    db.start_operation(pid, "op1", "passive_https_check")
    db.close()                                   # app "crashed" while running
    db2 = Database(p)
    assert db2.interrupted_operations == 1
    assert db2.operations(pid)[0]["state"] == "INTERRUPTED" and db2.verify_audit().ok
