# Changes in r5 (relative to r4, commit c878db314fac751aca30ab01651a28b24d66dffe)

Defect fixed: `tools/validate_windows.ps1` recorded `mode = 'WINDOWS'` but never `is_windows`, while
`build_report()` decides on `meta["is_windows"]`; a real Windows run could therefore be reported as a
non-Windows dry run.

* `tools/validate_windows.ps1`: `is_windows` is recorded explicitly: `$false` at start (mode
  `UNCONFIRMED`), `$false` on the non-Windows path, and `$true` (mode `WINDOWS`) only after the Windows
  10/11 client check and the x64 check have both succeeded, before the `env_os` PASS step.
  A host that fails those checks (Windows Server, ARM64, ...) keeps `is_windows = $false`.
* `tools/windows_validation.py` `build_report()`: fail closed. Windows is recognised only for a literal
  JSON `true` and a mode that is not DRY-RUN / NOT WINDOWS / UNCONFIRMED. Missing, null, "true", 1 etc.
  never give a Windows verdict. The banner says why (missing field, inconsistent mode, or dry-run/blocked).
  New verdict line: an automated PASS says nothing about the manual GUI checklist, Persian PDF,
  dependency locking or pip-audit (those lines remain NOT RUN / NOT VALIDATED / NOT DONE).
* `tests/test_windows_validation_tool.py`: 14 -> 34 tests (is_windows true/false/missing, non-boolean values,
  inconsistent modes, blocked step, BOM-prefixed results file, honesty lines, static ordering checks on the
  PowerShell script).
* `docs/WINDOWS_VALIDATION_REPORT_TEMPLATE.md`: branch name field updated to r5.

Not changed: application code, security controls, R3 fail-closed PDF publishing, `PERSIAN_PDF_VALIDATED`
(False), requirements. R4 and main are untouched.
