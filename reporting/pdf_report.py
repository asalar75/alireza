"""PDF report layout (ReportLab) for English and Persian.

Design notes
------------
* One layout engine for both languages; only strings, direction and font differ.
* ``BidiParagraph`` breaks lines on the LOGICAL text first, then shapes/reorders each line
  separately. Reordering a whole paragraph before wrapping reverses the line order of
  multi-line Persian paragraphs - this class avoids that by construction.
* Lines with no Arabic-script characters (URLs, IPs, CVE ids, English text) are never
  reordered; they are drawn as-is so they cannot be scrambled.
* Before drawing, every glyph is checked against the embedded font; a missing glyph raises
  ReportRenderingError instead of printing an empty box. The caller builds into a temp file,
  so a failure never leaves a partial PDF.
* Untrusted text (titles, evidence) is never interpreted as markup and has bidi-control
  characters stripped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, KeepTogether, SimpleDocTemplate, Spacer, Table, TableStyle

from .report_i18n import SEVERITY_ORDER, strings, value
from .rtl import TextShaper, clean_text, has_arabic_script
from .rtl_support import ReportRenderingError

PRODUCT = "AegisSec Enterprise"
VERSION = "0.3"
FONT_REG, FONT_BOLD = "AegisVazirmatn", "AegisVazirmatn-Bold"
MAX_FIELD_CHARS = 4000
FRAME_PAD = 6          # ReportLab Frame default left/right padding (points)
NAVY = colors.HexColor("#183B59")
BAND = colors.HexColor("#EEF3F7")
SEV_COLOR = {"Critical": "#8B0000", "High": "#C0392B", "Medium": "#D68910", "Low": "#1F6FB2", "Info": "#5D6D7E"}


@dataclass
class RenderContext:
    language: str
    rtl: bool
    regular: str
    bold: str
    ttf: bool                      # embedded TrueType font => glyph coverage can be verified
    shaper: Optional[TextShaper]
    s: dict
    demo: bool = False

    def missing_glyphs(self, fontname: str, text: str) -> set:
        if not self.ttf:
            return set()
        cmap = pdfmetrics.getFont(fontname).face.charToGlyph
        return {c for c in text if ord(c) not in cmap and c not in "\n‌‍"}


def _register_ttf(name: str, path: Path):
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(path)))


def make_context(language: str, *, font_dir: Path, shaper: Optional[TextShaper] = None,
                 demo: bool = False) -> RenderContext:
    s = strings(language)
    if language == "fa":
        reg, bold = Path(font_dir) / "Vazirmatn-Regular.ttf", Path(font_dir) / "Vazirmatn-Bold.ttf"
        _register_ttf(FONT_REG, reg)
        _register_ttf(FONT_BOLD, bold)
        if shaper is None:
            try:
                shaper = TextShaper.default()
            except ImportError as exc:
                raise ReportRenderingError(
                    f"Persian shaping library missing ({exc.name}); see docs/OFFLINE_DEPENDENCIES.md") from exc
        return RenderContext("fa", True, FONT_REG, FONT_BOLD, True, shaper, s, demo)
    # English: built-in Helvetica. Persian text inside an English report needs shaping + a
    # font that has the glyphs; that is only possible when the Persian toolchain is installed.
    ctx = RenderContext("en", False, "Helvetica", "Helvetica-Bold", False, shaper, s, demo)
    return ctx


class BidiParagraph(Flowable):
    """Left- or right-aligned text block with logical-order line breaking."""

    def __init__(self, text, ctx: RenderContext, *, size=9, bold=False, color=colors.black,
                 leading=None, keep_with_next=False, _lines=None, _visual=None):
        super().__init__()
        self.ctx, self.size = ctx, size
        self.color, self.leading = color, leading or size * 1.45
        self.font = ctx.bold if bold else ctx.regular
        self.text = clean_text(text)
        self.spaceBefore = self.spaceAfter = 0
        self.keepWithNext = keep_with_next
        self._lines, self._visual, self._w = _lines, _visual, None

    # -- shaping ---------------------------------------------------------------
    def _sanitize_for_font(self, line: str) -> str:
        if not self.ctx.ttf:                       # Helvetica: WinAnsi only
            return line.encode("cp1252", "replace").decode("cp1252")
        return line

    def _to_visual(self, line: str) -> str:
        c = self.ctx
        if not has_arabic_script(line):
            return self._sanitize_for_font(line)
        if c.shaper is None:
            raise ReportRenderingError(
                "The report contains Persian/Arabic text but the Persian toolchain (font + "
                "arabic-reshaper + python-bidi) is not available. No PDF was written; see "
                "docs/OFFLINE_DEPENDENCIES.md.")
        if not c.ttf:
            raise ReportRenderingError(
                "Persian text inside an English-layout report is not supported yet; "
                "export this project as a Persian report. No PDF was written.")
        return c.shaper.display(c.shaper.reshape(line), base_rtl=True)

    def _width(self, line: str) -> float:
        return pdfmetrics.stringWidth(self._shape_only(line), self.font, self.size)

    def _shape_only(self, line: str) -> str:
        if has_arabic_script(line) and self.ctx.shaper is not None and self.ctx.ttf:
            return self.ctx.shaper.reshape(line)
        return self._sanitize_for_font(line)

    # -- layout ---------------------------------------------------------------
    def _break(self, width: float) -> list[str]:
        lines: list[str] = []
        for seg in self.text.split("\n"):
            cur = ""
            for word in seg.split(" "):
                cand = word if not cur else cur + " " + word
                if self._width(cand) <= width:
                    cur = cand
                    continue
                if cur:
                    lines.append(cur)
                    cur = ""
                while self._width(word) > width and len(word) > 1:      # e.g. a very long URL
                    k = 1
                    for i in range(2, len(word) + 1):
                        if self._width(word[:i]) <= width:
                            k = i
                        else:
                            break
                    lines.append(word[:k])
                    word = word[k:]
                cur = word
            lines.append(cur)
        return lines

    def wrap(self, availWidth, availHeight):
        if self._lines is None or self._w != availWidth:
            self._lines = self._break(availWidth)
            self._visual = None
        self._w = availWidth
        if self._visual is None:
            self._visual = [self._to_visual(l) for l in self._lines]
            for v in self._visual:
                miss = self.ctx.missing_glyphs(self.font, v)
                if miss:
                    raise ReportRenderingError(
                        "The font has no glyph for " + ", ".join(f"U+{ord(c):04X}" for c in sorted(miss)) +
                        ". No PDF was written.")
        self.width, self.height = availWidth, len(self._lines) * self.leading
        return self.width, self.height

    def split(self, availWidth, availHeight):
        if self._lines is None or self._w != availWidth:
            self.wrap(availWidth, availHeight)
        n = int(availHeight // self.leading)
        if n >= len(self._lines):
            return [self]
        if n <= 0:
            return []
        kw = dict(size=self.size, color=self.color, leading=self.leading)
        a = BidiParagraph("", self.ctx, **kw, _lines=self._lines[:n], _visual=self._visual[:n])
        b = BidiParagraph("", self.ctx, **kw, _lines=self._lines[n:], _visual=self._visual[n:])
        for p in (a, b):
            p.font, p._w = self.font, availWidth
        return [a, b]

    def draw(self):
        c = self.canv
        c.setFillColor(self.color)
        c.setFont(self.font, self.size)
        for i, line in enumerate(self._visual):
            y = self.height - i * self.leading - self.size
            if self.ctx.rtl:
                c.drawRightString(self.width, y, line)
            else:
                c.drawString(0, y, line)


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas so the footer can print 'Page n of N'."""

    def __init__(self, *a, ctx: RenderContext, **k):
        super().__init__(*a, **k)
        self._ctx, self._saved = ctx, []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._footer(total)
            super().showPage()
        super().save()

    def _footer(self, total):
        c, s = self._ctx, self._ctx.s
        self.setFont(c.regular, 8)
        self.setFillColor(colors.HexColor("#5D6D7E"))
        w, _ = A4
        page = f"{s['page']} {self._pageNumber} {s['of']} {total}"
        if c.rtl:
            visual = c.shaper.display(c.shaper.reshape(page), base_rtl=True)
            self.drawCentredString(w / 2, 10 * mm, visual)
            self.drawString(18 * mm, 10 * mm, f"{PRODUCT} {VERSION}")
        else:
            self.drawCentredString(w / 2, 10 * mm, page)
            self.drawRightString(w - 18 * mm, 10 * mm, f"{PRODUCT} {VERSION}")
        if c.demo:
            self.setFillColor(colors.HexColor("#B03A2E"))
            self.setFont(c.bold, 8)
            label = s["demo_footer"]
            if c.rtl:
                label = c.shaper.display(c.shaper.reshape(label), base_rtl=True)
            self.drawCentredString(w / 2, 5 * mm, label)
        self.setStrokeColor(colors.HexColor("#C5D0DA"))
        self.line(18 * mm, 15 * mm, w - 18 * mm, 15 * mm)


# ------------------------------------------------------------------------- content
def _get(row, key, default=""):
    """Field access that works for dicts and sqlite3.Row and tolerates absent optional fields."""
    try:
        v = row[key]
    except (KeyError, IndexError):
        return default
    return default if v is None else v


def _clip(ctx, text):
    t = clean_text(text)
    return t if len(t) <= MAX_FIELD_CHARS else t[:MAX_FIELD_CHARS] + " " + ctx.s["truncated"]


CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.I)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\u061f])\s+")
_TEST_DATA_RE = re.compile(r"(?:\bexample\.(?:com|org|net)\b|\b(?:192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}\b)", re.I)


def collapse_repeats(text: str, min_repeat: int = 3) -> str:
    """Collapse runs of >= ``min_repeat`` identical consecutive lines or sentences into one
    occurrence followed by ``[xN]`` - the count is shown, so nothing is hidden silently."""
    def collapse(units):
        out, i = [], 0
        while i < len(units):
            j = i
            while j + 1 < len(units) and units[j + 1] == units[i]:
                j += 1
            n = j - i + 1
            if n >= min_repeat:
                out.append(f"{units[i]} [\u00d7{n}]")
            else:
                out.extend(units[i:j + 1])
            i = j + 1
        return out
    lines = collapse(text.split("\n"))
    return "\n".join(" ".join(collapse(_SENTENCE_SPLIT.split(l))) for l in lines)


def _cve_note(ctx, finding):
    status = str(_get(finding, "status"))
    if status == "Confirmed":
        return ""
    ids = []
    for key in ("title", "evidence", "remediation", "reference"):
        ids += [m.upper() for m in CVE_RE.findall(str(_get(finding, key)))]
    ids = list(dict.fromkeys(ids))
    return ctx.s["cve_unconfirmed"].format(ids=", ".join(ids)) if ids else ""


def looks_like_test_data(project, findings) -> bool:
    blob = " ".join([str(_get(project, "target")), str(_get(project, "name"))] + [
        str(_get(f, k)) for f in findings for k in ("url", "title", "evidence")])
    return bool(_TEST_DATA_RE.search(blob))


def _table(ctx, rows, widths, *, header=True, zebra=True):
    """RTL tables list columns right-to-left: column 1 is rightmost."""
    if ctx.rtl:
        rows = [list(reversed(r)) for r in rows]
        widths = list(reversed(widths))
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0,
              hAlign="RIGHT" if ctx.rtl else "LEFT")
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA8B5")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra and len(rows) > 2:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]))
    t.setStyle(TableStyle(style))
    return t


def build_story(ctx: RenderContext, project, findings, assets, generated_at: str, content_width: float):
    s, lang = ctx.s, ctx.language
    P = lambda text, **k: BidiParagraph(text, ctx, **k)
    story = [P(s["title"], size=20, bold=True, color=NAVY), Spacer(1, 10)]
    if ctx.demo:
        story += [P(s["demo_banner"], size=9.5, bold=True, color=colors.HexColor("#B03A2E")), Spacer(1, 8)]
    elif looks_like_test_data(project, findings):
        story += [P(s["testdata_warning"], size=9.5, bold=True, color=colors.HexColor("#B03A2E")), Spacer(1, 8)]

    meta = [[P(s["project"], bold=True), P(project["name"])],
            [P(s["target"], bold=True), P(project["target"])],
            [P(s["auth_ref"], bold=True), P(project["authorized_by"])],
            [P(s["generated"], bold=True), P(generated_at)],
            [P(s["tool"], bold=True), P(f"{PRODUCT} {VERSION}")]]
    story += [_table(ctx, meta, [content_width * 0.3, content_width * 0.7], header=False, zebra=False),
              Spacer(1, 12)]

    counts = {k: 0 for k in SEVERITY_ORDER}
    for f in findings:
        sev = _get(f, "severity", "Info")
        counts[sev] = counts.get(sev, 0) + 1
    story.append(P(s["summary"], size=13, bold=True, color=NAVY, keep_with_next=True))
    story.append(Spacer(1, 4))
    rows = [[P(s["col_severity"], bold=True, color=colors.white), P(s["count"], bold=True, color=colors.white)]]
    for k in [*SEVERITY_ORDER, *[x for x in counts if x not in SEVERITY_ORDER]]:
        rows.append([P(value(lang, k), bold=True, color=colors.HexColor(SEV_COLOR.get(k, "#000000"))),
                     P(str(counts.get(k, 0)))])
    rows.append([P(s["total"], bold=True), P(str(len(findings)), bold=True)])
    story += [_table(ctx, rows, [content_width * 0.35, content_width * 0.2]), Spacer(1, 14)]

    story.append(P(s["findings"], size=13, bold=True, color=NAVY, keep_with_next=True))
    story.append(Spacer(1, 4))
    if not findings:
        story.append(P(s["no_findings"]))
    else:
        w = content_width
        head = [P(s["col_no"], bold=True, color=colors.white), P(s["col_title"], bold=True, color=colors.white),
                P(s["col_severity"], bold=True, color=colors.white), P(s["col_status"], bold=True, color=colors.white),
                P(s["col_remediation"], bold=True, color=colors.white)]
        rows = [head]
        for f in findings:
            rows.append([P(str(f["id"])), P(_clip(ctx, _get(f, "title"))), P(value(lang, _get(f, "severity"))),
                         P(value(lang, _get(f, "status"))), P(_clip(ctx, _get(f, "remediation")) or s["none"])])
        story.append(_table(ctx, rows, [w * 0.10, w * 0.28, w * 0.12, w * 0.15, w * 0.35]))
        story += [Spacer(1, 14), P(s["details"], size=13, bold=True, color=NAVY, keep_with_next=True), Spacer(1, 4)]
        for f in findings:
            story.append(P(f"{f['id']}. {_clip(ctx, _get(f, 'title'))}", size=10.5, bold=True, keep_with_next=True))
            story.append(Spacer(1, 2))
            for label, key in (("url", "url"), ("confidence", "confidence"), ("evidence", "evidence"),
                               ("reference", "reference"), ("col_remediation", "remediation")):
                raw = _get(f, key)
                txt = value(lang, raw) if key == "confidence" else _clip(ctx, collapse_repeats(clean_text(raw)) if key == "evidence" else raw)
                story.append(P(f"{s[label]}: {txt or s['none']}", size=9))
                story.append(Spacer(1, 2))
            note = _cve_note(ctx, f)
            if note:
                story.append(P(note, size=8.5, color=colors.HexColor("#B03A2E")))
                story.append(Spacer(1, 2))
            story.append(Spacer(1, 8))

    if assets:
        story += [P(s["scope"], size=13, bold=True, color=NAVY, keep_with_next=True), Spacer(1, 4)]
        w = content_width
        rows = [[P(s["origin"], bold=True, color=colors.white), P(s["type"], bold=True, color=colors.white),
                 P(s["notes"], bold=True, color=colors.white)]]
        for a in assets:
            rows.append([P(_get(a, "origin")), P(value(lang, _get(a, "asset_type"))),
                         P(_clip(ctx, _get(a, "notes")) or s["none"])])
        story += [_table(ctx, rows, [w * 0.45, w * 0.2, w * 0.35]), Spacer(1, 14)]

    story.append(P(s["disclaimer"], size=8.5, color=colors.HexColor("#5D6D7E")))
    return story


def render_pdf(path, ctx: RenderContext, project, findings, assets=(), generated_at=None,
               doc_class=SimpleDocTemplate):
    """Render to ``path`` (caller is responsible for atomic replacement)."""
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    margin = 18 * mm
    doc = doc_class(str(path), pagesize=A4, leftMargin=margin, rightMargin=margin,
                            topMargin=18 * mm, bottomMargin=22 * mm,
                            title=ctx.s["title"], author=PRODUCT, subject=clean_text(project["name"]))
    story = build_story(ctx, project, list(findings), list(assets), generated_at, A4[0] - 2 * margin - 2 * FRAME_PAD)
    doc.build(story, canvasmaker=lambda *a, **k: NumberedCanvas(*a, ctx=ctx, **k))
