# AegisSec 0.3 - test report (milestone 1: items A, B, C, E-core)

Run in a Linux sandbox. Command: `python -I -m pytest -q -p no:cacheprovider tests`

| Environment | Executed | Passed | Failed | Skipped/not run |
|-------------|---------:|-------:|-------:|----------------:|
| Python 3.13.18 (SQLite 3.53.1) | 62 | 62 | 0 | 0 |
| Python 3.12.3 (pytest borrowed from the 3.13 environment) | 62 | 62 | 0 | 0 |

Suites: scope (5, from v0.2), migration + regression (16), integrity/crash/backup (11),
audit chain (12), operations + passive scan + service (18).

## NOT executed / NOT done (explicit)
* **Windows 10/11:** not available. Nothing was run on Windows.
* **PySide6 UI** (`ui/main_window.py`, `ui/workers.py`): PySide6 is not installed in the sandbox
  and cannot be installed (no network). Files were only syntax-checked (`py_compile`).
  Acceptance criterion 6 (UI does not freeze) is therefore verified for the *core*
  (`Operation`, `PassiveScanService`) and **not** end-to-end in the GUI.
* **Real HTTPS request path** (`httpx_fetch`): httpx is not installed; the check logic is tested
  with an injected fake fetch only.
* **D - Persian PDF: NOT implemented.** Needs `arabic-reshaper` + `python-bidi` + the Vazirmatn
  font file (not installable/downloadable here) or a Qt-based renderer. The v0.2 exporter is
  unchanged. Vazirmatn license (SIL OFL 1.1) must be checked and its text shipped when it is bundled.
* **F - dependency pinning / lock file / vulnerability audit: NOT done.** Needs network access to
  resolve versions (`pip-compile --generate-hashes`) and `pip-audit`. Coverage tooling
  (`coverage`, `pytest-cov`) is also unavailable, so no coverage figure is claimed.
* Tests that kill a process (`os._exit`) simulate a crash; they are not real power-loss tests.
