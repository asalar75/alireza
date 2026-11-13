"""Preflight for Persian PDF output: font file + shaping libraries.

Persian needs (1) a font with Persian glyphs and (2) contextual shaping and bidi reordering
(``arabic-reshaper`` + ``python-bidi``). If anything is missing we fail BEFORE any PDF is
written, with a message the analyst can act on, instead of producing a PDF full of empty boxes.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_REGULAR = "Vazirmatn-Regular.ttf"
FONT_BOLD = "Vazirmatn-Bold.ttf"
LICENSE_FILE = "OFL.txt"
REQUIRED_MODULES = {"arabic_reshaper": "arabic-reshaper", "bidi": "python-bidi"}


class ReportRenderingError(Exception):
    """The report cannot be rendered faithfully; no output file was created."""


def missing_persian_requirements(font_dir: Path = FONT_DIR) -> list[str]:
    problems = []
    for fname in (FONT_REGULAR, FONT_BOLD):
        if not (Path(font_dir) / fname).is_file():
            problems.append(f"font file missing: assets/fonts/{fname}")
    if not (Path(font_dir) / LICENSE_FILE).is_file():
        problems.append(f"font license missing: assets/fonts/{LICENSE_FILE} (must ship with the font)")
    for mod, pkg in REQUIRED_MODULES.items():
        if importlib.util.find_spec(mod) is None:
            problems.append(f"Python package not installed: {pkg}")
    return problems


def require_persian_support(font_dir: Path = FONT_DIR) -> None:
    problems = missing_persian_requirements(font_dir)
    if problems:
        raise ReportRenderingError(
            "Persian PDF cannot be generated: " + "; ".join(problems) +
            ". Install the requirements (see docs/DEPENDENCIES_AND_LICENSES.md) or export in English.")
