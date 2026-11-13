"""export_pdf: never overwrite, unique temp names, failure cleanup, atomic publish."""
import errno
import os
import threading

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


def test_fallback_when_hard_links_unsupported(tmp_path, monkeypatch):
    def nolink(*a, **k):
        raise OSError(errno.EPERM, "hard links unsupported")
    monkeypatch.setattr(os, "link", nolink)
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [FINDING], "en")
    assert out.read_bytes().startswith(b"%PDF") and [p.name for p in tmp_path.iterdir()] == ["r.pdf"]
    before = out.read_bytes()
    with pytest.raises(FileExistsError):
        export_pdf(out, PROJECT, [FINDING], "en")
    assert out.read_bytes() == before


def test_fallback_race_keeps_foreign_file(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EPERM, "x")))
    out = tmp_path / "r.pdf"
    real = ex.render_pdf

    def race(tmp, *a, **k):
        real(tmp, *a, **k)
        out.write_bytes(b"FOREIGN")
    monkeypatch.setattr(ex, "render_pdf", race)
    with pytest.raises(FileExistsError):
        export_pdf(out, PROJECT, [FINDING], "en")
    assert out.read_bytes() == b"FOREIGN" and [p.name for p in tmp_path.iterdir()] == ["r.pdf"]


def test_missing_destination_directory_gives_error_and_no_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        export_pdf(tmp_path / "nodir" / "r.pdf", PROJECT, [FINDING], "en")
    assert list(tmp_path.iterdir()) == []
