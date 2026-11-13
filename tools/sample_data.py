"""Fictional DEMO data for the sample reports + a consistency validator.

Everything here is invented: example.com and 192.0.2.10 are reserved documentation values
(RFC 2606 / RFC 5737), the Server value is a made-up banner. Reports built from this data are
generated with demo=True so they carry a visible DEMO marking.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reporting.pdf_report import CVE_RE, collapse_repeats  # noqa: E402

PROJECT = {"en": {"name": "DEMO - Example Corp web assessment", "target": "https://example.com",
                  "authorized_by": "DEMO-AUTH-0000 (fictional)"},
           "fa": {"name": "نمونه - ارزیابی وب‌سایت شرکت نمونه (Example Corp)", "target": "https://example.com",
                  "authorized_by": "DEMO-AUTH-0000 (ساختگی)"}}
ASSETS = [{"origin": "https://example.com", "asset_type": "Web origin", "notes": "demo target"}]

HEADER_ALIASES = {
    "strict-transport-security": ("strict-transport-security", "hsts"),
    "content-security-policy": ("content-security-policy", "csp"),
    "x-content-type-options": ("x-content-type-options",),
    "referrer-policy": ("referrer-policy",),
    "permissions-policy": ("permissions-policy",),
    "server": ("server",),
}
ABSENT = {"en": ("absent", "not observed"), "fa": ("مشاهده نشد",)}
DISCLOSURE_WORDS = ("disclos", "version", "افشا", "نسخه")


def _trace(n=30):
    return "\n".join(f"#{i} /srv/app/vendor/framework/Component{i:02d}.php({100 + 7 * i}): "
                     f"App\\Handler{i:02d}->process()" for i in range(n))


def build(lang):
    fa = lang == "fa"
    items = [
        dict(header="strict-transport-security", kind="missing",
             finding=dict(id=1, severity="Low", confidence="Medium", status="Needs review",
                          url="https://example.com/",
                          title="نبود هدر HSTS" if fa else "HSTS header not observed",
                          evidence=("HTTP 200 از https://example.com؛ هدر پاسخ strict-transport-security مشاهده نشد."
                                    if fa else "HTTP 200 from https://example.com; response header 'strict-transport-security' was absent."),
                          remediation=("پس از اطمینان از پشتیبانی همه‌ی زیردامنه‌ها از HTTPS، هدر Strict-Transport-Security (HSTS) را با max-age مناسب فعال کنید."
                                       if fa else "Enable Strict-Transport-Security (HSTS) with a suitable max-age after confirming all subdomains support HTTPS."),
                          reference="OWASP Secure Headers Project")),
        dict(header="content-security-policy", kind="missing",
             finding=dict(id=2, severity="Medium", confidence="Medium", status="Needs review",
                          url="https://example.com/",
                          title="نبود هدر Content-Security-Policy" if fa else "Content-Security-Policy header not observed",
                          evidence=("HTTP 200 از https://example.com؛ هدر پاسخ content-security-policy مشاهده نشد."
                                    if fa else "HTTP 200 from https://example.com; response header 'content-security-policy' was absent."),
                          remediation=("یک سیاست Content-Security-Policy متناسب با برنامه تعریف کنید و ابتدا در حالت report-only بیازمایید."
                                       if fa else "Define a Content-Security-Policy suited to the application and trial it in report-only mode first."),
                          reference="OWASP Secure Headers Project")),
        dict(header="server", kind="disclosed",
             finding=dict(id=3, severity="Info", confidence="High", status="Needs review",
                          url="https://example.com/",
                          title="افشای هدر Server" if fa else "Server response header disclosed",
                          evidence=("هدر پاسخ Server: nginx/1.18.0 (مقدار نمایشی ساختگی)"
                                    if fa else "Server response header: Server: nginx/1.18.0 (fictional demo value)"),
                          remediation=("افشای نام و نسخه‌ی محصول را کاهش دهید."
                                       if fa else "Reduce unnecessary product/version disclosure in the Server header."),
                          reference="Information disclosure review")),
        dict(header=None, kind="other",
             finding=dict(id=4, severity="Medium", confidence="Medium", status="Needs review",
                          url="https://example.com/account/orders?page=abc",
                          title=("افشای جزئیات فریم‌ورک در صفحه‌ی خطا" if fa
                                 else "Verbose error page discloses framework details"),
                          evidence=("درخواست: GET https://example.com/account/orders?page=abc\n"
                                    "پاسخ: HTTP 500 با صفحه‌ی اشکال‌زدایی فریم‌ورک.\n" if fa else
                                    "Request: GET https://example.com/account/orders?page=abc\n"
                                    "Response: HTTP 500 with a framework debug page.\n")
                          + "Stack trace excerpt (fictional demo data):\n" + _trace(),
                          remediation=("نمایش خطای تفصیلی را در محیط عملیاتی غیرفعال کنید، یک صفحه‌ی خطای عمومی نشان دهید و جزئیات را فقط در لاگ سرور ثبت کنید."
                                       if fa else "Disable verbose/debug error output in production, return a generic error page and log details server-side only."),
                          reference="OWASP Error Handling Cheat Sheet")),
    ]
    return items


def check_finding_consistency(finding, header, kind, lang="en"):
    """Return a list of human-readable problems (empty list == consistent)."""
    problems = []
    t, ev, rem = finding["title"], finding["evidence"], finding["remediation"]
    lower = lambda x: x.lower()
    if not t.strip() or not ev.strip() or not rem.strip():
        problems.append("title, evidence and remediation must all be non-empty")
    others = [k for k in HEADER_ALIASES if k != header]
    if header:
        aliases = HEADER_ALIASES[header]
        if not any(a in lower(t) for a in aliases):
            problems.append(f"title does not mention {header}")
        if kind == "missing":
            if header not in lower(ev):
                problems.append(f"evidence does not mention the header {header}")
            if not any(a in ev for a in ABSENT[lang]):
                problems.append("evidence of a missing header must say it was absent/not observed")
            if not any(a in lower(rem) for a in aliases):
                problems.append(f"remediation does not mention {header}")
        elif kind == "disclosed":
            if not re.search(r"server[^:\n]*:\s*\S+", ev, re.I):
                problems.append("evidence of a disclosed Server header must contain its value")
            if any(a in ev for a in ABSENT[lang]):
                problems.append("evidence says the header was absent but the title says it is disclosed")
            if not any(w in lower(rem) for w in DISCLOSURE_WORDS):
                problems.append("remediation does not address disclosure")
    for k in others:
        if k == "server":
            continue                       # the word 'server' appears in ordinary prose
        for name, text in (("evidence", ev), ("remediation", rem)):
            if k in lower(text) and k not in lower(t):
                problems.append(f"{name} mentions an unrelated header ({k})")
    if finding.get("status") != "Confirmed":
        for name in ("title", "evidence", "remediation", "reference"):
            if CVE_RE.search(str(finding.get(name, ""))):
                problems.append(f"unconfirmed finding cites a CVE in {name}")
    if collapse_repeats(ev) != ev:
        problems.append("evidence contains repeated identical lines/sentences")
    return problems


def validate_all(lang):
    out = {}
    for it in build(lang):
        probs = check_finding_consistency(it["finding"], it["header"], it["kind"], lang)
        if probs:
            out[it["finding"]["id"]] = probs
    return out


def findings(lang):
    return [it["finding"] for it in build(lang)]
