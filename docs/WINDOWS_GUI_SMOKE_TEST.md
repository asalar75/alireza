# Manual GUI smoke test - Windows 10/11 x64, PySide6

Not executed by any script. Record each item as **PASS**, **FAIL**, **BLOCKED** or **NOT RUN**
(definitions in `WINDOWS_VALIDATION_REPORT_TEMPLATE.md`). Never write PASS for something you did not do.

Before you start
* Use the virtual environment from the automated run: `.venv-validate-<timestamp>\Scripts\Activate.ps1`.
* The app stores data in `%USERPROFILE%\.aegissec\aegissec.sqlite3` and there is no override. Use a test
  Windows user, or copy that file elsewhere first if you already use the app.
* Use only the demo target `https://example.com` and the local-address examples below as scope text.
  **Do not press "Run passive HTTPS checks"** in this smoke test unless the target is yours or you have
  written authorization; it sends real requests.
* Machine / user / date / commit SHA: ______________________

## GUI-01 Application startup
1. `python app.py` from the project folder.
Expected: a window titled/branded AEGISSEC ENTERPRISE opens within a few seconds; no console traceback;
no error dialog. Status: ____ Notes: ____

## GUI-02 Main window rendering
1. Check header, project list (left), tabs "Findings" and "Assets", buttons.
2. Click the language button; check Persian layout (right-to-left, Persian text readable, no clipped
   buttons). Click again to return to English.
3. Resize and maximise the window.
Expected: all controls visible and readable in both languages; no overlapping or clipped text.
Status: ____ Notes (screenshots): ____

## GUI-03 Project creation and reopening
1. "New project": name `Smoke Test`, origin `https://example.com`, authorization `SMOKE-TEST-0001`.
2. Select the project; open the Assets tab.
3. Close the app (GUI-07) and start it again.
Expected: the project appears; the Assets tab lists `https://example.com` (regression check for the v0.2
target-asset bug); after restart the project is still listed and selectable.
Status: ____ Notes: ____

## GUI-04 Scope validation
Create projects (or try to) with these origins; empty authorization must also be tried.
| Input | Expected |
|---|---|
| `https://example.com` | accepted |
| `https://Example.COM:443` | accepted, shown as `https://example.com` |
| `https://example.com:8443` | accepted, port kept |
| `https://[::1]` | accepted, shown with brackets `https://[::1]` (a private address is allowed only because you typed it as scope) |
| `https://example.com/admin` | rejected: "Invalid origin" warning |
| `https://example.com/?a=1` | rejected |
| `https://user:pw@example.com` | rejected (credentials) |
| `ftp://example.com` | rejected |
| `https://example.com:99999` | rejected |
| `https://[::1` | rejected |
| valid origin, empty authorization | rejected: "Authorization required" |
Status: ____ Notes: ____

## GUI-05 Audit log visibility
At this commit the UI has **no audit-log view** (only Findings and Assets tabs). Record that as
**BLOCKED** (feature absent in the UI), then do the substitute check with the app closed:
```powershell
.venv-validate-<timestamp>\Scripts\python.exe -c "from core.database import Database; d=Database(); print(d.verify_audit()); print(len(d.audit_entries()), 'audit entries'); [print(dict(e)) for e in d.audit_entries()[-5:]]"
```
Expected: verification reports the chain valid; entries for the project creation (and any export) exist.
Status of UI item: ____ Status of substitute DB check: ____ Notes: ____

## GUI-06 PDF export and error display
1. Select the project, add one manual finding (Add manual finding).
2. "Export PDF" -> save as `smoke.pdf` in a local folder (e.g. Documents).
   Expected: info box "PDF report created."; open the file in a PDF viewer; text is readable.
3. "Export PDF" again with the same name `smoke.pdf` (confirm the Windows "replace?" prompt if it appears).
   Expected: the app refuses with a warning titled "PDF error" containing "Refusing to overwrite existing
   file"; the existing `smoke.pdf` is unchanged (same size/time, still opens).
4. Switch language to Persian and press "Export PDF".
   Expected: a clear error that Persian PDF is not validated / needs font and libraries - **no PDF is created**.
   (Persian PDF is NOT validated; this item only checks the refusal message.)
5. Try exporting to a network share or cloud-synced folder if you have one.
   Expected: either success, or a clear "Cannot publish ... hard link" error and no file. Record which.
Status: ____ Notes: ____

## GUI-07 Application shutdown
1. Close the window with the X button.
2. In Task Manager / `Get-Process python` check that no `python.exe` of the app remains after ~5 s.
3. Restart the app once more and confirm it opens normally (no database error, no "interrupted operation" surprise).
Expected: clean exit, no orphan process, no traceback in the console.
Status: ____ Notes: ____

## Summary
PASS ___  FAIL ___  BLOCKED ___  NOT RUN ___  (of 7)
Tester: ____________  Date: ____________
