# Test report - Milestone 2, revision 2

Environment: Linux sandbox, Python 3.13.18. Command: `python3 -m pytest -q`
Result: **178 executed, 178 passed, 0 failed, 0 skipped.**

New tests (run separately): test_scope_origin.py 37 passed; test_export_safety.py 12 passed.
(Symlink test would skip where symlinks are unavailable; it ran here.)

| File | Tests |
|---|---|
| test_scope.py | 5 |
| test_scope_origin.py (new) | 37 |
| test_export_safety.py (new) | 12 |
| test_database_migration.py | 16 |
| test_database_integrity.py | 11 |
| test_audit_chain.py | 12 |
| test_operations_and_scan.py | 18 |
| test_pdf_preflight.py | 4 |
| test_report_english.py | 15 |
| test_report_content.py | 23 |
| test_report_persian_plumbing.py | 10 (stand-ins; plumbing only) |
| test_offline_bundle_tool.py | 15 |

NOT run: Python 3.12 (interpreter present, but no pytest/reportlab and no network); Windows 10/11
(including NTFS/hard-link and concurrent-export behaviour there); PySide6 GUI; real Persian PDF
validation (no font/wheels); lock file and pip-audit.
