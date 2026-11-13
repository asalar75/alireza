# AegisSec 0.3 - milestone 2 (Persian PDF preparation) - test report

Command: `python -I -m pytest -q -p no:cacheprovider tests` - Linux sandbox, **Python 3.13.18**, reportlab 5.0.1.

| Result | Count |
|---|---:|
| Executed | 106 |
| Passed | 106 |
| Failed | 0 |
| Skipped | 0 (the 10 Persian-plumbing tests would be skipped on a machine without DejaVu Sans) |

| File | Tests | What it proves |
|---|---:|---|
| test_scope, test_database_*, test_audit_chain, test_operations_and_scan | 62 | milestone 1 - unchanged, still passing |
| test_pdf_preflight | 4 | pre-existing pre-flight tests (see docs/FILE_PROVENANCE.md; one test double adjusted) |
| test_report_english | 15 | **real English PDFs** generated and read back (pypdf/pdfplumber): content, summary counts, URL/IP/CVE/punctuation intact, long paragraph continues on page 2 without loss/reorder/duplication, page numbers "n of N", table header repeated across pages, nothing outside margins, markup shown literally, bidi controls stripped, truncation notice, Persian content in English report -> error and no file, DB-row end-to-end, JSON export |
| test_report_persian_plumbing | 10 | **plumbing only**, with DejaVu Sans as stand-in font and FAKE shaping (see module docstring): logical-order wrapping, one reordering call per wrapped line, right alignment, RTL column order, pagination, glyph-coverage guard, validation gate, error handling, wiring to the documented library API (with fake modules) |
| test_offline_bundle_tool | 15 | wheel-tag compatibility (3.12 / win_amd64), missing/ambiguous/unlisted files, hash record + tamper detection, manifest well-formed |

Also done: the English sample (`samples/report_en.pdf`, 2 pages) was rendered to PNG and looked at.

## NOT done / NOT verified (explicit)
* **No Persian PDF was produced and none is declared complete.** The Vazirmatn font, `arabic-reshaper`
  and `python-bidi` are absent; `export_pdf(..., "fa")` raises a readable error and writes nothing
  (verified by running `tools/make_validation_reports.py --persian`, exit code 2).
* Letter shaping, bidi ordering of mixed Persian/English text and Persian page layout were **never
  executed with the real libraries**. The plumbing tests cannot detect a wrong shaping result.
  `PERSIAN_PDF_VALIDATED` stays `False` until docs/PERSIAN_PDF_VALIDATION.md is fully ticked.
* The layout of the Persian report was looked at once using the stand-in font and a fake reordering
  function (right alignment, mirrored table, page flow looked as intended); that picture is NOT evidence
  of correct Persian rendering and is not part of the deliverable.
* **Python 3.12** was not used for this milestone: `reportlab` is not installed for 3.12 in the sandbox.
* **Windows**, PySide6 UI, `httpx` real requests: unchanged from milestone 1 - still not run.
* Dependency versions marked CANDIDATE in docs/OFFLINE_DEPENDENCIES.md are unverified.
* Dependency lock file and vulnerability audit (item F) are not started, as agreed.
* Version 0.3 is NOT declared ready for release; no final integration was done.
