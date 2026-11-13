# Changes in r2 (relative to r1)

1. `core/scope.py` - IPv6 origins
   * `https://[::1]` was normalised to `https://::1` (brackets lost, an invalid origin). Now the
     brackets are kept and the address is canonicalised (`[2001:0DB8:0:0:0:0:0:1]` -> `[2001:db8::1]`),
     so equivalent spellings match exactly and nothing is widened.
   * Host containing ':' must be a valid IPv6 literal; zone ids (`%...`) are rejected.
   * Malformed URLs that make `urlparse` raise (unbalanced `[`) now raise the same `ValueError`.
   * Default ports are still dropped (also for IPv6); invalid ports are rejected.
2. `reporting/exporters.py` - `export_pdf` no longer overwrites
   * Existing destination (file or symlink) -> `FileExistsError`, nothing touched.
   * Unique temp file (`tempfile.mkstemp`) in the destination directory.
   * Final step is an atomic no-overwrite publish (`os.link`; fallback O_EXCL reservation + rename
     where hard links are unsupported). A file created during rendering is never replaced.
   * Temp file is always removed on failure.
   * Behaviour change for the UI: choosing an existing file in the Save dialog now shows the
     error message "Refusing to overwrite existing file" (ui/main_window.py not changed;
     GUI not run).
3. Tests
   * new `tests/test_scope_origin.py` (37), new `tests/test_export_safety.py` (12).
   * `tests/test_report_persian_plumbing.py::test_failed_persian_export_leaves_no_file_and_keeps_old_one`
     adjusted: an existing destination now raises `FileExistsError`; the failing-render case uses a fresh path.
4. Untouched: r1 directory, v0.2, `samples/report_en.pdf` (SHA-256 prefix 2ad3c0903b7770e1, identical to r1).
