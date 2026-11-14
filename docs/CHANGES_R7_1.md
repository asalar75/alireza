# Changes in r7-1 (relative to r7, commit 98c6d04d9a44c6a6b2c6b755ff9d2c77ee9b8a0d)

Defect: the R7 PowerShell script protected new files with `Test-Path` followed by `File.WriteAllText`, and
`Start-Process -RedirectStandardOutput/-RedirectStandardError` opened its target by itself. Both leave a
time-of-check/time-of-use window in which a file that appears can be overwritten.

* `tools/validate_windows.ps1`
  * New helpers (`# BEGIN/END EXCLUSIVE-IO`): `Open-NewFileStream` (`FileMode.CreateNew`, `FileShare.Read`) and
    `Set-OwnedContent` (writes through a handle this run owns; shortens only after writing).
  * `results.json`: created once, exclusively, handle held for the whole run, updated only through it, closed
    before `REPORT.md` is rendered. `Write-Text`/`-AllowRewrite` removed.
  * `Invoke-Logged`: no `Start-Process`; the three log files are created exclusively before the command runs; the
    command output is captured in memory via `System.Diagnostics.Process` and written through those handles;
    process and handles are disposed in `finally`. If a log name exists the command is not run.
  * pytest JUnit file name carries a GUID.
* `tools/windows_validation.py`: `write_new` encodes first, then creates with `"xb"` (no pre-check, handle closed).
* Tests: `tests/test_windows_validation_exclusive_io.py` (new, 20); two R7 static tests adapted
  (`tests/test_windows_validation_outputs.py`).
* Docs: `docs/WINDOWS_VALIDATION.md`, `docs/TEST_REPORT_0_3_M2_R7_1.md`, this file, `STATUS.md`.

Not changed: application code, PDF publishing (R3 fail-closed), audit chain, `PERSIAN_PDF_VALIDATED=False`,
requirements, R6, R7, `main`, `master`. Nothing was deleted or merged.

Known limits: no delete is ever performed, so a log file reserved before a failure remains as an empty file;
pytest's own JUnit XML is protected by a unique name, not by file-level exclusive creation.
