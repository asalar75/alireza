import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from reportlab.platypus import SimpleDocTemplate
from .rtl_support import require_persian_support, ReportRenderingError, FONT_DIR
from .pdf_report import make_context, render_pdf

# Persian PDF stays refused until real output has passed the checks in
# docs/PERSIAN_PDF_VALIDATION.md (shaping, direction, table, pagination). Flip only then.
PERSIAN_PDF_VALIDATED = False


def export_json(path, project, findings, assets):
    data = {"product":"AegisSec Enterprise","version":"0.3",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "project":dict(project),"assets":[dict(x) for x in assets],
      "findings":[dict(x) for x in findings],
      "disclaimer":"Observations require analyst validation; no findings is not proof of security."}
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")


def export_pdf(path, project, findings, language="en", assets=None, *, allow_unvalidated=False,
               font_dir=None, shaper=None, generated_at=None, demo=False):
    """Write a PDF report atomically (unique temp file, then an atomic no-overwrite publish): a
    failure never leaves a broken or partial PDF, and an existing file is never replaced
    (FileExistsError).

    language "en": always available.
    language "fa": needs Vazirmatn + arabic-reshaper + python-bidi (pre-flight, below) and is
    refused until PERSIAN_PDF_VALIDATED is True (``allow_unvalidated=True`` is for the
    validation run only).
    """
    path = Path(path)
    if language == "fa":
        if font_dir is None:
            require_persian_support()
        else:
            require_persian_support(Path(font_dir))
        if not (PERSIAN_PDF_VALIDATED or allow_unvalidated):
            raise ReportRenderingError(
                "Persian PDF output has not passed real-output validation yet "
                "(docs/PERSIAN_PDF_VALIDATION.md); refusing to produce it. Export in English.")
    ctx = make_context(language, font_dir=Path(font_dir) if font_dir else FONT_DIR, shaper=shaper, demo=demo)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    # Unique temp file in the destination directory (same filesystem, so the final step is
    # atomic) - two concurrent exports can never share a temp name.
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        render_pdf(tmp, ctx, project, findings, assets or (), generated_at, doc_class=SimpleDocTemplate)
        _publish_no_overwrite(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _publish_no_overwrite(tmp: Path, dest: Path) -> None:
    """Make ``tmp`` appear as ``dest`` atomically, failing (FileExistsError) if dest exists.

    A hard link is created atomically and fails if the name is taken, so a file that appears
    between our check and this step is never replaced. If the filesystem has no hard links,
    fall back to reserving the name with O_EXCL and then renaming over our own placeholder.
    """
    try:
        os.link(tmp, dest)
        return
    except FileExistsError:
        raise
    except OSError:
        pass
    fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY)  # FileExistsError if taken
    os.close(fd)
    try:
        os.replace(tmp, dest)
    except BaseException:
        try:
            dest.unlink()
        except FileNotFoundError:
            pass
        raise
