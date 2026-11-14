# Test report - Milestone 2, revision 7.1

Environment: Linux 6.18.44, Python 3.13.18, pytest 9.1.1. PowerShell is NOT installed here.
Windows execution: **NOT PERFORMED**. PowerShell execution: **NOT PERFORMED**.

Commands (Linux)
* `python3 -m pytest -q -p no:cacheprovider -rs` -> **275 collected: 266 passed, 0 failed, 9 skipped**
  (r7: 255; +20 in tests/test_windows_validation_exclusive_io.py). The 9 skips are all PowerShell-runtime tests
  (6 new + 3 from R7): NOT RUN.
* `python3 -m compileall -q -f app.py core reporting ui tools tests` -> exit 0.

Evidence, kept apart
| Kind | Tests | Result |
|---|---|---|
| STATIC - PowerShell text inspected, not executed (CreateNew is the only FileMode; no Test-Path guard on writes; no redirect cmdlets, bulk writers, delete/rename/replace; logs reserved before the command and released in finally; results.json created once, owned, written only through its handle and closed before the report; unique JUnit name) | 6 | 6 passed |
| PYTHON - really executed (existing file preserved with bytes/size/mtime; collision between pre-check and write; foreign checks.json appearing during checks; 12 threads and 6 separate processes racing on one file: exactly one wins, no interleaving; unencodable content creates nothing; handle closed when the write fails; report failure creates no file) | 8 | 8 passed |
| POWERSHELL RUNTIME - script functions really executed (existing file; owned-stream rewrite; 6 concurrent pwsh processes; existing stdout log; existing stderr log + released handles; normal stdout/stderr/log publishing) | 6 | **6 SKIPPED - NOT RUN** |

Not covered by any executed test: results.json exclusive creation and the Invoke-Logged logic in PowerShell
(only statically inspected here); stdout/stderr log preservation (PowerShell-only feature, no Python analogue).
The PowerShell code of R7.1 has therefore NEVER been executed. Expect the first run in PowerShell to be able to
reveal script bugs (tooling defects, not product results).

Mutation checks: changing `CreateNew` to `Create` fails the static test; replacing the exclusive create in
`write_new` by exists()+write fails the collision and thread-race tests. Both restored.

NOT RUN: validate_windows.ps1, anything on Windows/NTFS, GUI smoke test, Python 3.12.
NOT VALIDATED: Persian PDF. NOT DONE: dependency lock, pip-audit.
