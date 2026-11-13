# Provenance of files found in the milestone-2 working tree

These four files were already present in `AegisSec_Enterprise_v0_3/` when it was copied to
`AegisSec_Enterprise_v0_3_m2/` (file times 2026-11-11 12:54-12:55, about 30 minutes after the
milestone-1 zip was produced at 12:23). They are **not in the milestone-1 zip** and I (the assistant)
did not write them in this conversation; the author of record is unknown to me. Their content states
"milestone 2, in progress" and describes the same blocker (font/libraries not obtainable offline).
Decision (per instruction): **kept, not deleted, not rewritten.** The only change touching one of
them is noted below.

| File | What it is | Used by code? | Relation to the current version |
|---|---|---|---|
| `reporting/rtl_support.py` | Pre-flight for Persian PDF: lists missing font files (`assets/fonts/Vazirmatn-Regular.ttf`, `-Bold.ttf`), license file `OFL.txt` and packages (`arabic_reshaper`, `bidi`); defines `ReportRenderingError`, `FONT_DIR`, `require_persian_support()` | **Yes.** Imported by `reporting/exporters.py` and `reporting/pdf_report.py`; tested by `tests/test_pdf_preflight.py` and the new report tests | Unmodified. It is the single source of the pre-flight and of the error type; the new code builds on it (font dir = `assets/fonts`) |
| `tests/test_pdf_preflight.py` | 4 tests: missing font/libs reported; Persian export fails cleanly without a file; English export valid + atomic; failed build leaves no partial file | Run by pytest (all 4 pass) | **One test double edited:** `Boom.build(self, story)` -> `build(self, story, **kwargs)` because the new renderer passes `canvasmaker=` (page numbers). Assertions unchanged |
| `assets/fonts/README.md` | Placeholder telling where font files and `OFL.txt` go | No (documentation only) | Still accurate; the font directory it describes is the one used |
| `docs/DEPENDENCIES_AND_LICENSES.md` | Font license check (OFL 1.1 summary) and dependency table, marked "partially complete" | Referenced only in the text of an error message in `rtl_support.py` | Kept as is. `docs/OFFLINE_DEPENDENCIES.md` adds the exact file list; the license conclusions are not duplicated there |

## Files I created and removed in this milestone (provenance proven)
`reporting/pdf_support.py`, `tests/test_pdf_support.py` and the directory `ui/resources/fonts/`:
written by me earlier in milestone 2 as a pre-flight, then found to duplicate `rtl_support.py`.
Before deleting I checked by search that nothing imported them (`exporters.py` was changed to use
`rtl_support`); the test file only tested the removed module.

## Note on the milestone-1 tree
`AegisSec_Enterprise_v0_3/` was not modified by this milestone. `diff -rq` between it and the m2 copy
(taken before the first m2 edit) showed exactly these differences: the four files above, the
`exporters.py` change, and nothing else under `core/`, `ui/` or the other tests.
