# Test report - Milestone 2, revision 3

Environment: Linux sandbox, Python 3.13.18 (`python3 -V`), pytest, reportlab 5.0.1.
Commands: `python3 -m pytest -q tests/test_export_safety.py` ; `python3 -m pytest -q`
Result (full suite): **188 executed, 188 passed, 0 failed, 0 skipped.**
test_export_safety.py: 22 passed (parametrised errno cases included).

NOT run: Python 3.12; Windows 10/11 (NTFS hard-link behaviour unverified); PySide6 GUI;
real Persian PDF validation; lock file / pip-audit.
Limitation: where hard links are unavailable, PDF export refuses (by design) instead of replacing.
