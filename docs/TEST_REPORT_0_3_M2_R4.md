# Test report - Milestone 2, revision 4 (Windows validation preparation)

## LINUX results (the only results that exist)
Environment: Linux (kernel 6.18), Python 3.13.18, filesystem ext2/ext3 family (stat -f), reportlab 5.0.1,
pytest 9.1.1. Windows: **NOT RUN**. Python 3.12: **NOT RUN**.

Commands and results
* `python3 -m pytest -q -p no:cacheprovider` -> **202 executed, 202 passed, 0 failed, 0 skipped**
  (r3 had 188; +14 new in `tests/test_windows_validation_tool.py`).
* `python3 -m pytest -q tests/test_windows_validation_tool.py` -> 14 passed.
* `python3 -m compileall -q -f app.py core reporting ui tools tests` -> exit 0.
* Dry run of the PDF checks (NOT a Windows validation):
  `python3 -I tools/windows_validation.py checks --out <dir> --allow-non-windows --rounds 2 --procs 4`
  -> pdf_demo, pdf_local_export, pdf_no_overwrite, pdf_concurrent (4 procs x 2 rounds: 1 ok + 3
  FileExistsError each), pdf_cleanup: all PASS **on Linux**.

## WINDOWS results
| Item | Status |
|---|---|
| tools/validate_windows.ps1 executed | **NOT RUN** (no Windows, no PowerShell in the sandbox; only statically checked: ASCII, bracket balance, step ids, no overwrite-capable commands) |
| pytest suite on Windows | NOT RUN |
| compileall on Windows | NOT RUN |
| PDF export / no-overwrite / concurrency / cleanup on NTFS | NOT RUN |
| PySide6 import and GUI smoke test | NOT RUN |
| Python 3.12 | NOT RUN |
| Persian PDF | NOT VALIDATED |
| Dependency lock / pip-audit | NOT DONE |

The PowerShell script is untested code: expect that a first Windows run may reveal script bugs. Any such
bug must be reported as a tooling defect, not as a product result.
