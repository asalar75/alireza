# Offline dependencies - what must be obtained outside the sandbox

Why: the development sandbox has no network (GitHub and PyPI are blocked), so fonts and wheels
cannot be downloaded there. Everything below is downloaded on a machine with internet access
and copied in. **Nothing in this file has been downloaded or hash-checked yet.**

## Target platform
| Item | Value |
|---|---|
| Python | CPython **3.12** (64-bit). 3.11 / 3.13 / 3.14 wheels are NOT interchangeable for the compiled packages |
| Windows | 10 or 11, **x64 only** (`win_amd64`). Windows ARM64 and 32-bit are unsupported/unverified (PySide6 is the limiting package) |
| Wheel tags accepted | `py3-none-any`, `py2.py3-none-any`, `cp312-cp312-win_amd64`, `cp39-abi3-win_amd64` (abi3 up to cp312) |
| Extra PC prerequisite | Microsoft Visual C++ Redistributable 2015-2022 **x64** (needed by Qt/PySide6) |

## How to read the "Status" column
* **verified version in sandbox** - that exact version is installed and was used to run the 188 tests on Linux. The Windows wheel *file name* is the expected pattern, not a downloaded file.
* **CANDIDATE (unverified)** - my recommended pin, written from memory without network access. It may not exist or may not be the best choice. `pip download` fails loudly if a version does not exist; if so, pick the nearest version and update `tools/offline_manifest.json`. Do not trust a candidate until its hash is recorded.

## A. Persian font (put in `assets/fonts/`)
| Id | File (name / glob) | Version | Goes to | License | Status |
|---|---|---|---|---|---|
| `vazirmatn-regular` | `Vazirmatn-Regular.ttf` | release tag to record (candidate v33.003) | assets/fonts/ | OFL-1.1 | CANDIDATE (unverified) |
| `vazirmatn-bold` | `Vazirmatn-Bold.ttf` | same release as Regular | assets/fonts/ | OFL-1.1 | CANDIDATE (unverified) |
| `vazirmatn-ofl` | `OFL.txt` | same release | assets/fonts/ | OFL-1.1 | CANDIDATE (unverified) |

Requirements: take the files unmodified from the official repository
`https://github.com/rastikerdar/vazirmatn` (TTF files in `fonts/ttf`, `OFL.txt` in the repo root) at
one release tag; record that tag. `OFL.txt` must contain the copyright line and must be copied
unchanged and ship with the font. `AUTHORS.txt` is optional. See `docs/DEPENDENCIES_AND_LICENSES.md`.

## B. Persian shaping libraries (pure Python - usable on Linux and Windows)
| Id | File (name / glob) | Version | Goes to | License | Status |
|---|---|---|---|---|---|
| `arabic-reshaper` | `arabic_reshaper-3.0.0-py3-none-any.whl` | 3.0.0 | wheelhouse/ | MIT (unverified) | CANDIDATE (unverified) |
| `python-bidi` | `python_bidi-0.4.2-*.whl` | 0.4.2 | wheelhouse/ | LGPL-3.0 (unverified) | CANDIDATE (unverified) |
| `six` | `six-1.17.0-py2.py3-none-any.whl` | 1.17.0 | wheelhouse/ | MIT (unverified) | CANDIDATE (unverified) |

`python-bidi` 0.4.2 is old (2019) but pure Python, so it has no architecture/ABI risk and the code
(`reporting/rtl.py`) calls `bidi.algorithm.get_display`. Versions 0.5+ are Rust wheels
(`win_amd64`); the code also supports them via `from bidi import get_display`, but that path is
unverified. Choose one and record the decision here.

## C. Other runtime dependencies (Windows application)
| Id | File (name / glob) | Version | Goes to | License | Status |
|---|---|---|---|---|---|
| `reportlab` | `reportlab-5.0.1-*.whl` | 5.0.1 | wheelhouse/ | BSD-3 (per package metadata) | verified version in sandbox |
| `pillow` | `pillow-12.3.0-cp312-cp312-win_amd64.whl` | 12.3.0 | wheelhouse/ | HPND (unverified) | verified version in sandbox |
| `charset-normalizer` | `charset_normalizer-3.5.1-*.whl` | 3.5.1 | wheelhouse/ | MIT (unverified) | verified version in sandbox |
| `pyside6` | `PySide6-6.8.3-*.whl` | 6.8.3 | wheelhouse/ | LGPL-3.0 / commercial (unverified) | CANDIDATE (unverified) |
| `pyside6-essentials` | `PySide6_Essentials-6.8.3-*.whl` | 6.8.3 | wheelhouse/ | LGPL-3.0 / commercial (unverified) | CANDIDATE (unverified) |
| `pyside6-addons` | `PySide6_Addons-6.8.3-*.whl` | 6.8.3 | wheelhouse/ | LGPL-3.0 / commercial (unverified) | CANDIDATE (unverified) |
| `shiboken6` | `shiboken6-6.8.3-*.whl` | 6.8.3 | wheelhouse/ | LGPL-3.0 / commercial (unverified) | CANDIDATE (unverified) |
| `httpx` | `httpx-0.28.1-py3-none-any.whl` | 0.28.1 | wheelhouse/ | BSD-3 (unverified) | CANDIDATE (unverified) |

`httpx` needs further wheels (httpcore, h11, anyio, idna, sniffio, certifi, ...). They are not listed
because I cannot resolve them offline; `pip download` produces the full set and each file must be
added to the manifest with its hash (this is part of the lock-file milestone).

## D. Development / test only
| Id | File (name / glob) | Version | Goes to | License | Status |
|---|---|---|---|---|---|
| `pytest` | `pytest-9.1.1-py3-none-any.whl` | 9.1.1 | wheelhouse-dev/ | MIT | verified version in sandbox |
| `iniconfig` | `iniconfig-2.3.0-py3-none-any.whl` | 2.3.0 | wheelhouse-dev/ | MIT (unverified) | verified version in sandbox |
| `packaging` | `packaging-26.3-py3-none-any.whl` | 26.3 | wheelhouse-dev/ | Apache-2.0 / BSD (unverified) | verified version in sandbox |
| `pluggy` | `pluggy-1.6.0-py3-none-any.whl` | 1.6.0 | wheelhouse-dev/ | MIT (unverified) | verified version in sandbox |
| `pygments` | `pygments-2.21.0-py3-none-any.whl` | 2.21.0 | wheelhouse-dev/ | BSD-2 (unverified) | verified version in sandbox |
| `colorama` | `colorama-*-py2.py3-none-any.whl` | to resolve | wheelhouse-dev/ | BSD-3 (unverified) | CANDIDATE (unverified) |
| `pypdf` | `pypdf-6.17.0-py3-none-any.whl` | 6.17.0 | wheelhouse-dev/ | BSD-3-Clause | verified version in sandbox |
| `pdfplumber` | `pdfplumber-0.11.10-py3-none-any.whl` | 0.11.10 | wheelhouse-dev/ | MIT (unverified) | verified version in sandbox |
| `pdfminer-six` | `pdfminer_six-20260107-py3-none-any.whl` | 20260107 | wheelhouse-dev/ | MIT (unverified) | verified version in sandbox |
| `pypdfium2` | `pypdfium2-5.13.0-*win_amd64.whl` | 5.13.0 | wheelhouse-dev/ | Apache-2.0/BSD-3 (unverified) | verified version in sandbox |
| `cryptography` | `cryptography-50.0.1-*win_amd64.whl` | 50.0.1 | wheelhouse-dev/ | Apache-2.0 / BSD (unverified) | verified version in sandbox |
| `cffi` | `cffi-2.1.1-cp312-cp312-win_amd64.whl` | 2.1.1 | wheelhouse-dev/ | MIT (unverified) | verified version in sandbox |
| `pycparser` | `pycparser-3.0-py3-none-any.whl` | 3.0 | wheelhouse-dev/ | BSD-3 (unverified) | verified version in sandbox |

`colorama` is a Windows-only pytest dependency; resolve its version with `pip download`.

## E. Procedure (on a machine with internet)
```powershell
py -3.12 -m pip download --only-binary=:all: --platform win_amd64 --python-version 3.12 `
   --implementation cp --abi cp312 -r requirements.txt -d bundle\wheelhouse
py -3.12 -m pip download --only-binary=:all: --platform win_amd64 --python-version 3.12 `
   --implementation cp --abi cp312 -r requirements-dev.txt -d bundle\wheelhouse-dev
# put Vazirmatn-Regular.ttf, Vazirmatn-Bold.ttf, OFL.txt in bundle\fonts
python tools\verify_offline_bundle.py --bundle bundle\fonts
python tools\verify_offline_bundle.py --bundle bundle\wheelhouse
```
Review the output, then run again with `--record` to store SHA-256 values in
`tools/offline_manifest.json`. Offline installation on the target PC:
```powershell
py -3.12 -m pip install --no-index --find-links bundle\wheelhouse -r requirements.txt
```
`verify_offline_bundle.py` rejects wheels with the wrong Python/platform tag and detects changed
files; it is standard library only and never executes anything from the bundle.

## F. Exact hand-over list
**Priority 1 - enough to finish and validate the Persian PDF here (Linux sandbox):**
1. `Vazirmatn-Regular.ttf`, `Vazirmatn-Bold.ttf`, `OFL.txt` (same release; tell me the tag)
2. `arabic_reshaper-3.0.0-py3-none-any.whl`
3. `python_bidi-0.4.2-py2.py3-none-any.whl` (or the 0.5+/0.6 wheel for Linux x86-64 *and* tell me which, if you prefer the Rust version)
4. `six-1.17.0-py2.py3-none-any.whl`

Upload them in the chat (or attach one zip). I will place them in `assets/fonts/` and a local wheelhouse, install offline and run the validation.

**Priority 2 - Windows build, lock file and security review (next stage, not needed for the PDF):**
everything in sections C and D (full resolved set incl. `httpx` dependencies), plus the output of
`pip download` as a `requirements.lock` with hashes, and `pip-audit` results.
