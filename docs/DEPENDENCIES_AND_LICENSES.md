# Dependencies and font license (milestone 2 - partially complete)

## Vazirmatn (Persian font) - SIL Open Font License 1.1
Source checked: official repository https://github.com/rastikerdar/vazirmatn - its README states the
font is licensed under the **SIL Open Font License, Version 1.1**; `OFL.txt` is at the repository
root; TTF files are in `fonts/ttf`. (Checked by reading the repository page; the full license text
and the copyright line were NOT copied because the sandbox cannot download files.)

OFL 1.1 conditions relevant to shipping the font inside AegisSec (summary, not legal advice;
the authoritative text is OFL.txt): the font may be bundled and redistributed with software;
it may not be sold on its own; the copyright notice and the license text must accompany every
copy; modified versions may not use a Reserved Font Name and must stay under OFL. We ship the
font unmodified, together with `assets/fonts/OFL.txt`.

TODO before release: add the font files and the unmodified OFL.txt (with its copyright line),
record file hashes here, and have the license reviewed.

## Python packages for Persian PDF
| Package | Purpose | Status |
|---|---|---|
| reportlab | PDF generation | installed (5.0.1 in dev sandbox) |
| arabic-reshaper | contextual letter shaping | NOT installed / not obtainable in sandbox |
| python-bidi | bidirectional reordering | NOT installed / not obtainable in sandbox |

Licenses/versions of these packages are not verified yet (to be recorded with the lock file).
