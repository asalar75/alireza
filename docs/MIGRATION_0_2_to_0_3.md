# Upgrading a v0.2 database to v0.3

Automatic: opening a v0.2 database with v0.3 applies migrations 1-4 in order.

| # | Migration | Effect |
|---|-----------|--------|
| 1 | baseline | Idempotent v0.2 schema + `schema_migrations` table (no change to existing data). |
| 2 | asset defaults + repair | Rebuilds `assets` with a default for `created_at` (root cause of the target-asset bug). For every project whose target origin is missing from `assets`, inserts it (note: *restored by migration 0002*) and audits it. Invalid legacy targets are **not** inserted; they are listed in `schema_migrations.notes` and audited as `MIGRATION_TARGET_SKIPPED` for manual review. |
| 3 | audit hash chain | Rebuilds `audit` with `actor`, `prev_hash`, `entry_hash`; back-fills the chain over existing rows (actor `legacy-v0.2`); adds append-only triggers and FK indexes. |
| 4 | operations | Adds the `operations` table (state, timing, outcome of background operations). |

Each migration runs in one `BEGIN IMMEDIATE` transaction together with its `user_version`
bump; failure rolls everything back. Foreign keys are re-checked before commit.

## Rollback path
Before the first pending migration, a verified copy is written to
`~/.aegissec/backups/<db>.pre-vN-to-vM.<UTC timestamp>.bak`. To go back to v0.2:
close AegisSec, copy that `.bak` over `~/.aegissec/aegissec.sqlite3`
(delete `aegissec.sqlite3-wal` / `-shm` next to it), start v0.2.
A database whose schema is newer than the app is refused, never modified.

## Scope note on repaired assets
The restored asset is the project's own target, which the analyst entered together with the
written-authorisation reference. It re-establishes the original intent and does not widen
the scope. Review the audit entries `ASSET_RESTORED_BY_MIGRATION` if you want to confirm.

## Audit-log limits
See `core/audit.py`. The hash chain is unkeyed: it detects accidental or partial tampering,
NOT a privileged user who recomputes all hashes, and it cannot see deletion of the newest
entries unless you recorded `Database.audit_head()` elsewhere. Entries written before
migration 3 were never protected.
