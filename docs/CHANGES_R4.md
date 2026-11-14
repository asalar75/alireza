# Changes in r4 (relative to r3, commit 0214031f355d8a9f1b0aa9824cf789573b131d81)

Purpose: prepare a reproducible Windows 10/11 x64 / CPython 3.12 validation package.
**No application code, security control, requirement or test of r3 was changed** (git diff of core/,
reporting/, ui/, app.py, requirements*.txt, pytest.ini, samples/ against r3 is empty).

Added
* `tools/validate_windows.ps1` - the Windows validation script (never executed; see limitations).
* `tools/windows_validation.py` - helper: probe / imports / guiimport / checks / junit / report.
* `docs/WINDOWS_VALIDATION.md` - how to run, step table, output, known risks.
* `docs/WINDOWS_GUI_SMOKE_TEST.md` - manual PySide6 checklist (GUI-01..07).
* `docs/WINDOWS_VALIDATION_REPORT_TEMPLATE.md` - PASS / FAIL / BLOCKED / NOT RUN template.
* `tests/test_windows_validation_tool.py` - 14 tests of the tooling (not of Windows).
* `docs/CHANGES_R4.md`, `docs/TEST_REPORT_0_3_M2_R4.md`.
Modified: `README.md` (pointer section), `.gitignore` (`.venv*/`, `validation_results/`).

Observations (no defect fixed here)
* The UI has no audit-log view; GUI-05 records that as BLOCKED and gives a substitute DB check.
* `core/database.py backup_to()` uses `os.replace` for the SQLite backup file (not PDF export);
  flagged as a Windows risk to watch, unchanged.
* The GUI always uses `%USERPROFILE%\.aegissec\aegissec.sqlite3` (no override).
* Persian PDF gate (`PERSIAN_PDF_VALIDATED=False`), dependency locking and pip-audit: untouched / not done.
