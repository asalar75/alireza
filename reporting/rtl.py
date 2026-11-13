"""Text shaping for right-to-left PDF output.

``TextShaper.default()`` wires ``arabic-reshaper`` (contextual letter forms, lam-alef ligatures)
and ``python-bidi`` (visual reordering). Both are imported lazily so that English reports and
the rest of the app work without them. Tests inject fakes through the constructor.

IMPORTANT: the real libraries have not been run in the development sandbox (no network).
The calls below follow their documented public API; ``docs/PERSIAN_PDF_VALIDATION.md`` lists the
checks that must pass on real output before Persian PDF is declared complete.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Optional

ARABIC_SCRIPT = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
# Bidi override/embedding/isolate controls in untrusted data could visually reorder text
# (spoofing). They are removed; ZWNJ (U+200C) and ZWJ (U+200D) are legitimate in Persian and kept.
_STRIP = re.compile("[‪-‮⁦-⁩‎‏؜]")
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def has_arabic_script(text: str) -> bool:
    return bool(ARABIC_SCRIPT.search(text))


def clean_text(text) -> str:
    """Normalise untrusted text: str, NFC, no control/bidi-control chars, tabs -> space."""
    s = "" if text is None else str(text)
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    s = _CONTROL.sub("", _STRIP.sub("", s))
    return unicodedata.normalize("NFC", s)


class TextShaper:
    def __init__(self, reshape: Callable[[str], str], display: Callable[..., str]):
        self._reshape, self._display = reshape, display

    @classmethod
    def default(cls) -> "TextShaper":
        import arabic_reshaper
        try:                                   # python-bidi >= 0.5 exposes it at top level
            from bidi import get_display
        except ImportError:                    # python-bidi 0.4.x
            from bidi.algorithm import get_display
        reshaper = arabic_reshaper.ArabicReshaper()
        return cls(reshaper.reshape, get_display)

    def reshape(self, text: str) -> str:
        return self._reshape(text)

    def display(self, logical_line: str, base_rtl: bool) -> str:
        """Reorder ONE already-wrapped line into visual order (must never see a whole paragraph)."""
        return self._display(logical_line, base_dir="R" if base_rtl else "L")
