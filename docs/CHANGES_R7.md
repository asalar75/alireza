# Changes in r7 (relative to r6, commit bcfc133001ce4563aed76d6fd4c6772def9f1854)

Goal: a re-run of the Windows validation script must never overwrite or reuse an earlier run's output.

* `tools/validate_windows.ps1`
  * Pre-flight before any write: existing `-OutDir` -> `REFUSED`, exit 2; existing
    `.venv-validate-<RunId>` -> `REFUSED`, exit 2 (never reused, cleaned or deleted).
  * OutDir and the venv folder are created with `New-Item ... -ErrorAction Stop`, no Force switch.
  * New parameter `-RunId` (validated `^[A-Za-z0-9._-]{1,40}$`) names both folders (default: UTC timestamp).
  * `Write-Text` and the redirected log files refuse to overwrite existing files; only this run's own
    `results.json` may be rewritten.
* `tools/windows_validation.py`: `checks.json` and `REPORT.md` are created exclusively (`open(..., "x")`);
  an existing file -> exit 2, content untouched; `checks` refuses before running anything.
* Tests: `tests/test_windows_validation_outputs.py` (new, 12); `tests/test_windows_validation_tool.py`
  one assertion updated (the Force switch now appears nowhere in the script).
* Docs: `docs/WINDOWS_VALIDATION.md`, `docs/TEST_REPORT_0_3_M2_R7.md`, this file, `STATUS.md`.

Not changed: application code, PDF publisher (R3 fail-closed), audit chain, Persian gate
(`PERSIAN_PDF_VALIDATED=False`), requirements, `NEXT.md`. No merge; `main` and `master` untouched.
