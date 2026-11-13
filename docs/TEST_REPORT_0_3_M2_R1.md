# Test report - Milestone 2, revision 1 (English report content fixes)

Environment: Linux sandbox, Python 3.13, reportlab 5.0.1, pytest 9.1.1, pypdf/pdfplumber.
Command: `python3 -m pytest -q`  ->  **129 executed, 129 passed, 0 failed, 0 skipped**.

| File | Tests |
|---|---|
| test_scope.py | 5 |
| test_database_migration.py | 16 |
| test_database_integrity.py | 11 |
| test_audit_chain.py | 12 |
| test_operations_and_scan.py | 18 |
| test_pdf_preflight.py | 4 |
| test_report_english.py | 15 |
| test_report_content.py (new in r1) | 23 |
| test_report_persian_plumbing.py | 10 (fake shaper + DejaVu stand-in: plumbing only) |
| test_offline_bundle_tool.py | 15 |

## r1 content fixes covered by test_report_content.py
HSTS and Server-header consistency per finding; no repeated evidence (`[xN]` collapsing);
severity counts and total; page numbers "Page n of N"; unconfirmed CVE not shown as a
definitive reference; demo data marked (banner + footer); multi-finding report with long evidence.

## NOT run / not validated
* Persian PDF: real shaping/bidi NOT validated (no Vazirmatn font, arabic-reshaper, python-bidi). `PERSIAN_PDF_VALIDATED=False`.
* Windows 10/11, PySide6 GUI, real httpx path: not run.
* Python 3.12 run of milestone 2: not run (no reportlab for 3.12 here).
* Lock file / pip-audit (item F): not started.

Sample PDF inspected visually (rendered to PNG): 3 pages, 4 findings, no repeated evidence.
