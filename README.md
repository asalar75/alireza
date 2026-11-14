# AegisSec Enterprise v0.3 (milestone 1 - work in progress)

Bilingual Windows desktop starter for authorized security assessment.

## New in 0.3 (milestone 1)
- Fixed: a new project's target was never recorded as an asset (v0.2 `INSERT OR IGNORE` swallowed a NOT NULL error)
- Versioned, transactional SQLite migrations with automatic pre-migration backup; v0.2 data is repaired
- Transactions with rollback, WAL + synchronous=FULL, verified backup/restore (`Database.backup_to/restore_from`)
- Hash-chained, append-only audit log with actor; `Database.verify_audit()` (limits: docs/MIGRATION_0_2_to_0_3.md)
- Passive check runs off the UI thread with cancel, time limit, persisted status/duration
- Milestone 2 (in progress): new report engine (English complete and tested; Persian code ready but **refused until validated** - needs Vazirmatn font + arabic-reshaper + python-bidi, see docs/OFFLINE_DEPENDENCIES.md and docs/PERSIAN_PDF_VALIDATION.md)
- NOT yet done: validated Persian PDF, dependency lock/audit (F), Windows validation. See docs/TEST_REPORT_0_3.md and docs/TEST_REPORT_0_3_M2.md

## Implemented (from 0.2)
- Persian/English UI language switch
- Project records with authorization reference
- Explicit origin allowlist and asset inventory
- Exact-origin passive HTTPS header/TLS-observation check (no redirects)
- Manual finding workflow with severity, confidence, status, evidence and remediation
- SQLite persistence and audit log
- JSON report export
- PDF report export
- Scope validation tests

## Safety boundaries
Only assess systems for which you have written authorization. The scanner in this release
makes one ordinary GET request to an explicitly allowlisted HTTPS origin, does not follow
redirects, does not submit forms, does not authenticate, does not exploit, and does not
enumerate arbitrary ports or subdomains. A missing header is an observation, not proof of
an exploitable vulnerability. Findings require analyst validation.

## Install (Windows 10/11)
Python 3.12:
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python app.py
```

## Tests
```powershell
python -m pytest -q
```

## Windows validation (prepared, NOT yet executed on Windows)
See `docs/WINDOWS_VALIDATION.md`. Run on Windows 10/11 x64 with CPython 3.12:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate_windows.ps1
```
Manual GUI checklist: `docs/WINDOWS_GUI_SMOKE_TEST.md`; report template: `docs/WINDOWS_VALIDATION_REPORT_TEMPLATE.md`.

## Build EXE
```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name AegisSec app.py
```
The executable is placed in `dist\\AegisSec\\` (one-folder build).

## Next engineering gates before 1.0
- Automated integration tests on supported Windows versions
- Code signing and installer
- Dependency/license review and software bill of materials
- Secure update mechanism with signature verification
- External penetration test of AegisSec itself
- Separate, opt-in integrations for vetted scanners with strict scope enforcement
