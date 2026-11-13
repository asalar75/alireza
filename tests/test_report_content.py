"""Content correctness of reports: finding consistency, no repeated evidence, severity counts,
page numbers, unconfirmed CVEs, DEMO marking. Real PDFs are generated and read back."""
import re
import subprocess
import sys
from pathlib import Path

import pdfplumber
import pytest
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import sample_data as sd  # noqa: E402

from core.database import Database
from core.passive_scan import Response, run_passive_check
from reporting.exporters import export_pdf
from reporting.pdf_report import collapse_repeats, looks_like_test_data

PROJECT = {"name": "Acme web assessment", "target": "https://app.acme-corp.net", "authorized_by": "AUTH-7"}


def pages(path):
    return [p.extract_text() for p in PdfReader(str(path)).pages]


def flat(path):
    return " ".join(" ".join(pages(path)).split())


def finding(i, **kw):
    d = dict(id=i, title=f"Finding {i}", severity="Low", confidence="Medium", status="Needs review",
             url="https://app.acme-corp.net/", evidence=f"Distinct evidence line for finding {i}.",
             remediation=f"Distinct remediation for finding {i}.", reference="ref")
    d.update(kw)
    return d


# ------------------------------------------------------------ 1. title / evidence / remediation agree
@pytest.mark.parametrize("lang", ["en", "fa"])
def test_sample_data_is_internally_consistent(lang):
    assert sd.validate_all(lang) == {}


def test_validator_catches_the_original_sample_defects():
    hsts_with_csp_evidence = dict(title="HSTS header not observed", status="Needs review", reference="",
                                  evidence="HTTP 200; response header 'content-security-policy' was absent.",
                                  remediation="Configure Strict-Transport-Security.")
    p = sd.check_finding_consistency(hsts_with_csp_evidence, "strict-transport-security", "missing")
    assert any("evidence does not mention" in x for x in p) and any("unrelated header" in x for x in p)

    server_but_absent = dict(title="Server response header disclosed", status="Needs review", reference="",
                             evidence="HTTP 200 header absent", remediation="Reduce version disclosure.")
    p = sd.check_finding_consistency(server_but_absent, "server", "disclosed")
    assert any("must contain its value" in x for x in p) and any("absent" in x for x in p)

    repeated = dict(title="x", status="Needs review", reference="", remediation="y",
                    evidence="The same sentence here. " * 10)
    assert any("repeated" in x for x in sd.check_finding_consistency(repeated, None, "other"))

    cve = dict(title="x", status="Needs review", reference="", evidence="e",
               remediation="See CVE-2025-12345 advisory.")
    assert any("CVE" in x for x in sd.check_finding_consistency(cve, None, "other"))


def test_real_scanner_output_passes_the_same_consistency_rules():
    mapping = {"HSTS header not observed": ("strict-transport-security", "missing"),
               "Content-Security-Policy header not observed": ("content-security-policy", "missing"),
               "X-Content-Type-Options header not observed": ("x-content-type-options", "missing"),
               "Referrer-Policy header not observed": ("referrer-policy", "missing"),
               "Permissions-Policy header not observed": ("permissions-policy", "missing"),
               "Server response header disclosed": ("server", "disclosed")}
    out = run_passive_check("https://example.com", ["https://example.com"],
                            fetch=lambda o: Response(200, {"Server": "nginx/1.18.0"}, False))
    assert {o["title"] for o in out} == set(mapping)
    for o in out:
        header, kind = mapping[o["title"]]
        assert sd.check_finding_consistency(o, header, kind) == [], o["title"]


def test_each_finding_in_the_rendered_sample_shows_matching_title_evidence_remediation(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, sd.PROJECT["en"], sd.findings("en"), "en", assets=sd.ASSETS, demo=True)
    t = flat(out)
    assert "HSTS header not observed" in t and "response header 'strict-transport-security' was absent" in t
    assert "Enable Strict-Transport-Security (HSTS)" in t
    assert "Content-Security-Policy header not observed" in t and "response header 'content-security-policy' was absent" in t
    assert "Server response header: Server: nginx/1.18.0" in t
    # the Server finding must not claim absence anywhere near its own text
    sec = t[t.index("3. Server response header disclosed"):t.index("4. Verbose error page")]
    assert "absent" not in sec


# ------------------------------------------------------------ 2. no unintended repeated evidence
def test_collapse_repeats_unit():
    assert collapse_repeats("A b. A b. A b. A b. Tail.") == "A b. [×4] Tail."
    assert collapse_repeats("x\nx\nx\ny") == "x [×3]\ny"
    assert collapse_repeats("a. a. b.") == "a. a. b."            # only runs of >= 3
    assert collapse_repeats("one. two. three.") == "one. two. three."


def test_repeated_evidence_is_shown_once_with_a_count(tmp_path):
    out = tmp_path / "r.pdf"
    ev = "The response lacked the header on every probe. " * 25
    export_pdf(out, PROJECT, [finding(1, evidence=ev)], "en")
    t = flat(out)
    assert t.count("The response lacked the header on every probe.") == 1 and "[×25]" in t


def test_long_distinct_evidence_paginates_with_no_duplicates(tmp_path):
    out = tmp_path / "r.pdf"
    lines = [f"line-{i:03d} unique trace entry {i * 7}" for i in range(1, 121)]
    export_pdf(out, PROJECT, [finding(1, evidence="\n".join(lines))], "en")
    t = " ".join(pages(out))
    got = re.findall(r"line-\d{3}", t)
    assert got == [f"line-{i:03d}" for i in range(1, 121)]          # each once, in order
    assert len(pages(out)) >= 2


def test_demo_sample_has_no_repeated_evidence_and_continues_across_pages(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, sd.PROJECT["en"], sd.findings("en"), "en", assets=sd.ASSETS, demo=True)
    t = " ".join(pages(out))
    frames = re.findall(r"#(\d+) /srv/app/vendor", t)
    assert frames == [str(i) for i in range(30)]                    # 0..29 once each, in order


# ------------------------------------------------------------ 3. severity counts / totals
def _summary(path):
    """The Severity/Count summary table of page 1 as {label: count}."""
    for tb in pdfplumber.open(path).pages[0].extract_tables():
        if tb and tb[0] == ["Severity", "Count"]:
            return {r[0]: r[1] for r in tb}
    raise AssertionError("summary table not found")


def test_severity_counts_and_total_match_the_findings(tmp_path):
    out = tmp_path / "r.pdf"
    sev = ["Critical", "High", "High", "Medium", "Medium", "Medium", "Low", "Low", "Info", "Info", "Info", "Info"]
    fs = [finding(i, severity=s) for i, s in enumerate(sev, 1)]
    export_pdf(out, PROJECT, fs, "en")
    rows = _summary(out)
    assert rows == {"Severity": "Count", "Critical": "1", "High": "2", "Medium": "3", "Low": "2",
                    "Info": "4", "Total": "12"}
    assert sum(int(rows[k]) for k in ("Critical", "High", "Medium", "Low", "Info")) == int(rows["Total"]) == len(fs)


def test_findings_table_row_count_equals_number_of_findings(tmp_path):
    out = tmp_path / "r.pdf"
    fs = [finding(i) for i in range(1, 38)]
    export_pdf(out, PROJECT, fs, "en")
    body = [r for pg in pdfplumber.open(out).pages for tb in pg.extract_tables()
            if tb and tb[0][:2] == ["#", "Title"] for r in tb[1:]]
    assert [r[0] for r in body] == [str(i) for i in range(1, 38)]


def test_unknown_severity_is_counted_not_dropped(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(1, severity="Weird"), finding(2)], "en")
    rows = _summary(out)
    assert rows["Weird"] == "1" and rows["Total"] == "2"


# ------------------------------------------------------------ 4. page numbers (multi-finding, long evidence)
def test_page_numbers_multi_finding_long_evidence(tmp_path):
    out = tmp_path / "r.pdf"
    fs = [finding(i, evidence="\n".join(f"f{i}-row{j:03d} detail {j}" for j in range(1, 60)))
          for i in range(1, 9)]
    export_pdf(out, PROJECT, fs, "en")
    pg = pages(out)
    n = len(pg)
    assert n >= 5
    for i, text in enumerate(pg, 1):
        assert f"Page {i} of {n}" in text
    allrows = re.findall(r"f(\d)-row(\d{3})", " ".join(pg))
    assert len(allrows) == len(set(allrows)) == 8 * 59                # none lost, none duplicated


# ------------------------------------------------------------ 5. unconfirmed CVEs
def test_unconfirmed_cve_is_flagged_not_presented_as_definitive(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(1, reference="CVE-2025-12345", status="Needs review")], "en")
    t = flat(out)
    assert "CVE-2025-12345" in t and "is/are not confirmed for the affected product and version" in t


def test_confirmed_cve_has_no_warning(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(1, reference="CVE-2025-12345", status="Confirmed")], "en")
    assert "not confirmed for the affected product" not in flat(out)


def test_finding_without_cve_has_no_cve_note(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(1)], "en")
    assert "CVE" not in flat(out)


def test_sample_report_contains_no_cve_at_all(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, sd.PROJECT["en"], sd.findings("en"), "en", assets=sd.ASSETS, demo=True)
    assert "CVE-" not in flat(out)


# ------------------------------------------------------------ 6. demo / test data marking
def test_demo_report_is_marked_on_first_page_and_every_footer(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, sd.PROJECT["en"], sd.findings("en"), "en", assets=sd.ASSETS, demo=True)
    pg = pages(out)
    assert "DEMONSTRATION DATA - sample report" in " ".join(pg[0].split())
    assert all("DEMO DATA" in p for p in pg)
    assert "DEMO - Example Corp" in pg[0]


def test_real_report_without_test_data_has_no_demo_marking(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, PROJECT, [finding(1)], "en")
    t = flat(out)
    assert "DEMO" not in t and "WARNING" not in t


def test_test_data_without_demo_flag_gets_a_warning_instead_of_passing_as_real(tmp_path):
    out = tmp_path / "r.pdf"
    export_pdf(out, {"name": "Real?", "target": "https://example.com", "authorized_by": "A"},
               [finding(1, evidence="seen at 192.0.2.10")], "en")
    t = flat(out)
    assert "WARNING: this report references reserved example/documentation" in t and "DEMONSTRATION" not in t


def test_looks_like_test_data_rules():
    assert looks_like_test_data({"target": "https://www.example.org", "name": ""}, [])
    assert looks_like_test_data({"target": "https://x.io", "name": ""}, [{"evidence": "ip 203.0.113.7"}])
    assert not looks_like_test_data({"target": "https://acme.io", "name": "notexample.company"}, [])
    assert not looks_like_test_data({"target": "https://x.io", "name": ""}, [{"evidence": "10.0.0.5 and 192.0.20.1"}])


def test_demo_data_in_a_real_database_row_is_still_flagged(tmp_path):
    db = Database(tmp_path / "a.sqlite3")
    pid = db.create_project("P", "https://example.com", "A")
    db.add_finding(pid, "t", "Low", "Low", "https://example.com", "Needs review", "e", "r")
    out = tmp_path / "r.pdf"
    export_pdf(out, db.projects()[0], db.findings(pid), "en", assets=db.assets(pid))
    assert "WARNING: this report references reserved" in flat(out)


# ------------------------------------------------------------ 7. generator script end to end
def test_generator_script_produces_marked_valid_english_pdf_and_refuses_persian(tmp_path):
    r = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "make_validation_reports.py"),
                        "--out", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "report_en.pdf").read_bytes().startswith(b"%PDF")
    r = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "make_validation_reports.py"),
                        "--out", str(tmp_path / "p"), "--persian"], capture_output=True, text=True)
    assert r.returncode == 2 and "Persian report NOT written" in r.stdout
    assert not (tmp_path / "p" / "report_fa.pdf").exists()
