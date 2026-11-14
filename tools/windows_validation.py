"""Windows validation helper for AegisSec Enterprise (used by tools/validate_windows.ps1).

Sub-commands
  probe   print interpreter facts as JSON (version, bitness, machine, implementation). stdlib only.
  imports check that the named packages import and print their versions as JSON; exit 1 if any
          is missing.
  guiimport import PySide6.QtWidgets and ui.main_window (no window is created).
  checks  run the PDF export checks (ReportLab demo PDF, local temp dir, no-overwrite,
          concurrent exports in separate processes, temp-file cleanup after failures) and write
          checks.json. Needs the project's dependencies (run it with the venv Python).
  junit   summarise a pytest JUnit XML file (exact counts, skip reasons). stdlib only.
  report  build REPORT.md from results.json. stdlib only.

Honesty rules
  * Every result records the platform it ran on. Unless the platform is Windows the run is
    labelled a DRY RUN and the report says it is NOT a Windows validation.
  * Nothing here weakens or replaces the application's fail-closed no-overwrite publishing.
    The fault-injection checks only simulate failures; they never call an overwrite-capable
    operation in the application.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ("PASS", "FAIL", "BLOCKED", "NOT RUN")

# Ordered ids of every automated step; a step that is never recorded is reported NOT RUN.
STEP_TITLES = {
    "env_os": "Windows 10/11 x64 detected",
    "env_python": "CPython 3.12 x64 detected",
    "venv": "Isolated virtual environment created",
    "pip_install": "Project requirements installed (requirements-dev.txt)",
    "imports": "Required packages importable",
    "pytest": "Complete pytest suite",
    "compileall": "compileall of all project Python sources",
    "gui_import": "PySide6 + ui.main_window import (no window shown)",
    "pdf_demo": "ReportLab generates the English DEMO PDF",
    "pdf_local_export": "PDF export to a local temp dir on the Windows file system",
    "pdf_no_overwrite": "Existing destination is never overwritten",
    "pdf_concurrent": "Concurrent exports (separate processes) to one destination: exactly one succeeds",
    "pdf_cleanup": "Temporary files removed after failures (injected faults)",
}
STEP_ORDER = list(STEP_TITLES)

GUI_ITEMS = (
    ("GUI-01", "Application startup (python app.py)"),
    ("GUI-02", "Main window rendering (EN and FA layout, RTL, fonts)"),
    ("GUI-03", "Project creation and reopening after restart"),
    ("GUI-04", "Scope validation (valid origin accepted, invalid origin / path / credentials rejected)"),
    ("GUI-05", "Audit log visibility (see note: no audit view exists in the UI at this commit)"),
    ("GUI-06", "PDF export success and error display (existing file refused with message)"),
    ("GUI-07", "Application shutdown (clean exit, no orphan process)"),
)


# --------------------------------------------------------------------------- helpers
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fs_info(path: Path) -> dict:
    """File-system facts about the volume holding ``path`` (best effort, never raises)."""
    info = {"path": str(path), "platform": platform.system(), "fs_name": "unknown",
            "drive_type": "unknown", "supports_hard_links": None}
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            root = ctypes.create_unicode_buffer(260)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetVolumePathNameW(str(path), root, 260)
            fsname = ctypes.create_unicode_buffer(64)
            flags = wintypes.DWORD()
            ok = k32.GetVolumeInformationW(root.value, None, 0, None, None, ctypes.byref(flags),
                                           fsname, 64)
            if ok:
                info["fs_name"] = fsname.value
                info["supports_hard_links"] = bool(flags.value & 0x00400000)
            info["volume_root"] = root.value
            dt = k32.GetDriveTypeW(root.value)
            info["drive_type"] = {2: "removable", 3: "fixed (local)", 4: "network", 5: "cd-rom",
                                  6: "ram disk"}.get(dt, f"unknown({dt})")
        else:
            out = subprocess.run(["stat", "-f", "-c", "%T", str(path)], capture_output=True,
                                 text=True, timeout=10)
            if out.returncode == 0:
                info["fs_name"] = out.stdout.strip()
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        info["error"] = repr(exc)
    return info


def _step(sid, status, detail, **extra):
    assert status in STATUSES
    d = {"id": sid, "title": STEP_TITLES.get(sid, sid), "status": status, "detail": detail}
    d.update(extra)
    return d


# --------------------------------------------------------------------------- checks
def _concurrent_worker(args):
    """Runs in a separate (spawned) process. Top-level so Windows 'spawn' can import it."""
    dest, barrier, queue, idx = args
    sys.path.insert(0, str(ROOT))
    from reporting.exporters import export_pdf
    sys.path.insert(0, str(ROOT / "tools"))
    import sample_data as sd
    try:
        barrier.wait(timeout=120)
        export_pdf(dest, sd.PROJECT["en"], sd.findings("en"), "en", assets=sd.ASSETS, demo=True)
        queue.put((idx, "ok", ""))
    except FileExistsError as exc:
        queue.put((idx, "exists", str(exc)))
    except BaseException as exc:  # noqa: BLE001
        queue.put((idx, "error", f"{type(exc).__name__}: {exc}"))


def _leftovers(d: Path, allowed: set[str]) -> list[str]:
    return sorted(p.name for p in d.iterdir() if p.name not in allowed)


def run_checks(work_dir: Path | None, rounds: int, procs: int, allow_non_windows: bool) -> dict:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))
    steps = []
    meta = {"started": _now(), "platform": platform.platform(), "system": platform.system(),
            "machine": platform.machine(), "python": sys.version, "executable": sys.executable,
            "is_windows": os.name == "nt"}
    if os.name != "nt" and not allow_non_windows:
        raise SystemExit("Refusing to run: not Windows. Use --allow-non-windows for a DRY RUN "
                         "(its results are NOT Windows validation).")
    meta["mode"] = "WINDOWS" if os.name == "nt" else "DRY-RUN (not Windows; not a validation)"

    import importlib.metadata as md
    meta["reportlab"] = md.version("reportlab")
    base = Path(work_dir) if work_dir else Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix="aegis-val-", dir=str(base)))
    meta["work_dir"] = str(tmpdir)
    meta["fs"] = fs_info(tmpdir)

    local_ok = (os.name != "nt") or meta["fs"].get("drive_type") == "fixed (local)"
    if not local_ok:
        why = (f"work directory {tmpdir} is on a {meta['fs'].get('drive_type')} drive "
               f"({meta['fs'].get('fs_name')}); a local fixed drive is required. "
               "Re-run with -WorkDir pointing at a local folder.")
        for sid in ("pdf_demo", "pdf_local_export", "pdf_no_overwrite", "pdf_concurrent", "pdf_cleanup"):
            steps.append(_step(sid, "BLOCKED", why))
        return {"meta": meta, "steps": steps}

    import reporting.exporters as ex
    from reporting.exporters import export_pdf
    import sample_data as sd

    def demo_export(dest):
        export_pdf(dest, sd.PROJECT["en"], sd.findings("en"), "en", assets=sd.ASSETS, demo=True)

    # 1. ReportLab generates the English demo PDF --------------------------------------
    first = tmpdir / "demo_en.pdf"
    try:
        demo_export(first)
    except ex.ExportPublishError as exc:
        why = ("The volume does not allow the atomic no-overwrite step (hard link): "
               f"{exc}. The application fails closed by design; run with a local NTFS folder.")
        for sid in ("pdf_demo", "pdf_local_export", "pdf_no_overwrite", "pdf_concurrent", "pdf_cleanup"):
            steps.append(_step(sid, "BLOCKED", why))
        return {"meta": meta, "steps": steps}
    except BaseException as exc:  # noqa: BLE001
        steps.append(_step("pdf_demo", "FAIL", f"{type(exc).__name__}: {exc}"))
        for sid in ("pdf_local_export", "pdf_no_overwrite", "pdf_concurrent", "pdf_cleanup"):
            steps.append(_step(sid, "NOT RUN", "earlier step failed"))
        return {"meta": meta, "steps": steps}

    try:
        from pypdf import PdfReader
        rd = PdfReader(str(first))
        text = "\n".join(p.extract_text() or "" for p in rd.pages)
        header = first.read_bytes()[:5]
        problems = []
        if header != b"%PDF-":
            problems.append(f"bad header {header!r}")
        if len(rd.pages) < 1:
            problems.append("no pages")
        for needle in ("DEMONSTRATION DATA", "Page 1 of", "Security Assessment Report"):
            if needle not in text:
                problems.append(f"missing text {needle!r}")
        steps.append(_step("pdf_demo", "FAIL" if problems else "PASS",
                           "; ".join(problems) if problems else
                           f"{len(rd.pages)} page(s), {first.stat().st_size} bytes, ReportLab {meta['reportlab']}"))
    except BaseException as exc:  # noqa: BLE001
        steps.append(_step("pdf_demo", "FAIL", f"could not read generated PDF: {exc!r}"))

    # 2. local export: file exists, only that file, no temp leftovers --------------------
    left = _leftovers(tmpdir, {"demo_en.pdf"})
    steps.append(_step("pdf_local_export", "FAIL" if left or not first.exists() else "PASS",
                       f"destination on {meta['fs'].get('fs_name')} / {meta['fs'].get('drive_type')}; "
                       f"leftover files: {left or 'none'}"))

    # 3. existing destination never overwritten -----------------------------------------
    d3 = Path(tempfile.mkdtemp(prefix="noover-", dir=str(tmpdir)))
    dest = d3 / "existing.pdf"
    marker = b"EXISTING DESTINATION - MUST SURVIVE\n" + os.urandom(64)
    dest.write_bytes(marker)
    before = _sha(dest)
    outcome = ""
    try:
        demo_export(dest)
        outcome = "export returned without error (overwrite attempted!)"
    except FileExistsError:
        outcome = "FileExistsError (expected)"
    except BaseException as exc:  # noqa: BLE001
        outcome = f"unexpected {type(exc).__name__}: {exc}"
    same = dest.read_bytes() == marker and _sha(dest) == before
    left = _leftovers(d3, {"existing.pdf"})
    ok = same and outcome.startswith("FileExistsError") and not left
    steps.append(_step("pdf_no_overwrite", "PASS" if ok else "FAIL",
                       f"{outcome}; content identical: {same}; leftovers: {left or 'none'}"))

    # 4. concurrent exports in separate processes ----------------------------------------
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    round_notes, ok4 = [], True
    for r in range(rounds):
        d4 = Path(tempfile.mkdtemp(prefix=f"conc{r}-", dir=str(tmpdir)))
        dest4 = d4 / "same.pdf"
        barrier, queue = ctx.Barrier(procs), ctx.Queue()
        ps = [ctx.Process(target=_concurrent_worker, args=((dest4, barrier, queue, i),))
              for i in range(procs)]
        for p in ps:
            p.start()
        results = []
        try:
            for _ in ps:
                results.append(queue.get(timeout=300))
        except Exception as exc:  # noqa: BLE001
            results.append((-1, "error", f"collect failed: {exc!r}"))
        for p in ps:
            p.join(60)
            if p.is_alive():
                p.terminate()
        kinds = sorted(k for _, k, _ in results)
        n_ok = kinds.count("ok")
        n_exists = kinds.count("exists")
        errs = [m for _, k, m in results if k == "error"]
        valid = dest4.exists() and dest4.read_bytes()[:5] == b"%PDF-"
        left = _leftovers(d4, {"same.pdf"})
        good = n_ok == 1 and n_exists == procs - 1 and not errs and valid and not left
        ok4 = ok4 and good
        round_notes.append(f"round {r + 1}: ok={n_ok} exists={n_exists} errors={errs or 0} "
                           f"valid_pdf={valid} leftovers={left or 'none'}")
    steps.append(_step("pdf_concurrent", "PASS" if ok4 else "FAIL",
                       f"{procs} processes x {rounds} rounds. " + " | ".join(round_notes)))

    # 5. cleanup after failures (injected faults; simulates failures, not real FS faults) ---
    notes, ok5 = [], True
    real_render, real_link = ex.render_pdf, os.link
    d5 = Path(tempfile.mkdtemp(prefix="cleanup-", dir=str(tmpdir)))
    try:
        ex.render_pdf = lambda tmp, *a, **k: (Path(tmp).write_bytes(b"%PDF-partial"),
                                              (_ for _ in ()).throw(RuntimeError("injected")))[1]
        try:
            demo_export(d5 / "render_fail.pdf")
            ok5, _msg = False, "render failure not raised"
        except RuntimeError:
            _msg = "render failure -> RuntimeError"
        left = _leftovers(d5, set())
        ok5 = ok5 and not left
        notes.append(f"{_msg}; leftovers: {left or 'none'}")
    finally:
        ex.render_pdf = real_render
    try:
        def nolink(*a, **k):
            raise OSError(1, "injected: hard links unsupported")
        os.link = nolink
        try:
            demo_export(d5 / "nolink.pdf")
            ok5, _msg = False, "link failure not raised"
        except ex.ExportPublishError:
            _msg = "link failure -> ExportPublishError"
        left = _leftovers(d5, set())
        ok5 = ok5 and not left
        notes.append(f"{_msg}; leftovers: {left or 'none'}")
    finally:
        os.link = real_link
    steps.append(_step("pdf_cleanup", "PASS" if ok5 else "FAIL", " | ".join(notes)))

    meta["finished"] = _now()
    return {"meta": meta, "steps": steps}


# --------------------------------------------------------------------------- junit
def summarize_junit(xml_path: Path) -> dict:
    root = ET.parse(xml_path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    out = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "passed": 0,
           "skipped_tests": [], "failed_tests": []}
    for s in suites:
        out["tests"] += int(s.get("tests", 0))
        out["failures"] += int(s.get("failures", 0))
        out["errors"] += int(s.get("errors", 0))
        out["skipped"] += int(s.get("skipped", 0))
    for tc in root.iter("testcase"):
        name = f"{tc.get('classname')}::{tc.get('name')}"
        sk = tc.find("skipped")
        if sk is not None:
            out["skipped_tests"].append(f"{name} ({sk.get('message', '')})")
        if tc.find("failure") is not None or tc.find("error") is not None:
            out["failed_tests"].append(name)
    out["passed"] = out["tests"] - out["failures"] - out["errors"] - out["skipped"]
    return out


# --------------------------------------------------------------------------- report
def build_report(results: dict) -> str:
    meta = results.get("meta", {})
    by_id = {s["id"]: s for s in results.get("steps", [])}
    steps = []
    for sid in STEP_ORDER:
        steps.append(by_id.get(sid) or _step(sid, "NOT RUN", "step was never reached"))
    for sid, s in by_id.items():  # unknown extra steps
        if sid not in STEP_TITLES:
            steps.append(s)
    # Fail closed (R6): a Windows verdict needs BOTH a literal JSON true for is_windows AND the exact
    # string "WINDOWS" as mode. A missing/null/"true"/1 value, or any other mode (known-bad like
    # "DRY-RUN", or unknown like "WINDOWS-UNVERIFIED" / "windows" / " WINDOWS"), is never accepted.
    raw_mode = meta.get("mode", "")
    mode = str(raw_mode)
    recorded = meta.get("is_windows")
    is_win = (recorded is True) and (isinstance(raw_mode, str) and raw_mode == "WINDOWS")
    counts = {k: sum(1 for s in steps if s["status"] == k) for k in STATUSES}
    auto_pass = is_win and counts["PASS"] == len(steps)
    L = []
    L.append("# AegisSec Enterprise - Windows validation report (automated part)\n")
    L.append(f"Generated: {_now()}  \nCommit: {meta.get('commit', 'unknown')}  \n"
             f"Script mode: **{meta.get('mode', 'unknown')}**\n")
    if not is_win:
        if "is_windows" not in meta:
            why = "the platform was not recorded (`is_windows` is missing)"
        elif recorded is True:
            why = f"the recorded mode is inconsistent with a Windows run ({mode!r})"
        else:
            why = "the run did not confirm a supported Windows 10/11 x64 platform (dry run or blocked)"
        L.append("> **NOT A WINDOWS VALIDATION.** " + (why[0].upper() + why[1:]) + ". Nothing in this report "
                 "validates Windows or NTFS behaviour.\n")
    L.append("## Verdict\n")
    L.append(f"* Automated steps: PASS {counts['PASS']} / FAIL {counts['FAIL']} / "
             f"BLOCKED {counts['BLOCKED']} / NOT RUN {counts['NOT RUN']} (of {len(steps)})")
    L.append("* Automated Windows validation: **" + ("PASS" if auto_pass else
             "NOT PASSED (see steps)") + "**")
    L.append("* An automated PASS covers only the automated steps above; it says nothing about the manual "
             "GUI checklist, Persian PDF, dependency locking or pip-audit.")
    L.append("* Manual GUI smoke test: **NOT RUN** until a person fills in "
             "`docs/WINDOWS_GUI_SMOKE_TEST.md` (this script never runs the GUI).")
    L.append("* Persian PDF: **NOT VALIDATED** (`PERSIAN_PDF_VALIDATED` is False; font and wheels pending).")
    L.append("* Dependency locking and pip-audit: **NOT DONE** (requirements are not pinned).")
    L.append("* Windows validation of the project as a whole is complete only if the automated "
             "part is PASS **and** every GUI item is PASS.\n")
    L.append("## Steps\n")
    L.append("| # | Step | Status | Detail |\n|---|---|---|---|")
    for i, s in enumerate(steps, 1):
        d = str(s.get("detail", "")).replace("|", "\\|").replace("\n", " ")
        cmd = f" `{s['command']}`" if s.get("command") else ""
        ec = f" (exit {s['exit_code']})" if s.get("exit_code") is not None else ""
        L.append(f"| {i} | {s['title']}{cmd} | **{s['status']}**{ec} | {d} |")
    pt = results.get("pytest")
    if pt:
        L.append("\n## pytest (exact counts)\n")
        L.append(f"tests={pt['tests']} passed={pt['passed']} failed={pt['failures']} "
                 f"errors={pt['errors']} skipped={pt['skipped']}\n")
        if pt["skipped_tests"]:
            L.append("Skipped tests (a skip is NOT a pass):\n")
            L += [f"* {t}" for t in pt["skipped_tests"]]
        if pt["failed_tests"]:
            L.append("\nFailed tests:\n")
            L += [f"* {t}" for t in pt["failed_tests"]]
    L.append("\n## Environment\n")
    for k in ("os", "os_build", "architecture", "python", "executable", "work_dir", "powershell"):
        if k in meta:
            L.append(f"* {k}: {meta[k]}")
    if meta.get("fs"):
        L.append(f"* file system of work dir: {json.dumps(meta['fs'])}")
    if meta.get("packages"):
        L.append("\n### Installed packages\n")
        L.append("```\n" + "\n".join(meta["packages"]) + "\n```")
    if results.get("commands"):
        L.append("\n## Commands run\n")
        L.append("| Command | Exit code |\n|---|---|")
        for c in results["commands"]:
            L.append(f"| `{c['command']}` | {c['exit_code']} |")
    L.append("\n## Manual GUI smoke test (not executed by the script)\n")
    L.append("| ID | Item | Status |\n|---|---|---|")
    for gid, title in GUI_ITEMS:
        L.append(f"| {gid} | {title} | **NOT RUN** |")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- safe output
def write_new(path: Path, text: str) -> None:
    """Create ``path`` exclusively. An existing file is never truncated or replaced
    (FileExistsError); there is no overwrite fallback."""
    with open(path, "x", encoding="utf-8") as fh:
        fh.write(text)


def _refuse_existing(path: Path) -> int:
    print(f"REFUSED: {path} already exists. Nothing was written, deleted or replaced. "
          "Choose a new output path.", file=sys.stderr)
    return 2


# --------------------------------------------------------------------------- probes
def probe() -> dict:
    import struct
    return {"version": list(sys.version_info[:3]), "bits": struct.calcsize("P") * 8,
            "machine": platform.machine(), "implementation": sys.implementation.name,
            "executable": sys.executable, "system": platform.system(),
            "platform": platform.platform()}


def check_imports(names) -> dict:
    import importlib
    import importlib.metadata as md
    out = {}
    for n in names:
        try:
            importlib.import_module(n)
            out[n] = md.version(n)
        except Exception as exc:  # noqa: BLE001
            out[n] = None
            out[n + ".error"] = f"{type(exc).__name__}: {exc}"
    return out


def gui_import() -> dict:
    sys.path.insert(0, str(ROOT))
    import PySide6
    from PySide6 import QtWidgets  # noqa: F401
    import ui.main_window as mw  # noqa: F401 - import only; no QApplication, no window
    return {"PySide6": PySide6.__version__, "module": "ui.main_window imported"}


# --------------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("checks")
    c.add_argument("--out", required=True, type=Path, help="directory for checks.json")
    c.add_argument("--work-dir", type=Path, default=None)
    c.add_argument("--rounds", type=int, default=5)
    c.add_argument("--procs", type=int, default=6)
    c.add_argument("--allow-non-windows", action="store_true")
    sub.add_parser("probe")
    im = sub.add_parser("imports")
    im.add_argument("names", nargs="+")
    sub.add_parser("guiimport")
    j = sub.add_parser("junit")
    j.add_argument("xml", type=Path)
    r = sub.add_parser("report")
    r.add_argument("results", type=Path)
    r.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    if a.cmd == "checks":
        if (a.out / "checks.json").exists():
            return _refuse_existing(a.out / "checks.json")
        res = run_checks(a.work_dir, a.rounds, a.procs, a.allow_non_windows)
        a.out.mkdir(parents=True, exist_ok=True)
        try:
            write_new(a.out / "checks.json", json.dumps(res, indent=2))
        except FileExistsError:
            return _refuse_existing(a.out / "checks.json")
        for s in res["steps"]:
            print(f"[{s['status']}] {s['id']}: {s['detail']}")
        return 0 if all(s["status"] == "PASS" for s in res["steps"]) else 1
    if a.cmd == "probe":
        print(json.dumps(probe()))
        return 0
    if a.cmd == "imports":
        res = check_imports(a.names)
        print(json.dumps(res))
        return 0 if all(res.get(n) for n in a.names) else 1
    if a.cmd == "guiimport":
        try:
            print(json.dumps(gui_import()))
            return 0
        except BaseException as exc:  # noqa: BLE001
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
            return 1
    if a.cmd == "junit":
        print(json.dumps(summarize_junit(a.xml)))
        return 0
    if a.cmd == "report":
        if a.out.exists():
            return _refuse_existing(a.out)
        results = json.loads(a.results.read_text(encoding="utf-8-sig"))
        try:
            write_new(a.out, build_report(results))
        except FileExistsError:
            return _refuse_existing(a.out)
        print(f"wrote {a.out}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
