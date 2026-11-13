"""Runs a passive check as a background Operation and persists the outcome.

Thread model: the worker thread only performs the (network) check and returns observations;
all SQLite access happens on the calling thread (``start`` and ``finalize``).
"""
from __future__ import annotations

from .database import Database
from .operations import FINAL, Operation, State
from .passive_scan import run_passive_check

SCAN_TIME_LIMIT_S = 30.0   # hard ceiling for the whole operation (single GET + 12 s HTTP timeout)


class PassiveScanService:
    def __init__(self, db: Database, *, fetch=None, time_limit_s: float = SCAN_TIME_LIMIT_S):
        self.db, self.fetch, self.time_limit_s = db, fetch, time_limit_s

    def start(self, project, on_done=None) -> Operation:
        """Validate scope up front (fast, on the caller thread), record the start, spawn the worker."""
        origins = [a["origin"] for a in self.db.assets(project["id"])]
        target = project["target"]
        # Cheap pre-flight so an out-of-scope request never even becomes an operation.
        from .scope import is_in_scope
        if not is_in_scope(target, origins):
            self.db.log(project["id"], "PASSIVE_CHECK_REFUSED", f"{target} not in approved scope")
            raise PermissionError("Target origin is not in the approved scope")

        def work(op: Operation):
            op.set_progress("request in flight")
            return run_passive_check(target, origins, fetch=self.fetch, cancel=op.token)

        op = Operation("passive_https_check", work, time_limit_s=self.time_limit_s, on_done=on_done)
        self.db.start_operation(project["id"], op.status.id, op.status.name, target)
        return op.start()

    def finalize(self, project, op: Operation) -> int:
        """Persist the result. Call on the thread that owns ``db`` after the operation finished."""
        st = op.status
        if st.state not in FINAL:
            raise RuntimeError("operation not finished")
        if st.state is State.SUCCEEDED:
            with self.db.transaction():
                self.db.add_findings(project["id"], st.result)
                self.db.finish_operation(st.id, "SUCCEEDED", duration_ms=st.duration_ms,
                                         summary=f"{len(st.result)} observations")
            return len(st.result)
        self.db.finish_operation(st.id, st.state.value, duration_ms=st.duration_ms, error=st.error)
        return 0
