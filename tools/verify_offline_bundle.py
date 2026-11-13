#!/usr/bin/env python3
"""Verify a folder of offline files (wheels, font, license) against tools/offline_manifest.json.

    python tools/verify_offline_bundle.py --bundle D:\\bundle            # check
    python tools/verify_offline_bundle.py --bundle D:\\bundle --record   # store SHA-256 of files
                                                                        # that have none yet

Checks per entry: exactly one file matches the glob; for wheels the filename tags are compatible
with CPython 3.12 on Windows x64 (cp312 / abi3<=cp312 / py3 ; win_amd64 / any); the SHA-256 equals
the recorded one (when recorded). Standard library only; never imports or executes bundle files.
Exit code 0 only if every required entry is OK.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from pathlib import Path

MANIFEST = Path(__file__).with_name("offline_manifest.json")
PY_MINOR = 12                                   # target: CPython 3.12
OK_PLATFORMS = {"any", "win_amd64"}              # Windows 10/11 x64 only (ARM64/32-bit unsupported)
WHEEL_RE = re.compile(r"^(?P<name>.+?)-(?P<ver>[^-]+)(?:-(?P<build>\d[^-]*))?-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wheel_problem(filename: str) -> str | None:
    """None if the wheel can be installed on CPython 3.12 / Windows x64, else the reason."""
    m = WHEEL_RE.match(filename)
    if not m:
        return "not a valid wheel filename"
    plats = set(m["plat"].split("."))
    if not plats & OK_PLATFORMS:
        return f"platform tag {m['plat']!r} is not win_amd64/any"
    for py in m["py"].split("."):
        for abi in m["abi"].split("."):
            if py in ("py3", "py2.py3") or py == "py3" or re.fullmatch(r"py3\d*", py) and (py == "py3" or int(py[3:] or 0) <= PY_MINOR):
                if abi in ("none", "abi3") or abi == f"cp3{PY_MINOR}":
                    return None
            mm = re.fullmatch(r"cp3(\d+)", py)
            if mm:
                minor = int(mm[1])
                if abi == "abi3" and minor <= PY_MINOR:
                    return None
                if abi == f"cp3{PY_MINOR}" and minor == PY_MINOR:
                    return None
    return f"python/abi tags {m['py']}-{m['abi']} are not compatible with CPython 3.{PY_MINOR}"


def check(bundle: Path, manifest: dict, record: bool = False) -> tuple[list[dict], bool]:
    files = {p.name: p for p in bundle.iterdir() if p.is_file()} if bundle.is_dir() else {}
    results, ok_all = [], True
    claimed: set[str] = set()
    for e in manifest["entries"]:
        matches = sorted(n for n in files if fnmatch.fnmatch(n, e["glob"]))
        r = {"id": e["id"], "required": e.get("required", True), "status": "OK", "detail": ""}
        if len(matches) != 1:
            r["status"] = "MISSING" if not matches else "AMBIGUOUS"
            r["detail"] = f"{len(matches)} file(s) match {e['glob']}"
        else:
            name = matches[0]
            claimed.add(name)
            r["file"] = name
            problem = wheel_problem(name) if name.endswith(".whl") else None
            digest = sha256(files[name])
            r["sha256"] = digest
            if problem:
                r["status"], r["detail"] = "INCOMPATIBLE", problem
            elif e.get("sha256") and e["sha256"] != digest:
                r["status"], r["detail"] = "HASH_MISMATCH", f"expected {e['sha256']}"
            elif not e.get("sha256"):
                if record:
                    e["sha256"] = digest
                    r["detail"] = "hash recorded"
                else:
                    r["status"], r["detail"] = "UNRECORDED", "no SHA-256 recorded yet (use --record after review)"
        if r["required"] and r["status"] not in ("OK",):
            ok_all = False
        results.append(r)
    for name in sorted(set(files) - claimed):
        results.append({"id": name, "required": False, "status": "UNLISTED",
                        "detail": "file not in manifest (add it, with hash, before release)"})
    return results, ok_all


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--record", action="store_true", help="store SHA-256 for entries without one")
    a = ap.parse_args(argv)
    manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    results, ok = check(a.bundle, manifest, a.record)
    for r in results:
        print(f"{r['status']:<13} {r['id']:<34} {r.get('file', '')} {r['detail']}")
    if a.record:
        a.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RESULT:", "OK" if ok else "NOT OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
