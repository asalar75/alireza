# Changes in r3 (relative to r2)

`reporting/exporters.py` - PDF publish now fails closed
* r2 fallback (reserve with O_EXCL, close, `os.replace`) had a race: another process could replace
  the reserved name before our `os.replace`, which would then overwrite its file. Removed.
* `_publish_no_overwrite()` now uses only `os.link(tmp, dest)` (atomic, fails with FileExistsError
  if the name exists). If hard links are unsupported or fail for any other reason it raises the new
  `ExportPublishError` (subclass of `ReportRenderingError`, so the UI shows it) with an actionable
  message. There is NO overwrite-capable fallback (no os.replace/os.rename/shutil.move).
* Destination is never created or modified on failure; the unique temp file is always removed.

## Behaviour on file systems without hard links
Export fails with: "Cannot publish <path> safely: the file system or folder does not allow the
atomic no-overwrite step (hard link) ... Nothing was written to the destination and any existing
file is untouched. Export to a folder on a local drive that supports hard links ...".
This is intentional: the no-overwrite guarantee is not weakened. Windows/NTFS behaviour has NOT been
tested (no Windows available); network shares, FAT/exFAT and some cloud-synced folders may refuse
hard links and would therefore refuse the export.

## Tests
`tests/test_export_safety.py`: 12 -> 22. Replaced the two r2 fallback tests with fail-closed tests;
added: link unsupported (no destination, no temp), several errno values, other-process creation
during render (real subprocess), regression that os.replace/os.rename/shutil.move/Path.replace/
Path.rename are never called in any outcome, a source-level check of the publish function, and
concurrent exports to different destinations. Mutation check: re-inserting an `os.replace` fallback
makes 9 tests fail.

Untouched: Scope validation, audit log, database, r1, r2, v0.2, samples/report_en.pdf.
