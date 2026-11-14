"""R7.1: genuinely exclusive creation of every validation output file (no check-then-write race).

Evidence kinds are kept apart (see docs/TEST_REPORT_0_3_M2_R7_1.md):
  STATIC      - PowerShell text inspected; the script is NOT executed.
  PYTHON      - Python helper really executed (windows_validation.write_new / report / checks).
  POWERSHELL  - PowerShell really executed. SKIPPED when pwsh/powershell is not installed (the Linux
                sandbox has none), i.e. NOT RUN there.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PS1_PATH = ROOT / "tools" / "validate_windows.ps1"
PS1 = PS1_PATH.read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location("wv_excl", ROOT / "tools" / "windows_validation.py")
wv = importlib.util.module_from_spec(_spec)
sys.modules["wv_excl"] = wv
_spec.loader.exec_module(wv)


def _function(name: str) -> str:
    """Text of a top-level PowerShell function (brace matched)."""
    start = PS1.index(f"function {name}")
    i = PS1.index("{", start)
    depth = 0
    for j in range(i, len(PS1)):
        depth += PS1[j] == "{"
        depth -= PS1[j] == "}"
        if depth == 0:
            return PS1[start:j + 1]
    raise AssertionError(name)


def _io_block() -> str:
    a = PS1.index("# BEGIN EXCLUSIVE-IO")
    b = PS1.index("# END EXCLUSIVE-IO")
    return PS1[a:b]


# =========================================================================== STATIC
def test_static_createnew_is_the_only_file_mode_and_there_is_no_overwrite_mode():
    modes = re.findall(r"FileMode\]::(\w+)", PS1)
    assert modes == ["CreateNew"]
    for bad in ("OpenOrCreate", "Truncate", "Append", "FileMode]::Create\b", "FileMode]::Open\b"):
        assert not re.search(bad, PS1), bad


def test_static_no_test_path_guard_protects_any_write():
    for name in ("Open-NewFileStream", "Set-OwnedContent", "Invoke-Logged"):
        assert "Test-Path" not in _function(name), name
    assert "Test-Path" not in _io_block()
    # remaining Test-Path uses are the two pre-flight refusals and read-only existence checks
    main_try = PS1.index('try {\n    Write-Host "AegisSec Enterprise')
    before_main = [l for l in PS1[:main_try].splitlines() if "Test-Path" in l and not l.lstrip().startswith("#")]
    assert len(before_main) == 2 and all("Stop-Refused" in l for l in before_main)


def test_static_no_redirect_cmdlets_no_bulk_writers_no_delete_rename_replace():
    for bad in ("Start-Process", "-RedirectStandard", "WriteAllText", "WriteAllBytes", "Set-Content", "Out-File",
                "Add-Content", "Remove-Item", "Move-Item", "Rename-Item", "Copy-Item", "Clear-Content",
                "File]::Delete", "File]::Move", "File]::Replace", "File]::Copy", "Directory]::Delete",
                ".Delete(", "[System.IO.File]::Create(", "OpenWrite", "-Force", "os.replace", "os.rename",
                "shutil.move", "--clear"):
        assert bad not in PS1, bad


def test_static_log_files_are_reserved_exclusively_before_the_command_runs_and_always_released():
    f = _function("Invoke-Logged")
    reserve = f.index("Open-NewFileStream (Join-Path $OutDir ($LogName + $suffix))")
    start = f.index("[System.Diagnostics.Process]::Start($psi)")
    assert reserve < start
    assert "'.stdout.txt', '.stderr.txt', '.log'" in f
    assert "$psi.RedirectStandardOutput = $true" in f and "$psi.RedirectStandardError = $true" in f
    assert "ReadToEndAsync" in f and "WaitForExit()" in f
    fin = f[f.index("finally {"):]
    assert "$proc.Dispose()" in fin and "$st.Dispose()" in fin
    # the content is written only through the owned handles
    assert f.count("Set-OwnedContent") == 3


def test_static_results_json_is_created_once_exclusively_and_owned_for_the_whole_run():
    assert PS1.count("Open-NewFileStream (Join-Path $OutDir 'results.json')") == 1
    assert "$Share = [System.IO.FileShare]::Read" in _function("Open-NewFileStream")
    assert "FileShare]::ReadWrite" not in PS1 and "FileShare]::Delete" not in PS1
    # rewritten only through the owned stream, never by path
    assert "Set-OwnedContent $script:ResultsStream $json" in _function("Save-Results")
    assert PS1.count("SetLength") == 1 and "SetLength" in _function("Set-OwnedContent")
    sol = _function("Set-OwnedContent")
    assert sol.index("$Stream.Write(") < sol.index("$Stream.SetLength(")      # shortened only after writing
    # ownership ends (handle closed) before the report helper reads the file
    dispose = PS1.index("$script:ResultsStream.Dispose()")
    report = PS1.index("'report'")
    assert dispose < report


def test_static_child_process_output_file_has_a_unique_name():
    assert "'pytest-junit-' + [guid]::NewGuid().ToString('N') + '.xml'" in PS1


# =========================================================================== PYTHON (executed)
def _snapshot(p: Path):
    st = p.stat()
    return (p.read_bytes(), st.st_size, st.st_mtime_ns)


def test_python_existing_output_file_is_preserved(tmp_path):
    f = tmp_path / "REPORT.md"
    f.write_bytes(b"EARLIER RUN")
    os.utime(f, ns=(1_500_000_000, 1_500_000_000))
    before = _snapshot(f)
    with pytest.raises(FileExistsError):
        wv.write_new(f, "NEW CONTENT")
    assert _snapshot(f) == before


def test_python_collision_between_precheck_and_write_is_caught_by_exclusive_create(tmp_path, monkeypatch):
    """The early existence pre-check reports 'free' (stale), the file then exists: write_new must still refuse."""
    res = {"meta": {"is_windows": False, "mode": "NOT WINDOWS"}, "steps": [], "commands": []}
    src = tmp_path / "results.json"
    src.write_text(__import__("json").dumps(res), encoding="utf-8")
    out = tmp_path / "REPORT.md"
    out.write_bytes(b"CREATED BY ANOTHER PROCESS")
    before = _snapshot(out)
    real_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda self, *a, **k: False if self == out else real_exists(self, *a, **k))
    assert wv.main(["report", str(src), "--out", str(out)]) == 2
    monkeypatch.undo()
    assert _snapshot(out) == before


def test_python_checks_json_created_by_someone_else_while_checks_run_is_preserved(tmp_path, monkeypatch):
    out = tmp_path / "run"
    out.mkdir()
    target = out / "checks.json"

    def fake_checks(*a, **k):
        target.write_bytes(b"FOREIGN checks.json")       # appears after the pre-check, before the write
        return {"meta": {}, "steps": [{"id": "x", "status": "PASS", "detail": ""}]}
    monkeypatch.setattr(wv, "run_checks", fake_checks)
    assert wv.main(["checks", "--out", str(out), "--allow-non-windows"]) == 2
    assert target.read_bytes() == b"FOREIGN checks.json"
    assert [p.name for p in out.iterdir()] == ["checks.json"]


def test_python_concurrent_threads_creating_the_same_file_exactly_one_wins(tmp_path):
    target = tmp_path / "same.txt"
    n = 12
    barrier = threading.Barrier(n)
    outcomes = []
    lock = threading.Lock()

    def worker(i):
        barrier.wait()
        try:
            wv.write_new(target, f"WRITER-{i}\n" * 2000)
            r = ("ok", i)
        except FileExistsError:
            r = ("exists", i)
        with lock:
            outcomes.append(r)
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join(30) for t in ts]
    winners = [i for k, i in outcomes if k == "ok"]
    assert len(outcomes) == n and len(winners) == 1
    assert target.read_text(encoding="utf-8") == f"WRITER-{winners[0]}\n" * 2000   # no interleaving
    assert [p.name for p in tmp_path.iterdir()] == ["same.txt"]


def test_python_concurrent_processes_creating_the_same_file_exactly_one_wins(tmp_path):
    target = tmp_path / "same.txt"
    go = tmp_path / "go.flag"
    code = ("import sys,time,importlib.util as u\n"
            "s=u.spec_from_file_location('w',sys.argv[1]);m=u.module_from_spec(s);s.loader.exec_module(m)\n"
            "from pathlib import Path\n"
            "while not Path(sys.argv[3]).exists(): time.sleep(0.001)\n"
            "try:\n m.write_new(Path(sys.argv[2]),'P'+sys.argv[4]+'\\n'*1000);sys.exit(0)\n"
            "except FileExistsError:\n sys.exit(3)\n")
    procs = [subprocess.Popen([sys.executable, "-I", "-c", code, str(ROOT / "tools" / "windows_validation.py"),
                               str(target), str(go), str(i)]) for i in range(6)]
    time.sleep(0.5)
    go.write_bytes(b"go")
    rcs = sorted(p.wait(timeout=60) for p in procs)
    assert rcs == [0, 3, 3, 3, 3, 3]
    txt = target.read_text(encoding="utf-8")
    assert txt.startswith("P") and txt.count("\n") == 1000


def test_python_unencodable_content_creates_no_file_and_keeps_existing_ones(tmp_path):
    new = tmp_path / "new.md"
    with pytest.raises(UnicodeEncodeError):
        wv.write_new(new, "bad \ud800 surrogate")
    assert not new.exists()
    old = tmp_path / "old.md"
    old.write_bytes(b"KEEP")
    with pytest.raises(UnicodeEncodeError):
        wv.write_new(old, "bad \ud800")
    assert old.read_bytes() == b"KEEP"


def test_python_handle_is_closed_when_the_write_itself_fails(tmp_path, monkeypatch):
    import builtins
    seen = []
    real_open = builtins.open

    class Boom:
        def __init__(self, fh):
            self.fh = fh
            seen.append(fh)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.fh.close()

        def write(self, data):
            raise OSError("disk full (injected)")
    monkeypatch.setattr(wv, "open", lambda *a, **k: Boom(real_open(*a, **k)), raising=False)
    with pytest.raises(OSError, match="injected"):
        wv.write_new(tmp_path / "x.txt", "data")
    assert seen and seen[0].closed


def test_python_report_failure_creates_no_output_file(tmp_path, monkeypatch):
    src = tmp_path / "results.json"
    src.write_text('{"meta": {}, "steps": []}', encoding="utf-8")
    monkeypatch.setattr(wv, "build_report", lambda r: (_ for _ in ()).throw(RuntimeError("render failed")))
    with pytest.raises(RuntimeError):
        wv.main(["report", str(src), "--out", str(tmp_path / "REPORT.md")])
    assert [p.name for p in tmp_path.iterdir()] == ["results.json"]


# =========================================================================== POWERSHELL (executed if available)
PWSH = shutil.which("pwsh") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(PWSH is None,
                              reason="PowerShell (pwsh/powershell) is not installed here: runtime test NOT RUN")


def _ps(tmp_path: Path, body: str, name="h.ps1", timeout=120):
    script = tmp_path / name
    script.write_text(body, encoding="utf-8")
    return subprocess.run([PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                          capture_output=True, text=True, timeout=timeout)


def _harness(tmp_path: Path, tail: str) -> str:
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    return ("$ErrorActionPreference = 'Stop'\n" + _io_block() + "\n"
            + _function("Format-Arg") + "\n" + _function("Invoke-Logged") + "\n"
            + f"$OutDir = '{out}'\n$RepoRoot = '{tmp_path}'\n"
            + "$script:Commands = New-Object System.Collections.ArrayList\nfunction Save-Results { }\n" + tail)


@needs_ps
def test_powershell_existing_file_is_preserved_by_open_newfilestream(tmp_path):
    f = tmp_path / "existing.txt"
    f.write_bytes(b"EARLIER")
    os.utime(f, ns=(1_600_000_000, 1_600_000_000))
    before = _snapshot(f)
    r = _ps(tmp_path, _harness(tmp_path, f"try {{ $s = Open-NewFileStream '{f}'; exit 0 }} catch {{ exit 7 }}\n"))
    assert r.returncode == 7, r.stdout + r.stderr
    assert _snapshot(f) == before


@needs_ps
def test_powershell_owned_stream_rewrites_shorter_content_and_blocks_a_second_creation(tmp_path):
    f = tmp_path / "results.json"
    tail = (f"$s = Open-NewFileStream '{f}'\n"
            "Set-OwnedContent $s ('x' * 5000)\nSet-OwnedContent $s 'short'\n"
            f"try {{ $t = Open-NewFileStream '{f}'; exit 9 }} catch {{ }}\n"
            "$s.Dispose()\nexit 0\n")
    r = _ps(tmp_path, _harness(tmp_path, tail))
    assert r.returncode == 0, r.stdout + r.stderr
    assert f.read_bytes() == b"short"


@needs_ps
def test_powershell_concurrent_creation_of_one_file_exactly_one_succeeds(tmp_path):
    f = tmp_path / "same.txt"
    body = _harness(tmp_path, f"try {{ $s = Open-NewFileStream '{f}'; Set-OwnedContent $s 'W'; $s.Dispose(); exit 0 }} catch {{ exit 7 }}\n")
    script = tmp_path / "c.ps1"
    script.write_text(body, encoding="utf-8")
    procs = [subprocess.Popen([PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(6)]
    rcs = sorted(p.wait(timeout=180) for p in procs)
    assert rcs == [0, 7, 7, 7, 7, 7]


@needs_ps
def test_powershell_existing_stdout_log_is_preserved_command_not_run_and_handles_released(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    log = out / "t.stdout.txt"
    log.write_bytes(b"EARLIER STDOUT")
    os.utime(log, ns=(1_700_000_000, 1_700_000_000))
    before = _snapshot(log)
    marker = tmp_path / "ran.marker"
    touch = tmp_path / "touch.py"
    touch.write_text("import sys, pathlib\npathlib.Path(sys.argv[1]).write_text('x')\n", encoding="utf-8")
    tail = f"try {{ Invoke-Logged '{sys.executable}' @('{touch}', '{marker}') 't'; exit 0 }} catch {{ exit 7 }}\n"
    r = _ps(tmp_path, _harness(tmp_path, tail))
    assert r.returncode == 7, r.stdout + r.stderr
    assert _snapshot(log) == before and not marker.exists()
    assert sorted(p.name for p in out.iterdir()) == ["t.stdout.txt"]


@needs_ps
def test_powershell_existing_stderr_and_log_files_are_preserved_and_reserved_handles_released(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    err = out / "t.stderr.txt"
    err.write_bytes(b"EARLIER STDERR")
    before = _snapshot(err)
    hello = tmp_path / "hello.py"
    hello.write_text("print(1)\n", encoding="utf-8")
    tail = f"try {{ Invoke-Logged '{sys.executable}' @('{hello}') 't'; exit 0 }} catch {{ exit 7 }}\n"
    r = _ps(tmp_path, _harness(tmp_path, tail))
    assert r.returncode == 7, r.stdout + r.stderr
    assert _snapshot(err) == before
    # the stdout log that was reserved before the failure is an empty file of this run, and its handle is closed
    s = out / "t.stdout.txt"
    assert s.exists() and s.read_bytes() == b""
    with open(s, "ab"):                      # re-openable for writing => no leaked handle
        pass
    assert not (out / "t.log").exists()


@needs_ps
def test_powershell_invoke_logged_publishes_stdout_stderr_and_combined_log_exclusively(tmp_path):
    out = tmp_path / "out"
    emit = tmp_path / "emit.py"
    emit.write_text("import sys\nprint('OUT')\nsys.stderr.write('ERR')\nsys.exit(5)\n", encoding="utf-8")
    tail = (f"$r = Invoke-Logged '{sys.executable}' @('{emit}') 't'\n"
            "if ($r.ExitCode -ne 5) { exit 9 }\nexit 0\n")
    r = _ps(tmp_path, _harness(tmp_path, tail))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (out / "t.stdout.txt").read_text(encoding="utf-8").strip() == "OUT"
    assert (out / "t.stderr.txt").read_text(encoding="utf-8") == "ERR"
    combined = (out / "t.log").read_text(encoding="utf-8")
    assert "OUT" in combined and "ERR" in combined
