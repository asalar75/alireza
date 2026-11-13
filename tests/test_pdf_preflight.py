import pytest

from reporting import rtl_support
from reporting.exporters import export_pdf
from reporting.rtl_support import ReportRenderingError, missing_persian_requirements

PROJECT = {"name": "Demo", "target": "https://example.com", "authorized_by": "AUTH-1"}
FINDINGS = [{"id": 1, "title": "HSTS header not observed", "severity": "Low",
             "confidence": "Low", "status": "Needs review"}]


def test_missing_font_and_libs_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(rtl_support.importlib.util, "find_spec", lambda name: None)
    problems = missing_persian_requirements(tmp_path)
    assert any("Vazirmatn-Regular.ttf" in p for p in problems)
    assert any("OFL.txt" in p for p in problems)
    assert any("arabic-reshaper" in p for p in problems) and any("python-bidi" in p for p in problems)


def test_persian_export_fails_cleanly_without_creating_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rtl_support, "FONT_DIR", tmp_path)       # empty dir: no font
    monkeypatch.setattr("reporting.exporters.require_persian_support",
                        lambda: rtl_support.require_persian_support(tmp_path))
    out = tmp_path / "fa.pdf"
    with pytest.raises(ReportRenderingError, match="Persian PDF cannot be generated"):
        export_pdf(out, PROJECT, FINDINGS, "fa")
    assert not out.exists() and not (tmp_path / "fa.pdf.tmp").exists()


def test_english_export_is_valid_pdf_and_atomic(tmp_path):
    out = tmp_path / "en.pdf"
    export_pdf(out, PROJECT, FINDINGS, "en")
    assert out.read_bytes().startswith(b"%PDF") and not (tmp_path / "en.pdf.tmp").exists()
    from pypdf import PdfReader
    text = "".join(p.extract_text() for p in PdfReader(out).pages)
    assert "Security Assessment Report" in text and "HSTS header not observed" in text


def test_failed_build_leaves_no_partial_file(tmp_path, monkeypatch):
    import reporting.exporters as ex
    class Boom:
        def __init__(self, *a, **k): pass
        def build(self, story, **kwargs): raise RuntimeError("render failed")
    monkeypatch.setattr(ex, "SimpleDocTemplate", Boom)
    out = tmp_path / "x.pdf"
    with pytest.raises(RuntimeError):
        export_pdf(out, PROJECT, FINDINGS, "en")
    assert not out.exists() and not (tmp_path / "x.pdf.tmp").exists()
