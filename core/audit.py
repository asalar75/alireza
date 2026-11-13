"""Tamper-evident audit log: SHA-256 hash chain.

Each entry stores ``prev_hash`` (the previous entry's ``entry_hash``, or GENESIS for the
first) and ``entry_hash = SHA256(canonical_json([prev_hash, project_id, action, details,
created_at, actor]))``. Editing, deleting from the middle, inserting or reordering entries
breaks the chain and is reported by :func:`verify_chain`.

LIMITS (by design, also documented in the README):
* The hash is NOT keyed. Anyone who can write the SQLite file (e.g. a local administrator)
  can edit an entry and recompute every later hash; the chain then verifies. It detects
  accidental corruption and casual or partial tampering, not a determined privileged attacker.
* Deleting the newest entries (truncating the tail) leaves a valid chain. Record the head
  hash/count externally (``Database.audit_head()``; it is also included in exports) and
  pass them as ``expected_head`` / ``expected_count`` to detect that.
* Entries written before migration 3 (v0.2 and earlier) were unprotected; the chain proves
  integrity only from the migration onwards. They are marked actor ``legacy-v0.2``.
* The append-only triggers stop accidental or application-level UPDATE/DELETE, nothing more.
Stronger options (HMAC with a DPAPI-protected key, external timestamping/WORM storage) are
planned for the data-security release.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

GENESIS = "0" * 64
LEGACY_ACTOR = "legacy-v0.2"


def local_actor() -> str:
    """OS account of the person running the app (single-user now; multi-user ready)."""
    try:
        return getpass.getuser()
    except Exception:  # no usable environment/pwd entry
        return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"


def entry_hash(prev_hash: str, project_id, action: str, details: str,
               created_at: str, actor: str) -> str:
    payload = json.dumps([prev_hash, project_id, action, details, created_at, actor],
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class AuditVerification:
    ok: bool
    checked: int
    head: str
    problems: list[str] = field(default_factory=list)
    first_bad_id: Optional[int] = None


def verify_chain(conn: sqlite3.Connection, *, expected_head: Optional[str] = None,
                 expected_count: Optional[int] = None) -> AuditVerification:
    problems: list[str] = []
    first_bad: Optional[int] = None
    prev = GENESIS
    count = 0
    rows = conn.execute(
        "SELECT id,project_id,action,details,created_at,actor,prev_hash,entry_hash "
        "FROM audit ORDER BY id").fetchall()

    def bad(rid, msg):
        nonlocal first_bad
        if first_bad is None:
            first_bad = rid
        problems.append(f"entry {rid}: {msg}")

    for r in rows:
        count += 1
        if r["prev_hash"] != prev:
            bad(r["id"], "chain broken (entry removed, inserted or reordered before this one)")
        recomputed = entry_hash(r["prev_hash"], r["project_id"], r["action"], r["details"],
                                r["created_at"], r["actor"])
        if recomputed != r["entry_hash"]:
            bad(r["id"], "content does not match its hash (entry modified)")
        prev = r["entry_hash"]
    if expected_count is not None and expected_count != count:
        problems.append(f"expected {expected_count} entries, found {count} (entries removed or added)")
    if expected_head is not None and expected_head != prev:
        problems.append("head hash differs from the externally recorded value")
    return AuditVerification(ok=not problems, checked=count, head=prev,
                             problems=problems, first_bad_id=first_bad)
