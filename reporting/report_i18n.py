"""Report strings (English / Persian) and value translations. Unknown values pass through."""

STRINGS = {
    "en": {
        "title": "Security Assessment Report",
        "project": "Project", "target": "Authorized target", "auth_ref": "Authorization reference",
        "generated": "Generated (UTC)", "tool": "Tool",
        "summary": "Summary", "findings": "Findings", "details": "Finding details",
        "scope": "Authorized assets (scope)", "no_findings": "No findings were recorded.",
        "col_no": "#", "col_title": "Title", "col_severity": "Severity", "col_status": "Status",
        "col_remediation": "Remediation", "count": "Count", "total": "Total",
        "url": "URL", "confidence": "Confidence", "evidence": "Evidence", "reference": "Reference",
        "origin": "Origin", "type": "Type", "notes": "Notes",
        "disclaimer": ("Analyst validation is required. A missing security header is an observation, "
                       "not automatically an exploitable vulnerability, and the absence of findings "
                       "is not proof of security."),
        "page": "Page", "of": "of", "none": "-", "truncated": "... (truncated)",
        "demo_banner": ("DEMONSTRATION DATA - sample report. The target, addresses and findings are "
                        "fictional and do not describe a real system."),
        "demo_footer": "DEMO DATA",
        "testdata_warning": ("WARNING: this report references reserved example/documentation names or "
                             "addresses (example.com, 192.0.2.x, ...). Make sure it is not test data "
                             "presented as a real assessment."),
        "cve_unconfirmed": ("Note: {ids} is/are not confirmed for the affected product and version; "
                            "treat as informational until validated by an analyst."),
    },
    "fa": {
        "title": "گزارش ارزیابی امنیت وب‌سایت",
        "project": "پروژه", "target": "هدف مجاز", "auth_ref": "مرجع مجوز کتبی",
        "generated": "زمان تولید گزارش (UTC)", "tool": "ابزار",
        "summary": "خلاصه", "findings": "یافته‌ها", "details": "جزئیات یافته‌ها",
        "scope": "دارایی‌های مجاز (محدوده)", "no_findings": "هیچ یافته‌ای ثبت نشده است.",
        "col_no": "ردیف", "col_title": "عنوان", "col_severity": "شدت", "col_status": "وضعیت",
        "col_remediation": "راهکار", "count": "تعداد", "total": "جمع",
        "url": "نشانی", "confidence": "اطمینان", "evidence": "شواهد", "reference": "مرجع",
        "origin": "مبدأ", "type": "نوع", "notes": "یادداشت",
        "disclaimer": ("اعتبارسنجی توسط کارشناس الزامی است. نبود یک هدر امنیتی صرفاً یک مشاهده است "
                       "و لزوماً به معنای آسیب‌پذیری قابل بهره‌برداری نیست؛ نبود یافته نیز به معنای امن بودن نیست."),
        "page": "صفحه", "of": "از", "none": "-", "truncated": "... (کوتاه‌شده)",
        "demo_banner": ("داده‌ی نمایشی - گزارش نمونه. هدف، نشانی‌ها و یافته‌ها ساختگی‌اند و هیچ سامانه‌ی "
                        "واقعی را توصیف نمی‌کنند."),
        "demo_footer": "داده‌ی نمایشی",
        "testdata_warning": ("هشدار: این گزارش به نام‌ها یا نشانی‌های رزروشده‌ی نمونه/مستندات "
                             "(example.com، 192.0.2.x و ...) اشاره دارد. مطمئن شوید داده‌ی آزمایشی "
                             "به‌عنوان ارزیابی واقعی معرفی نمی‌شود."),
        "cve_unconfirmed": ("توجه: {ids} برای محصول و نسخه‌ی تحت‌تأثیر تأیید نشده است؛ تا زمان اعتبارسنجی "
                            "توسط کارشناس، فقط اطلاعاتی در نظر گرفته شود."),
    },
}

VALUES = {
    "en": {},
    "fa": {
        "Critical": "بحرانی", "High": "بالا", "Medium": "متوسط", "Low": "کم", "Info": "اطلاعاتی",
        "Needs review": "نیازمند بررسی", "Confirmed": "تأیید شده", "False positive": "مثبت کاذب",
        "Resolved": "رفع شده", "Accepted risk": "ریسک پذیرفته‌شده",
        "Web origin": "مبدأ وب", "API origin": "مبدأ API", "Other authorized endpoint": "نقطهٔ پایانی مجاز دیگر",
    },
}

SEVERITY_ORDER = ["Critical", "High", "Medium", "Low", "Info"]
LANGUAGES = tuple(STRINGS)


def strings(language: str) -> dict:
    if language not in STRINGS:
        raise ValueError(f"unsupported report language: {language!r}")
    return STRINGS[language]


def value(language: str, v) -> str:
    v = "" if v is None else str(v)
    return VALUES[language].get(v, v)
