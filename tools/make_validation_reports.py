#!/usr/bin/env python3
"""Build the sample reports (docs/PERSIAN_PDF_VALIDATION.md). ALL data is fictional DEMO data
(tools/sample_data.py) and the reports are marked DEMO.

    python tools/make_validation_reports.py --out samples            # English only
    python tools/make_validation_reports.py --out samples --persian  # also the Persian report

The Persian run uses allow_unvalidated=True: it is THE validation run. Without the font and
libraries it stops with a readable error and writes nothing.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sample_data as sd  # noqa: E402
from reporting.exporters import export_pdf  # noqa: E402
from reporting.rtl_support import ReportRenderingError  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("samples"))
    ap.add_argument("--persian", action="store_true")
    a = ap.parse_args()
    for lang in (("en", "fa") if a.persian else ("en",)):
        problems = sd.validate_all(lang)
        if problems:                                # never publish inconsistent sample data
            print("sample data inconsistent:", problems)
            return 3
    a.out.mkdir(parents=True, exist_ok=True)
    export_pdf(a.out / "report_en.pdf", sd.PROJECT["en"], sd.findings("en"), "en", assets=sd.ASSETS, demo=True)
    print("wrote", a.out / "report_en.pdf")
    if a.persian:
        try:
            export_pdf(a.out / "report_fa.pdf", sd.PROJECT["fa"], sd.findings("fa"), "fa", assets=sd.ASSETS,
                       demo=True, allow_unvalidated=True)
            print("wrote", a.out / "report_fa.pdf", "- now run the checks in docs/PERSIAN_PDF_VALIDATION.md")
        except ReportRenderingError as exc:
            print("Persian report NOT written:", exc)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
