# Windows 10/11 x64 validation (CPython 3.12) - how to run

Status of this package: **prepared, NOT executed on Windows.** Nothing in this repository
claims that Windows or NTFS behaviour has been validated. The only thing that can establish that is
a real run of the steps below on a Windows machine, recorded in a report (see the template).

Out of scope here (still open): Persian PDF validation (`PERSIAN_PDF_VALIDATED` stays False),
dependency locking, pip-audit, EXE build.

## What you need
* Windows 10 or 11 (client edition), x64 (AMD64). Windows on ARM and Windows Server are refused.
* CPython **3.12, 64-bit** from python.org (the `py` launcher is used: `py -3.12`).
* Internet access to PyPI for `pip install` **or** a folder of pre-downloaded wheels (`-WheelDir`).
  Pip downloads only what `requirements-dev.txt` asks for; nothing else is fetched.
* Microsoft Visual C++ Redistributable x64 (needed by PySide6).
* A local fixed drive (NTFS) for the temporary PDF tests. Network shares, cloud-synced folders and
  FAT/exFAT are expected to make PDF export fail closed (hard links unsupported); the script then
  records BLOCKED, not PASS.

## The command
Open PowerShell in the project folder (the one containing `app.py`) and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate_windows.ps1
```

Optional parameters
```powershell
-WorkDir D:\scratch        # local folder for the temporary PDF tests (default %TEMP%)
-WheelDir C:\wheels        # offline install: pip --no-index --find-links
-OutDir   C:\results\run1  # where results go; must NOT exist yet (default validation_results\<RunId>)
-RunId    mytest1          # name stamp for the default OutDir and .venv-validate-<RunId> (default: UTC timestamp)
-Rounds 5 -Procs 6         # concurrent-export check: rounds x processes
```
The script creates `.venv-validate-<RunId>` inside the project folder (a new one each run).

### Output safety (R7): earlier results are never touched
* If `-OutDir` (or the default `validation_results\<RunId>`) **already exists**, the script stops at once
  with `REFUSED: ...` and **exit code 2**, before writing anything.
* If `.venv-validate-<RunId>` **already exists**, it stops the same way. An existing venv is never
  reused, cleaned or deleted.
* The two folders are created with `New-Item` without the Force switch, so a folder that appears in the
  meantime is also a refusal. No file is ever deleted, truncated, replaced or renamed; every log and the
  report are created once. The only file rewritten is this run's own `results.json` (progress file).
* Consequence: running twice in the same second without `-RunId`/`-OutDir` is refused. Give each run a new
  `-RunId`, or remove the old folders yourself.
Exit codes: 0 = every automated step PASS; 1 = at least one step not PASS; 2 = refused (output path
exists / invalid RunId); the report helper also exits 2 when its output file already exists.

## What it does (in order)
| Step id | What | If it fails |
|---|---|---|
| env_os | Windows 10/11 client, x64 | BLOCKED, run stops |
| env_python | CPython 3.12, 64-bit, AMD64 | BLOCKED, run stops |
| venv | new isolated virtual environment | BLOCKED, run stops |
| pip_install | `pip install -r requirements-dev.txt` | BLOCKED with the missing package name(s) from the pip log, run stops |
| imports | PySide6, httpx, reportlab, pytest, pypdf, pdfplumber import | BLOCKED naming the package, run stops |
| pytest | full suite, JUnit XML, exact counts (skips listed) | FAIL (run continues) |
| compileall | `compileall -f` on app.py core reporting ui tools tests | FAIL (run continues) |
| gui_import | `import PySide6` and `ui.main_window` with `QT_QPA_PLATFORM=offscreen`; no window, no database | FAIL (run continues) |
| pdf_demo | ReportLab builds the English DEMO PDF; it is read back with pypdf | FAIL / BLOCKED |
| pdf_local_export | export onto the local file system; no leftovers; fs name and drive type recorded | FAIL / BLOCKED |
| pdf_no_overwrite | an existing file is never replaced (SHA-256 before/after, `FileExistsError`) | FAIL |
| pdf_concurrent | N separate processes export to one destination, repeated for several rounds; exactly one must succeed, the rest must get `FileExistsError`, the result must be a valid PDF, no temp files | FAIL |
| pdf_cleanup | injected render failure and injected hard-link failure leave no temp file and no destination | FAIL |

Required checks are never skipped silently: a step that is not reached is reported **NOT RUN**.
If the volume does not support hard links the PDF checks are **BLOCKED** (the application fails
closed by design; it does not fall back to an overwrite-capable operation).

The fault-injection part of `pdf_cleanup` simulates failures; it does not prove behaviour under real
disk-full or permission errors.

## Output (in `validation_results\<timestamp>\`)
* `REPORT.md` - the report (PASS / FAIL / BLOCKED / NOT RUN per step, pytest counts, skipped tests,
  OS, Python, package versions, file system, commands with exit codes).
* `results.json` - the same data, machine readable.
* `*.log`, `pytest-junit.xml`, `checks.json` - raw logs.


## After the automated run
1. Do the manual GUI smoke test: `docs\WINDOWS_GUI_SMOKE_TEST.md` (the script never starts the GUI).
2. Fill in `docs\WINDOWS_VALIDATION_REPORT_TEMPLATE.md` (attach `REPORT.md`).
3. Send back `REPORT.md`, `results.json` and the filled GUI checklist.

Windows validation counts as passed only when the automated part is all PASS **and** every GUI item
is PASS (BLOCKED / NOT RUN items keep it open).

## Dry run on non-Windows (development only)
`python tools/windows_validation.py checks --out OUT --allow-non-windows` runs only the PDF checks and
labels everything "DRY-RUN (not Windows; not a validation)". The PowerShell script itself refuses to
run anywhere but Windows.

## Known risks to look at on Windows (not verified, not defects yet)
* `core/database.py` `backup_to()` publishes the SQLite backup with `os.replace`. This is the database
  backup, not PDF export, and was not changed. On Windows a replace can fail if another process holds the
  target open. The test suite exercises backup/restore; watch those tests in the Windows run.
* pytest temporary directories contain SQLite files; Windows may keep them locked until the process ends.
* The GUI uses the real database `%USERPROFILE%\.aegissec\aegissec.sqlite3` (no override exists).
