# Persian PDF - validation checklist (NOT yet performed)

Status: **code ready, never run with the real font and libraries.** `PERSIAN_PDF_VALIDATED = False`
in `reporting/exporters.py` makes `export_pdf(..., "fa")` refuse to produce output. The flag may only
be set to `True` after every item below passed on REAL output and the result is recorded in the
test report.

## Run
```
python tools/make_validation_reports.py --out samples --persian
```
(requires the files of docs/OFFLINE_DEPENDENCIES.md, priority 1). It writes `samples/report_fa.pdf`
and `samples/report_en.pdf` with: Persian title, mixed Persian/English text, `https://example.com`,
`192.0.2.10`, `CVE-2025-12345`, a table (title / severity / status / remediation) and a long Persian
paragraph that continues on the next page.

## Checks - each looked at on rendered pages (`pdftoppm -r 100 -png`), not only in code
| # | Check | Pass criterion |
|---|---|---|
| 1 | Letter shaping | Letters are joined (initial/medial/final forms); no isolated-letter "typewriter" look; lam-alef ligature correct; ZWNJ words (e.g. وب‌سایت) not split or joined wrongly |
| 2 | Persian-only specific letters | پ چ ژ گ ک ی render correctly (Persian shapes, not Arabic ك ي) |
| 3 | Direction | Persian lines read right-to-left, right-aligned; English-only values are left-to-right intact |
| 4 | Mixed lines | In a Persian sentence, `https://example.com`, `192.0.2.10`, `CVE-2025-12345` are intact, in left-to-right order, positioned correctly; trailing punctuation (، ؛ . ) ) lands on the correct side |
| 5 | Digits | Latin digits (page numbers, IP) are not reversed (`10.2.0.291` would be a failure) |
| 6 | Table | First column ("ردیف") is rightmost; header repeated on a continuation page; no clipped or overlapping cells; wrapped cells keep line order |
| 7 | Long paragraph | Line order top-to-bottom is the reading order; the break at the page end loses and repeats no line; no line wider than the frame |
| 8 | Footer | "صفحه n از N" correct on every page, N equals the page count |
| 9 | Text extraction | `pdftotext` returns the Persian text (copy-paste works) - note extraction order of presentation forms is a known limitation, record what is observed |
| 10 | Fonts | `pdffonts` shows Vazirmatn embedded (subset), no Type 3 fallbacks, no missing-glyph boxes |
| 11 | English report | unchanged and still correct after the Persian run |
| 12 | Failure mode | Remove the font (or library) -> readable error, no file written, previous file untouched |

## Known risks to look at specifically (they could not be tested here)
* `arabic_reshaper.ArabicReshaper().reshape` output must be covered by the font's glyphs. The code
  raises `ReportRenderingError` listing missing code points instead of drawing boxes; if Vazirmatn lacks
  presentation forms, a different reshaper configuration is needed.
* `get_display(text, base_dir="R")`: the keyword and the 0.4.x vs 0.5+ import path follow the
  documented API but were only exercised with fakes.
* Word-by-word wrapping uses widths of the reshaped text; a very long word is split by characters,
  which can break joining at the split point (edge case).
* Persian text inside an *English-layout* report is rejected with an error (not yet supported).
* `unicodedata`/NFC normalisation and stripping of bidi-control characters are applied to all
  untrusted text; legitimate use of those controls in findings would be lost.

Do not set `PERSIAN_PDF_VALIDATED = True` (and do not call the Persian PDF complete) before this table
is fully ticked on real output.
