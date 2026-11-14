"""Tests for the Windows-validation tooling (tools/windows_validation.py, tools/validate_windows.ps1,
docs). These run on any OS and test the TOOLING; they do not validate Windows behaviour.
The PowerShell script itself is only checked statically here (no PowerShell in the Linux sandbox)."""
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("windows_validation", ROOT / "tools" / "windows_validation.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["windows_validation"] = mod
    spec.loader.exec_module(mod)
    return mod


wv = _load()
PS1 = (ROOT / "tools" / "validate_windows.ps1").read_text(encoding="utf-8")


def _results(statuses, is_windows):
    return {"meta": {"is_windows": is_windows, "mode": "WINDOWS" if is_windows else "DRY-RUN"},
            "steps": [{"id": sid, "title": wv.STEP_TITLES[sid], "status": st, "detail": "d"}
                      for sid, st in statuses.items()], "commands": []}


# ---- report builder ------------------------------------------------------------------
def test_non_windows_report_is_never_a_validation():
    res = _results({sid: "PASS" for sid in wv.STEP_ORDER}, is_windows=False)
    md = wv.build_report(res)
    assert "NOT A WINDOWS VALIDATION" in md
    assert "Automated Windows validation: **PASS**" not in md
    assert "NOT PASSED" in md


def test_unreached_steps_are_reported_not_run_and_gui_is_not_run():
    res = _results({"env_os": "PASS", "env_python": "BLOCKED"}, is_windows=True)
    md = wv.build_report(res)
    rows = {l.split("|")[2].strip(): l for l in md.splitlines() if l.startswith("| ") and "**" in l}
    assert md.count("**NOT RUN**") >= len(wv.STEP_ORDER) - 2 + len(wv.GUI_ITEMS)
    for gid, _ in wv.GUI_ITEMS:
        assert re.search(rf"\| {gid} \|.*\*\*NOT RUN\*\*", md)
    assert "BLOCKED" in md and "NOT PASSED" in md and rows


def test_rendering_of_an_all_pass_input_keeps_open_items_open():
    """Synthetic input, used only to test the renderer: even then the GUI part, Persian PDF
    and the dependency audit must be reported as not done."""
    md = wv.build_report(_results({sid: "PASS" for sid in wv.STEP_ORDER}, is_windows=True))
    assert "Automated Windows validation: **PASS**" in md
    assert "Manual GUI smoke test: **NOT RUN**" in md
    assert "Persian PDF: **NOT VALIDATED**" in md
    assert "pip-audit: **NOT DONE**" in md
    assert "complete only if the automated part is PASS **and** every GUI item is PASS" in md


def test_a_single_fail_prevents_pass_verdict():
    st = {sid: "PASS" for sid in wv.STEP_ORDER}
    st["pdf_concurrent"] = "FAIL"
    assert "Automated Windows validation: **PASS**" not in wv.build_report(_results(st, True))


def test_skipped_tests_are_listed_and_not_counted_as_passed(tmp_path):
    xml = tmp_path / "j.xml"
    xml.write_text('<testsuites><testsuite tests="4" failures="1" errors="0" skipped="1">'
                   '<testcase classname="a" name="ok"/><testcase classname="a" name="ok2"/>'
                   '<testcase classname="a" name="bad"><failure message="x"/></testcase>'
                   '<testcase classname="a" name="sk"><skipped message="no symlinks"/></testcase>'
                   '</testsuite></testsuites>', encoding="utf-8")
    s = wv.summarize_junit(xml)
    assert (s["tests"], s["passed"], s["failures"], s["errors"], s["skipped"]) == (4, 2, 1, 0, 1)
    assert s["skipped_tests"] == ["a::sk (no symlinks)"] and s["failed_tests"] == ["a::bad"]


# ---- checks (dry run, non-Windows only) ---------------------------------------------------
@pytest.mark.skipif(os.name == "nt", reason="dry-run guard is for non-Windows hosts")
def test_checks_refuse_to_run_off_windows_without_explicit_flag(tmp_path):
    with pytest.raises(SystemExit) as ei:
        wv.run_checks(tmp_path, 1, 2, allow_non_windows=False)
    assert "Refusing" in str(ei.value)


@pytest.mark.skipif(os.name == "nt", reason="dry run on a non-Windows host")
def test_dry_run_checks_are_labelled_and_pass_on_this_host(tmp_path):
    res = wv.run_checks(tmp_path, rounds=1, procs=3, allow_non_windows=True)
    assert "not a validation" in res["meta"]["mode"].lower() and res["meta"]["is_windows"] is False
    ids = [s["id"] for s in res["steps"]]
    assert ids == ["pdf_demo", "pdf_local_export", "pdf_no_overwrite", "pdf_concurrent", "pdf_cleanup"]
    assert all(s["status"] == "PASS" for s in res["steps"]), res["steps"]
    assert "exists=2" in next(s for s in res["steps"] if s["id"] == "pdf_concurrent")["detail"]


# ---- static checks of the PowerShell script and docs ----------------------------------------
def test_ps1_is_ascii_and_brackets_balance():
    assert PS1.isascii()
    for a, b in ("()", "{}", "[]"):
        assert PS1.count(a) == PS1.count(b)


def test_ps1_references_every_step_id():
    for sid in wv.STEP_ORDER:
        assert sid in PS1, sid


def test_ps1_has_no_overwrite_capable_operations_and_no_silent_skip():
    for bad in ("Move-Item", "Copy-Item", "-Force:$true", "os.replace", "os.rename", "shutil.move",
                "SkipInstall", "-Skip", "ErrorAction SilentlyContinue -Force"):
        assert bad not in PS1, bad
    # the only -Force is the creation of the output folder
    assert [l.strip() for l in PS1.splitlines() if "-Force" in l] == [
        "New-Item -ItemType Directory -Force -Path $OutDir | Out-Null"]


def test_ps1_requires_windows_python312_x64_and_stops_on_missing_dependency():
    for needle in ("Win32NT", "AMD64", "$v[1] -eq 12", "-eq 'cpython'", "No matching distribution found",
                   "Missing/uninstallable package", "VALIDATION_STOP", "exit $ExitCodeOut"):
        assert needle in PS1, needle


def test_tooling_never_contains_overwrite_capable_fallbacks():
    src = (ROOT / "tools" / "windows_validation.py").read_text(encoding="utf-8")
    for bad in ("os.replace", "os.rename", "shutil.move", ".replace(tmp", "O_EXCL"):
        assert bad not in src, bad


def test_persian_gate_and_publish_function_untouched():
    from reporting import exporters
    assert exporters.PERSIAN_PDF_VALIDATED is False
    import inspect
    body = inspect.getsource(exporters._publish_no_overwrite).split('"""')[-1]
    for bad in ("os.replace", "os.rename", "shutil"):
        assert bad not in body


def test_docs_exist_and_define_the_four_statuses_and_gui_items():
    tpl = (ROOT / "docs" / "WINDOWS_VALIDATION_REPORT_TEMPLATE.md").read_text(encoding="utf-8")
    for st in ("**PASS**", "**FAIL**", "**BLOCKED**", "**NOT RUN**"):
        assert st in tpl
    gui = (ROOT / "docs" / "WINDOWS_GUI_SMOKE_TEST.md").read_text(encoding="utf-8")
    for gid, _ in wv.GUI_ITEMS:
        assert gid in gui and gid in tpl
    run = (ROOT / "docs" / "WINDOWS_VALIDATION.md").read_text(encoding="utf-8")
    assert "tools\\validate_windows.ps1" in run and "NOT executed on Windows" in run
