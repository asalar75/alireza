"""export_pdf: never overwrite, unique temp names, failure cleanup, atomic publish."""
import errno
import os
import threading
from pathlib import Path

import pytest

import reporting.exporters as ex
from reporting.exporters import export_pdf

PROJECT = {"name": "Demo Corp", "target": "https://example.com", "authorized_by": "AUTH-1"}
FINDING = dict(id=1, title="T", severity="Low", confidence="Medium", status="Needs review",
               url="https://example.com", evidence="e", remediation="r", reference="")


def test_existing_destination_is_not_replaced(tmp_path):
    out = tmp_path / "r.pdf"
    out.write_bytes(b"ORIGINAL CONTENT")
    with pytest.raises(FileExistsError):
        export_pdf(out, PROJECT, [FINDING], "en")
    assert out.read_bytes() == b"ORIGINAL CONTENT"
    assert [p.name for p in tmp_path.iterdir()] == ["r.pdf"]


def test_existing_valid_pdf_is_byte_identical_after_second_export(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [FINDING], "en", generated_at="2026-11-13 00:00")
    before = out.read_bytes()
    assert before.startswith(b"%PDF")
    with pytest.raises(FileExistsError):
        export_pdf(out, PROJECT, [dict(FINDING, title="Different")], "en")
    assert out.read_bytes() == before


def test_existing_symlink_destination_is_refused(tmp_path):
    target = tmp_path / "t.bin"
    target.write_bytes(b"KEEP")
    link = tmp_path / "l.pdf"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(FileExistsError):
        export_pdf(link, PROJECT, [FINDING], "en")
    assert target.read_bytes() == b"KEEP"


def test_success_leaves_only_the_pdf(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [FINDING], "en")
    assert out.read_bytes().startswith(b"%PDF")
    assert [p.name for p in tmp_path.iterdir()] == ["r.pdf"]


def test_failure_during_generation_cleans_temp_and_creates_no_destination(tmp_path, monkeypatch):
    seen = []

    def boom(tmp, *a, **k):
        seen.append(tmp)
        tmp.write_bytes(b"%PDF-partial")
        raise RuntimeError("render failed")
    monkeypatch.setattr(ex, "render_pdf", boom)
    out = tmp_path / "r.pdf"
    with pytest.raises(RuntimeError, match="render failed"):
        export_pdf(out, PROJECT, [FINDING], "en")
    assert seen and not seen[0].exists()
    assert not out.exists() and list(tmp_path.iterdir()) == []


def test_failure_does_not_touch_other_existing_files(tmp_path, monkeypatch):
    other = tmp_path / "other.pdf"
    other.write_bytes(b"OTHER")
    monkeypatch.setattr(ex, "render_pdf", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        export_pdf(tmp_path / "new.pdf", PROJECT, [FINDING], "en")
    assert other.read_bytes() == b"OTHER" and [p.name for p in tmp_path.iterdir()] == ["other.pdf"]


def test_destination_appearing_during_render_is_not_overwritten(tmp_path, monkeypatch):
    """Race: the name is free at the check but taken before the final step."""
    out = tmp_path / "r.pdf"
    real = ex.render_pdf

    def render_then_race(tmp, *a, **k):
        real(tmp, *a, **k)
        out.write_bytes(b"CREATED BY SOMEONE ELSE")
    monkeypatch.setattr(ex, "render_pdf", render_then_race)
    with pytest.raises(FileExistsError):
        export_pdf(out, PROJECT, [FINDING], "en")
    assert out.read_bytes() == b"CREATED BY SOMEONE ELSE"
    assert [p.name for p in tmp_path.iterdir()] == ["r.pdf"]


def test_temp_names_are_unique_for_concurrent_exports(tmp_path, monkeypatch):
    real = ex.render_pdf
    names, barrier = [], threading.Barrier(2, timeout=10)

    def slow(tmp, *a, **k):
        names.append(str(tmp))
        barrier.wait()          # both exports are in flight with their temp files at once
        real(tmp, *a, **k)
    monkeypatch.setattr(ex, "render_pdf", slow)
    results = {}

    def run(i):
        try:
            export_pdf(tmp_path / "same.pdf", PROJECT, [dict(FINDING, title=f"T{i}")], "en")
            results[i] = "ok"
        except FileExistsError:
            results[i] = "exists"
    ts = [threading.Thread(target=run, args=(i,)) for i in (1, 2)]
    [t.start() for t in ts]
    [t.join(30) for t in ts]
    assert len(set(names)) == 2                       # distinct temp files
    assert sorted(results.values()) == ["exists", "ok"]  # exactly one winner
    assert (tmp_path / "same.pdf").read_bytes().startswith(b"%PDF")
    assert [p.name for p in tmp_path.iterdir()] == ["same.pdf"]


def test_two_exports_to_different_names_both_succeed(tmp_path):
    export_pdf(tmp_path / "a.pdf", PROJECT, [FINDING], "en")
    export_pdf(tmp_path / "b.pdf", PROJECT, [FINDING], "en")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.pdf", "b.pdf"]


def _no_hardlinks(monkeypatch, exc=None):
    exc = exc or OSError(errno.EPERM, "hard links unsupported")

    def nolink(*a, **k):
        raise exc
    monkeypatch.setattr(os, "link", nolink)


def test_hardlink_unsupported_fails_safely_and_creates_no_destination(tmp_path, monkeypatch):
    _no_hardlinks(monkeypatch)
    out = tmp_path / "r.pdf"
    with pytest.raises(ex.ExportPublishError, match="hard link"):
        export_pdf(out, PROJECT, [FINDING], "en")
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []          # temp file removed too


@pytest.mark.parametrize("err", [errno.EPERM, errno.ENOTSUP, errno.EXDEV, errno.EACCES, errno.EMLINK])
def test_any_non_exists_link_error_fails_closed(tmp_path, monkeypatch, err):
    _no_hardlinks(monkeypatch, OSError(err, "link failed"))
    with pytest.raises(ex.ExportPublishError) as ei:
        export_pdf(tmp_path / "r.pdf", PROJECT, [FINDING], "en")
    assert isinstance(ei.value.__cause__, OSError) and "untouched" in str(ei.value)
    assert list(tmp_path.iterdir()) == []


def test_hardlink_unsupported_preserves_existing_destination(tmp_path, monkeypatch):
    out = tmp_path / "r.pdf"
    out.write_bytes(b"MINE")
    _no_hardlinks(monkeypatch)
    with pytest.raises(FileExistsError):      # refused up front; link is never even attempted
        export_pdf(out, PROJECT, [FINDING], "en")
    assert out.read_bytes() == b"MINE" and [p.name for p in tmp_path.iterdir()] == ["r.pdf"]


def test_hardlink_unsupported_and_foreign_file_appears_keeps_foreign_file(tmp_path, monkeypatch):
    _no_hardlinks(monkeypatch)
    out = tmp_path / "r.pdf"
    real = ex.render_pdf

    def race(tmp, *a, **k):
        real(tmp, *a, **k)
        out.write_bytes(b"FOREIGN")
    monkeypatch.setattr(ex, "render_pdf", race)
    with pytest.raises(ex.ExportPublishError):
        export_pdf(out, PROJECT, [FINDING], "en")
    assert out.read_bytes() == b"FOREIGN" and [p.name for p in tmp_path.iterdir()] == ["r.pdf"]


def test_destination_created_by_another_process_during_render_is_untouched(tmp_path, monkeypatch):
    """A genuinely separate OS process creates the destination while we are rendering."""
    import subprocess
    import sys
    out = tmp_path / "r.pdf"
    real = ex.render_pdf

    def render_with_other_process(tmp, *a, **k):
        real(tmp, *a, **k)
        subprocess.run([sys.executable, "-I", "-c",
                        "import sys; open(sys.argv[1],'wb').write(b'OTHER PROCESS DATA')", str(out)],
                       check=True)
    monkeypatch.setattr(ex, "render_pdf", render_with_other_process)
    with pytest.raises(FileExistsError):
        export_pdf(out, PROJECT, [FINDING], "en")
    assert out.read_bytes() == b"OTHER PROCESS DATA"
    assert [p.name for p in tmp_path.iterdir()] == ["r.pdf"]


def test_overwrite_capable_calls_are_never_used_to_publish(tmp_path, monkeypatch):
    """Regression: no os.replace / os.rename / shutil.move / Path.replace/rename/write on the
    destination in any outcome (success, link failure, existing destination, render failure)."""
    import shutil
    calls = []

    def forbid(name):
        def f(*a, **k):
            calls.append(name)
            raise AssertionError(f"unsafe overwrite-capable call: {name}")
        return f
    monkeypatch.setattr(os, "replace", forbid("os.replace"))
    monkeypatch.setattr(os, "rename", forbid("os.rename"))
    monkeypatch.setattr(shutil, "move", forbid("shutil.move"))
    monkeypatch.setattr(Path, "replace", forbid("Path.replace"))
    monkeypatch.setattr(Path, "rename", forbid("Path.rename"))

    ok = tmp_path / "ok.pdf"
    export_pdf(ok, PROJECT, [FINDING], "en")                       # success path
    assert ok.read_bytes().startswith(b"%PDF")
    with pytest.raises(FileExistsError):                           # existing destination
        export_pdf(ok, PROJECT, [FINDING], "en")
    real_link = os.link
    _no_hardlinks(monkeypatch)
    with pytest.raises(ex.ExportPublishError):                     # link unsupported
        export_pdf(tmp_path / "nolink.pdf", PROJECT, [FINDING], "en")
    monkeypatch.setattr(os, "link", real_link)
    monkeypatch.setattr(ex, "render_pdf", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):                              # render failure
        export_pdf(tmp_path / "fail.pdf", PROJECT, [FINDING], "en")
    assert calls == []
    assert [p.name for p in tmp_path.iterdir()] == ["ok.pdf"]


def test_source_has_no_overwrite_capable_calls_in_publish_function():
    import inspect
    src = inspect.getsource(ex._publish_no_overwrite)
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith(("#",)))
    body = code.split('"""')[-1]            # drop the docstring
    for bad in ("os.replace", "os.rename", ".replace(", ".rename(", "shutil", "O_EXCL"):
        assert bad not in body, bad


def test_concurrent_exports_to_different_destinations_both_succeed(tmp_path, monkeypatch):
    real = ex.render_pdf
    barrier = threading.Barrier(2, timeout=10)

    def slow(tmp, *a, **k):
        barrier.wait()           # both renders are in flight at the same moment
        real(tmp, *a, **k)
    monkeypatch.setattr(ex, "render_pdf", slow)
    errors = []

    def run(name):
        try:
            export_pdf(tmp_path / name, PROJECT, [FINDING], "en")
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=run, args=(n,)) for n in ("a.pdf", "b.pdf")]
    [t.start() for t in ts]
    [t.join(30) for t in ts]
    assert errors == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.pdf", "b.pdf"]
    assert all((tmp_path / n).read_bytes().startswith(b"%PDF") for n in ("a.pdf", "b.pdf"))


def test_missing_destination_directory_gives_error_and_no_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        export_pdf(tmp_path / "nodir" / "r.pdf", PROJECT, [FINDING], "en")
    assert list(tmp_path.iterdir()) == []
