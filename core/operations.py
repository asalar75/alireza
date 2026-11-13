"""Long-running operations, kept out of the UI thread.

Pure standard-library (threading) so it is unit-testable without Qt; ``ui/workers.py``
adapts it to Qt signals. Rules:

* The worker thread must NOT touch the SQLite connection (``sqlite3`` connections are
  bound to their creating thread). Workers only compute and return data; persistence is
  done by the caller thread in the completion handler.
* Cancellation is cooperative (``CancelToken``). A request that is already in flight cannot
  be aborted, so on cancel/time-out the operation is reported CANCELLED immediately and
  the late result is discarded. Network calls keep their own finite timeouts.
* Every operation has a hard time limit; there is no unbounded run.
"""
from __future__ import annotations

import enum
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


class OperationCancelled(Exception):
    pass


class State(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


FINAL = {State.SUCCEEDED, State.FAILED, State.CANCELLED}


class CancelToken:
    def __init__(self):
        self._ev = threading.Event()
        self.reason = ""

    def cancel(self, reason="cancelled by analyst"):
        if not self._ev.is_set():
            self.reason = reason
            self._ev.set()

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()

    def raise_if_cancelled(self):
        if self._ev.is_set():
            raise OperationCancelled(self.reason)


@dataclass
class OperationStatus:
    id: str
    name: str
    state: State = State.PENDING
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    error: str = ""
    result: Any = None
    progress: str = ""


class Operation:
    def __init__(self, name: str, fn: Callable[["Operation"], Any], *, time_limit_s: float = 60.0,
                 on_done: Optional[Callable[["Operation"], None]] = None):
        if time_limit_s <= 0:
            raise ValueError("time_limit_s must be positive")
        self.token = CancelToken()
        self.status = OperationStatus(id=uuid.uuid4().hex, name=name)
        self._fn, self._limit, self._on_done = fn, time_limit_s, on_done
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._t0 = 0.0
        self._timer: Optional[threading.Timer] = None
        self._thread: Optional[threading.Thread] = None

    # -- control ---------------------------------------------------------------
    def start(self) -> "Operation":
        with self._lock:
            if self.status.state is not State.PENDING:
                raise RuntimeError("operation already started")
            self.status.state = State.RUNNING
        self._t0 = time.monotonic()
        self.status.started_at = datetime.now(timezone.utc).isoformat()
        self._timer = threading.Timer(self._limit, self._expire)
        self._timer.daemon = True
        self._timer.start()
        self._thread = threading.Thread(target=self._run, name=f"op-{self.status.name}", daemon=True)
        self._thread.start()
        return self

    def cancel(self, reason="cancelled by analyst"):
        self.token.cancel(reason)
        self._finish(State.CANCELLED, error=reason)

    def _expire(self):
        reason = f"time limit of {self._limit:g}s exceeded"
        self.token.cancel(reason)
        self._finish(State.CANCELLED, error=reason)

    def set_progress(self, text: str):
        self.status.progress = text

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self._done.wait(timeout)

    # -- internals ---------------------------------------------------------------
    def _run(self):
        try:
            self.token.raise_if_cancelled()
            result = self._fn(self)
            self.token.raise_if_cancelled()
            self._finish(State.SUCCEEDED, result=result)
        except OperationCancelled as exc:
            self._finish(State.CANCELLED, error=str(exc))
        except BaseException as exc:  # noqa: BLE001 - report every failure, never crash the app
            self._finish(State.FAILED, error=f"{type(exc).__name__}: {exc}",
                         detail=traceback.format_exc())

    def _finish(self, state: State, *, result=None, error="", detail=""):
        with self._lock:                      # first terminal state wins; late results are discarded
            if self.status.state in FINAL:
                return
            self.status.state = state
            self.status.result = result if state is State.SUCCEEDED else None
            self.status.error = error
            self.status.finished_at = datetime.now(timezone.utc).isoformat()
            self.status.duration_ms = int((time.monotonic() - self._t0) * 1000)
            self._detail = detail
        if self._timer:
            self._timer.cancel()
        self._done.set()
        if self._on_done:
            try:
                self._on_done(self)
            except Exception:  # a broken callback must not break the operation
                traceback.print_exc()
