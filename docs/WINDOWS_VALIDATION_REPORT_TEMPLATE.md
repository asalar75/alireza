# Windows validation report - template

Copy this file, fill it in, and attach the script's `REPORT.md` and `results.json`.

## Status vocabulary (use exactly these four words)
| Status | Meaning |
|---|---|
| **PASS** | The check was executed on the stated machine and met its expected result. |
| **FAIL** | The check was executed and did not meet its expected result (give the evidence). |
| **BLOCKED** | The check could not be executed because something it needs is missing or unsupported (missing package, wrong OS/Python, file system without hard links, feature absent). Name the blocker. |
| **NOT RUN** | The check was not attempted. Nothing may be inferred from it. |

A skipped test is not a PASS. "Probably works" is not a PASS. Only executed checks may be PASS.

## Identification
| Field | Value |
|---|---|
| Report date (UTC) | |
| Tester | |
| Git commit SHA | |
| Branch | aegissec-v0.3-m2-r4 |
| Windows edition / build | |
| CPU architecture | |
| CPython version (must be 3.12.x 64-bit) | |
| Work directory and file system (e.g. C:\Users\...\Temp, NTFS, fixed drive) | |
| PowerShell version | |
| Command used | `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate_windows.ps1` |
| Script exit code | |

## Automated steps (from REPORT.md)
| Step | Status | Evidence / notes |
|---|---|---|
| env_os | | |
| env_python | | |
| venv | | |
| pip_install | | |
| imports | | |
| pytest (tests / passed / failed / errors / skipped) | | |
| compileall | | |
| gui_import | | |
| pdf_demo | | |
| pdf_local_export | | |
| pdf_no_overwrite | | |
| pdf_concurrent | | |
| pdf_cleanup | | |

## Manual GUI smoke test (docs/WINDOWS_GUI_SMOKE_TEST.md)
| Item | Status | Notes |
|---|---|---|
| GUI-01 startup | | |
| GUI-02 main window rendering | | |
| GUI-03 project creation and reopening | | |
| GUI-04 scope validation | | |
| GUI-05 audit log visibility (UI) / substitute DB check | | |
| GUI-06 PDF export and error display | | |
| GUI-07 shutdown | | |

## Items explicitly NOT covered by this report
| Item | Status |
|---|---|
| Persian PDF validation (font, shaping, RTL, 12-point checklist) | NOT RUN |
| Dependency lock file and pip-audit | NOT RUN |
| EXE build / installer / signing | NOT RUN |
| Passive HTTPS scan against a real target | NOT RUN |

## Overall result
* Automated part: PASS / FAIL / BLOCKED / NOT RUN
* GUI part: PASS / FAIL / BLOCKED / NOT RUN
* Windows validation of this commit: **PASSED only if both parts are PASS**; otherwise OPEN.

## Defects found (report before fixing)
| # | Description | Evidence | Severity |
|---|---|---|---|
