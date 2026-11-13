"""English report: independent of the Persian toolchain. Real PDFs are generated and read back."""
import re

import pdfplumber
import pytest
from pypdf import PdfReader

from core.database import Database
from reporting.exporters import export_json, export_pdf
from reporting.rtl import clean_text
from reporting.rtl_support import ReportRenderingError

PROJECT = {"name": "Demo Corp", "target": "https://example.com", "authorized_by": "AUTH-1"}


def finding(i, **kw):
    d = dict(id=i, title=f"Finding {i}", severity="Low", confidence="Medium", status="Needs review",
             url="https://example.com", evidence="ev", remediation="rem", reference="ref")
    d.update(kw)
    return d


def text_of(path):
    return "\n".join(p.extract_text() for p in PdfReader(str(path)).pages)


def test_basic_content_and_summary_counts(tmp_path):
    out = tmp_path / "r.pdf"
    fs = [finding(1, severity="High"), finding(2, severity="Low"), finding(3, severity="Low")]
    export_pdf(out, PROJECT, fs, "en", generated_at="2026-11-12 05:00")
    t = text_of(out)
    for needle in ("Security Assessment Report", "Demo Corp", "https://example.com", "AUTH-1",
                   "2026-11-12 05:00", "Finding 1", "Finding details"):
        assert needle in t
    pdf = pdfplumber.open(out)
    rows = [r for tb in pdf.pages[0].extract_tables() for r in tb]
    assert ["High", "1"] in rows and ["Low", "2"] in rows and ["Total", "3"] in rows


def test_url_ip_cve_and_punctuation_are_preserved(tmp_path):
    out = tmp_path / "r.pdf"
    ev = "See https://example.com/a?b=1&c=2, IP 192.0.2.10 (CVE-2025-12345); ratio 3/4 - done."
    export_pdf(out, PROJECT, [finding(1, evidence=ev)], "en")
    flat = " ".join(text_of(out).split())
    assert "https://example.com/a?b=1&c=2," in flat and "192.0.2.10" in flat
    assert "CVE-2025-12345" in flat and "ratio 3/4 - done." in flat


def test_long_paragraph_flows_to_next_page_without_loss_or_reorder(tmp_path):
    out = tmp_path / "r.pdf"
    words = [f"w{i:04d}" for i in range(1, 1201)]
    # each field stays under MAX_FIELD_CHARS (4000) so nothing is truncated
    export_pdf(out, PROJECT, [finding(1, evidence=" ".join(words[:600])),
                              finding(2, evidence=" ".join(words[600:]))], "en")
    pages = PdfReader(str(out)).pages
    assert len(pages) >= 2
    got = re.findall(r"w\d{4}", text_of(out))
    assert got == words                                  # nothing lost, duplicated or reordered
    assert re.findall(r"w\d{4}", pages[1].extract_text())    # text really continues on page 2


def test_page_numbers_are_correct(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(i, evidence="word " * 780) for i in range(1, 7)], "en")
    pages = PdfReader(str(out)).pages
    n = len(pages)
    assert n >= 3
    for i, pg in enumerate(pages, 1):
        assert f"Page {i} of {n}" in pg.extract_text()


def test_findings_table_spans_pages_and_repeats_header(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(i) for i in range(1, 121)], "en")
    pdf = pdfplumber.open(out)
    heads = 0
    for pg in pdf.pages:
        for tb in pg.extract_tables():
            if tb and tb[0][:3] == ["#", "Title", "Severity"]:
                heads += 1
    assert heads >= 2


def test_nothing_is_drawn_outside_the_margins(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(1, url="https://example.com/" + "x" * 400,
                                      evidence="y" * 600)], "en")
    for pg in pdfplumber.open(out).pages:
        assert all(c["x1"] <= pg.width - 18 * 72 / 25.4 - 6 + 1.5 and c["x0"] >= 18 * 72 / 25.4 + 6 - 1.5
                   for c in pg.chars if c["top"] < pg.height - 20 * 72 / 25.4)   # body only, not the footer


def test_untrusted_markup_is_shown_literally(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, {"name": "<b>A</b> & <i>B</i>", "target": "https://example.com",
                     "authorized_by": "x"}, [finding(1, title="<script>alert(1)</script>")], "en")
    flat = text_of(out)
    assert "<b>A</b> & <i>B</i>" in flat and "<script>alert(1)</script>" in flat


def test_bidi_control_characters_are_stripped():
    assert clean_text("ab‮cd⁦ef\x00g\t.") == "abcdefg ."
    assert clean_text("می‌خواهم") == "می‌خواهم"        # ZWNJ is legitimate Persian


def test_non_latin1_characters_do_not_crash_or_print_boxes(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(1, title="中文 title")], "en")
    assert "title" in text_of(out)


def test_persian_content_in_english_report_fails_cleanly(tmp_path):
    out = tmp_path / "r.pdf"
    with pytest.raises(ReportRenderingError, match="No PDF was written"):
        export_pdf(out, PROJECT, [finding(1, title="عنوان فارسی")], "en")
    assert not out.exists() and not list(tmp_path.glob("*.tmp"))


def test_no_findings_message(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [], "en")
    assert "No findings were recorded." in text_of(out)


def test_unsupported_language(tmp_path):
    with pytest.raises(ValueError):
        export_pdf(tmp_path / "r.pdf", PROJECT, [], "de")
    assert not list(tmp_path.glob("*"))


def test_end_to_end_with_real_database_rows(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("Real", "https://example.com", "AUTH-9")
    db.add_finding(pid, "HSTS header not observed", "Low", "Low", "https://example.com",
                   "Needs review", "HTTP 200; header absent", "Enable HSTS", "OWASP")
    out = tmp_path / "r.pdf"
    export_pdf(out, db.projects()[0], db.findings(pid), "en", assets=db.assets(pid))
    t = text_of(out)
    assert "HSTS header not observed" in t and "Authorized assets (scope)" in t and "project target" in t


def test_json_export_roundtrip(tmp_path):
    import json
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("Real", "https://example.com", "AUTH-9")
    out = tmp_path / "r.json"
    export_json(out, db.projects()[0], db.findings(pid), db.assets(pid))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["version"] == "0.3" and data["project"]["name"] == "Real" and len(data["assets"]) == 1


def test_very_long_field_is_truncated_with_notice(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(1, evidence="word " * 3000)], "en")
    assert "(truncated)" in " ".join(text_of(out).split())
