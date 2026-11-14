# Test report - Milestone 2, revision 7

Environment: Linux 6.18.44, Python 3.13.18, pytest 9.1.1. PowerShell is NOT installed here.
Windows execution: **NOT PERFORMED**.

Commands (Linux)
* `python3 -m pytest -q -p no:cacheprovider -rs` -> **255 collected: 252 passed, 0 failed, 3 skipped**
  (r6: 243; +12 in tests/test_windows_validation_outputs.py).
* `python3 -m compileall -q -f app.py core reporting ui tools tests` -> exit 0.

Evidence, kept apart
| Kind | Tests | Result |
|---|---|---|
| STATIC (PowerShell text inspected, not executed) | 5 (preflight order, no Force/delete/rename/replace commands, write guards, RunId) | 5 passed |
| PYTHON (really executed: write_new, report, checks refuse existing files; before/after SHA-256, size, mtime) | 4 | 4 passed |
| POWERSHELL RUNTIME (script really executed: existing OutDir, existing venv, invalid RunId) | 3 | **3 SKIPPED - NOT RUN (no pwsh/powershell)** |

Mutation checks: re-adding `-Force` to the OutDir `New-Item` fails 2 static tests; changing `write_new`
from exclusive create to overwrite fails the Python test; both restored.

The 3 PowerShell runtime tests will execute automatically wherever PowerShell exists (including the
Windows validation run). Until then the PowerShell refusal behaviour is UNVERIFIED by execution.
NOT RUN: validate_windows.ps1, Windows/NTFS, GUI smoke test, Python 3.12. NOT VALIDATED: Persian PDF.
NOT DONE: dependency lock, pip-audit.
