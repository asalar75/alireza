"""R7: the Windows validation script must never overwrite, reuse or delete an earlier run's output.

Three kinds of evidence, reported separately:
  STATIC   - the PowerShell text is inspected (does not execute it).
  PYTHON   - the Python helper's output functions are really executed.
  POWERSHELL RUNTIME - the script is really executed; SKIPPED when no PowerShell is installed
                       (the Linux sandbox has none).
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PS1_PATH = ROOT / "tools" / "validate_windows.ps1"
PS1 = PS1_PATH.read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location("wv_outputs", ROOT / "tools" / "windows_validation.py")
wv = importlib.util.module_from_spec(_spec)
sys.modules["wv_outputs"] = wv
_spec.loader.exec_module(wv)


def snapshot(root: Path):
    """name -> (sha256 or None for dirs, size, mtime_ns) for everything under root."""
    out = {}
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        st = p.stat()
        out[rel] = (None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest(), st.st_size, st.st_mtime_ns)
    return out


# =========================================================================== STATIC (PowerShell text)
def _pos(needle, start=0):
    i = PS1.find(needle, start)
    assert i >= 0, needle
    return i


def test_static_preflight_runs_before_anything_is_written():
    refuse = _pos("function Stop-Refused")
    outdir_check = _pos("if (Test-Path -LiteralPath $OutDir)")
    venv_check = _pos("if (Test-Path -LiteralPath $venvDir)")
    create_out = _pos("New-Item -ItemType Directory -Path $OutDir")
    main_try = _pos("try {\n    Write-Host \"AegisSec Enterprise")
    first_write = _pos("$script:ResultsStream = Open-NewFileStream")
    assert refuse < outdir_check < venv_check < create_out < main_try
    assert venv_check < first_write and "exit 2" in PS1[refuse:outdir_check]
    # nothing but reads (Set-Location, Test-Path) happens before the OutDir check
    assert "Out-File" not in PS1[:outdir_check] and "WriteAllText" not in PS1


def test_static_new_item_never_uses_force_and_fails_closed():
    for l in PS1.splitlines():
        if "New-Item" in l and not l.lstrip().startswith("#"):
            assert "-Force" not in l and "-ErrorAction Stop" in l, l
    assert "-Force" not in PS1
    assert PS1.count("New-Item -ItemType Directory") == 2        # OutDir and venv folder only
    assert "Stop-Refused (\"cannot create a NEW OutDir" in PS1
    assert "Stop-Run 'venv'" in PS1 and "an existing one is never reused or deleted" in PS1


def test_static_no_delete_truncate_replace_rename_or_venv_reuse_commands():
    for bad in ("Remove-Item", "Move-Item", "Rename-Item", "Clear-Content", "Set-Content", "Out-File",
                "Add-Content", "Copy-Item", "--clear", "--upgrade", "-Recurse", "rmdir", "del ", "os.replace",
                "os.rename", "shutil.move", "SilentlyContinue -Force"):
        assert bad not in PS1, bad
    assert "@('-m', 'venv', $venvDir)" in PS1


def test_static_file_writes_use_exclusive_creation_only():
    """R7.1 superseded the R7 Test-Path/Write-Text guard; details in test_windows_validation_exclusive_io.py."""
    assert "function Write-Text" not in PS1 and "AllowRewrite" not in PS1
    assert "[System.IO.FileMode]::CreateNew" in PS1


def test_static_runid_is_validated_and_documented():
    assert "'^[A-Za-z0-9._-]{1,40}$'" in PS1 and ".PARAMETER RunId" in PS1 and "exit code 2" in PS1


# =========================================================================== PYTHON (really executed)
def test_python_write_new_refuses_existing_file_without_touching_it(tmp_path):
    f = tmp_path / "REPORT.md"
    f.write_bytes(b"EARLIER RUN\n")
    os.utime(f, ns=(1_000_000_000, 1_000_000_000))
    before = snapshot(tmp_path)
    with pytest.raises(FileExistsError):
        wv.write_new(f, "NEW")
    assert snapshot(tmp_path) == before


def test_python_report_refuses_existing_output_and_leaves_it_unchanged(tmp_path):
    res = {"meta": {"is_windows": False, "mode": "NOT WINDOWS"}, "steps": [], "commands": []}
    src = tmp_path / "results.json"
    src.write_text(json.dumps(res), encoding="utf-8")
    out = tmp_path / "REPORT.md"
    out.write_bytes(b"OLD REPORT")
    os.utime(out, ns=(2_000_000_000, 2_000_000_000))
    before = snapshot(tmp_path)
    assert wv.main(["report", str(src), "--out", str(out)]) == 2
    assert snapshot(tmp_path) == before


def test_python_report_to_a_new_path_still_works(tmp_path):
    res = {"meta": {"is_windows": False, "mode": "NOT WINDOWS"}, "steps": [], "commands": []}
    src = tmp_path / "results.json"
    src.write_text(json.dumps(res), encoding="utf-8")
    assert wv.main(["report", str(src), "--out", str(tmp_path / "new.md")]) == 0
    assert (tmp_path / "new.md").read_text(encoding="utf-8").startswith("# AegisSec")


def test_python_checks_refuse_when_checks_json_exists_and_do_not_run(tmp_path, monkeypatch):
    out = tmp_path / "run"
    out.mkdir()
    (out / "checks.json").write_bytes(b"{}")
    os.utime(out / "checks.json", ns=(3_000_000_000, 3_000_000_000))
    before = snapshot(tmp_path)
    monkeypatch.setattr(wv, "run_checks", lambda *a, **k: pytest.fail("checks must not run"))
    assert wv.main(["checks", "--out", str(out), "--allow-non-windows"]) == 2
    assert snapshot(tmp_path) == before


# =========================================================================== POWERSHELL RUNTIME
PWSH = shutil.which("pwsh") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(PWSH is None,
                              reason="PowerShell (pwsh/powershell) is not installed here: runtime test NOT RUN")


def _sandbox_repo(tmp_path: Path) -> Path:
    """A throw-away copy of the script so RepoRoot (derived from the script location) is tmp."""
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy2(PS1_PATH, repo / "tools" / "validate_windows.ps1")
    return repo


def _run_ps(repo: Path, *args):
    return subprocess.run([PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(repo / "tools" / "validate_windows.ps1"), *args],
                          capture_output=True, text=True, timeout=120, cwd=str(repo))


@needs_ps
def test_powershell_refuses_existing_outdir_and_changes_nothing(tmp_path):
    repo = _sandbox_repo(tmp_path)
    od = tmp_path / "old_out"
    od.mkdir()
    (od / "REPORT.md").write_bytes(b"EARLIER REPORT")
    (od / "results.json").write_bytes(b"{}")
    os.utime(od / "REPORT.md", ns=(4_000_000_000, 4_000_000_000))
    before = snapshot(tmp_path)
    r = _run_ps(repo, "-OutDir", str(od), "-RunId", "t7a")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "REFUSED" in r.stdout + r.stderr
    assert snapshot(tmp_path) == before
    assert not (repo / ".venv-validate-t7a").exists()


@needs_ps
def test_powershell_refuses_existing_venv_and_neither_reuses_nor_deletes_it(tmp_path):
    repo = _sandbox_repo(tmp_path)
    venv = repo / ".venv-validate-t7b"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "Scripts" / "python.exe").write_bytes(b"NOT A REAL PYTHON")
    os.utime(venv / "Scripts" / "python.exe", ns=(5_000_000_000, 5_000_000_000))
    before = snapshot(tmp_path)
    r = _run_ps(repo, "-RunId", "t7b")
    assert r.returncode == 2, r.stdout + r.stderr
    assert snapshot(tmp_path) == before
    assert not (repo / "validation_results").exists()


@needs_ps
def test_powershell_refuses_invalid_runid(tmp_path):
    repo = _sandbox_repo(tmp_path)
    before = snapshot(tmp_path)
    assert _run_ps(repo, "-RunId", "bad name/..").returncode == 2
    assert snapshot(tmp_path) == before
