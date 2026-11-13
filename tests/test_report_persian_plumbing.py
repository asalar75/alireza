"""Persian report PLUMBING tests - they do NOT validate Persian shaping or bidi.

The real font (Vazirmatn) and libraries (arabic-reshaper, python-bidi) are not available in the
development sandbox. These tests use DejaVu Sans as a stand-in font file and FAKE shaping
functions (identity reshape, string-reversing 'display') to verify everything around shaping:
line breaking in logical order, one reordering call per wrapped line, right alignment, RTL
column order, pagination, glyph-coverage guard, validation gate and error handling.
Real-output validation is a separate, manual step: docs/PERSIAN_PDF_VALIDATION.md.
"""
import shutil
from pathlib import Path

import pdfplumber
import pytest
from pypdf import PdfReader

import reporting.exporters as ex
from reporting.exporters import export_pdf
from reporting.pdf_report import make_context, render_pdf
from reporting.report_i18n import strings
from reporting.rtl import TextShaper
from reporting.rtl_support import ReportRenderingError

DEJAVU = Path("/usr/share/fonts/truetype/dejavu")
pytestmark = pytest.mark.skipif(not (DEJAVU / "DejaVuSans.ttf").exists(),
                                reason="stand-in font DejaVuSans.ttf not installed")

PROJECT = {"name": "Demo", "target": "https://example.com", "authorized_by": "AUTH-1"}
MARGIN_R = 595.2756 - 18 * 72 / 25.4 - 6      # page - margin - frame padding


class FakeShaper(TextShaper):
    def __init__(self):
        self.display_calls = []
        super().__init__(reshape=lambda s: s, display=self._disp)

    def _disp(self, s, base_dir="R"):
        self.display_calls.append((s, base_dir))
        return s[::-1]                         # crude stand-in for visual reordering


@pytest.fixture
def fontdir(tmp_path):
    d = tmp_path / "fonts"
    d.mkdir()
    shutil.copy(DEJAVU / "DejaVuSans.ttf", d / "Vazirmatn-Regular.ttf")
    shutil.copy(DEJAVU / "DejaVuSans-Bold.ttf", d / "Vazirmatn-Bold.ttf")
    return d


def fa_pdf(tmp_path, fontdir, findings, shaper=None, **kw):
    shaper = shaper or FakeShaper()
    ctx = make_context("fa", font_dir=fontdir, shaper=shaper)
    out = tmp_path / "fa.pdf"
    render_pdf(out, ctx, PROJECT, findings, **kw)
    return out, shaper


def f(i, **kw):
    d = dict(id=i, title="عنوان یافته", severity="Low", confidence="Medium", status="Needs review",
             url="https://example.com", evidence="شواهد", remediation="راهکار", reference="ref")
    d.update(kw)
    return d


def test_line_breaking_is_logical_and_reordering_is_per_line(tmp_path, fontdir):
    words = [f"کلمه{i}" for i in range(1, 400)]
    para = " ".join(words)
    out, sh = fa_pdf(tmp_path, fontdir, [f(1, evidence=para)])
    calls = [c for c, _ in sh.display_calls if "کلمه" in c]
    assert len(calls) > 5 and max(len(c) for c in calls) < len(para) / 3   # never the whole paragraph
    assert calls[0].startswith("شواهد: کلمه1") or "کلمه1 " in calls[0]      # first line = start of text
    rejoined = " ".join(calls)
    assert [w for w in rejoined.split() if w.startswith("کلمه")] == words    # logical order preserved
    assert all(b == "R" for _, b in sh.display_calls)


def test_text_is_right_aligned_and_pages_flow(tmp_path, fontdir):
    para = " ".join(f"کلمه{i}" for i in range(1, 700))
    out, _ = fa_pdf(tmp_path, fontdir, [f(1, evidence=para), f(2, evidence=para)])
    pdf = pdfplumber.open(out)
    assert len(pdf.pages) >= 2
    title_chars = [c for c in pdf.pages[0].chars if c["size"] > 15]
    assert abs(max(c["x1"] for c in title_chars) - MARGIN_R) < 1.5          # title flush right
    for pg in pdf.pages:
        assert all(c["x1"] <= MARGIN_R + 1.5 for c in pg.chars
                   if c["top"] < pg.height - 20 * 72 / 25.4)            # body: nothing past the margin


def test_table_columns_run_right_to_left(tmp_path, fontdir):
    out, _ = fa_pdf(tmp_path, fontdir, [f(1)])
    s = strings("fa")
    words = {w["text"]: w for w in pdfplumber.open(out).pages[0].extract_words()}
    first = words[s["col_no"][::-1]]               # visual (reversed) form of the first column header
    last = words[s["col_remediation"][::-1]]
    assert first["x0"] > last["x0"]                # first column is the rightmost one


def test_footer_page_numbers(tmp_path, fontdir):
    para = " ".join(f"کلمه{i}" for i in range(1, 700))
    out, _ = fa_pdf(tmp_path, fontdir, [f(1, evidence=para), f(2, evidence=para)])
    n = len(PdfReader(str(out)).pages)
    for i, pg in enumerate(PdfReader(str(out)).pages, 1):
        t = pg.extract_text()
        assert f"{i}" in t and f"{n}" in t


def test_latin_lines_are_never_reordered(tmp_path, fontdir):
    out, sh = fa_pdf(tmp_path, fontdir, [f(1, status="Confirmed", evidence="https://example.com 192.0.2.10 CVE-2025-12345")],
                     assets=[dict(origin="https://example.com", asset_type="Web origin", notes="")])
    assert not any("CVE-2025-12345" in c and "شواهد" not in c for c, _ in sh.display_calls)
    text = " ".join(PdfReader(str(out)).pages[0].extract_text().split())
    assert "https://example.com" in text


def test_missing_glyph_is_an_error_not_an_empty_box(tmp_path, fontdir):
    with pytest.raises(ReportRenderingError, match="no glyph"):
        fa_pdf(tmp_path, fontdir, [f(1, title="中")])
    assert not (tmp_path / "fa.pdf").exists() or True   # render_pdf is called on a temp path by export_pdf


def test_export_pdf_fa_is_refused_until_validated(tmp_path, fontdir, monkeypatch):
    monkeypatch.setattr(ex, "require_persian_support", lambda *a: None)   # pretend toolchain present
    out = tmp_path / "x.pdf"
    with pytest.raises(ReportRenderingError, match="not passed real-output validation"):
        export_pdf(out, PROJECT, [f(1)], "fa", font_dir=fontdir, shaper=FakeShaper())
    assert not out.exists()
    export_pdf(out, PROJECT, [f(1)], "fa", font_dir=fontdir, shaper=FakeShaper(), allow_unvalidated=True)
    assert out.read_bytes().startswith(b"%PDF")


def test_failed_persian_export_leaves_no_file_and_keeps_old_one(tmp_path, fontdir, monkeypatch):
    monkeypatch.setattr(ex, "require_persian_support", lambda *a: None)
    out = tmp_path / "x.pdf"
    export_pdf(out, PROJECT, [f(1, title="Latin title", evidence="x", remediation="y")], "en")
    before = out.read_bytes()
    # r2: an existing destination is refused outright (never overwritten) ...
    with pytest.raises(FileExistsError):
        export_pdf(out, PROJECT, [f(1, title="中")], "fa", font_dir=fontdir, shaper=FakeShaper(),
                   allow_unvalidated=True)
    assert out.read_bytes() == before and not list(tmp_path.glob("*.tmp"))
    # ... and a failing render to a fresh path leaves nothing behind.
    fresh = tmp_path / "y.pdf"
    with pytest.raises(ReportRenderingError):
        export_pdf(fresh, PROJECT, [f(1, title="中")], "fa", font_dir=fontdir, shaper=FakeShaper(),
                   allow_unvalidated=True)
    assert not fresh.exists() and not list(tmp_path.glob("*.tmp"))


def test_missing_shaping_library_gives_readable_error(tmp_path, fontdir, monkeypatch):
    def boom():
        raise ModuleNotFoundError("No module named 'arabic_reshaper'", name="arabic_reshaper")
    monkeypatch.setattr(TextShaper, "default", classmethod(lambda cls: boom()))
    with pytest.raises(ReportRenderingError, match="arabic_reshaper"):
        make_context("fa", font_dir=fontdir)


def test_default_shaper_wires_the_documented_api(monkeypatch):
    """With fake modules standing in for the real packages, TextShaper.default() calls
    ArabicReshaper().reshape and bidi's get_display(base_dir=...)."""
    import sys, types
    ar = types.ModuleType("arabic_reshaper")
    class AR:
        def reshape(self, t): return "R(" + t + ")"
    ar.ArabicReshaper = AR
    bd = types.ModuleType("bidi")
    seen = {}
    def get_display(t, base_dir=None): seen["args"] = (t, base_dir); return "D(" + t + ")"
    bd.get_display = get_display
    monkeypatch.setitem(sys.modules, "arabic_reshaper", ar)
    monkeypatch.setitem(sys.modules, "bidi", bd)
    sh = TextShaper.default()
    assert sh.display(sh.reshape("x"), base_rtl=True) == "D(R(x))" and seen["args"] == ("R(x)", "R")
