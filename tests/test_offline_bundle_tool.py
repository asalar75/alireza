import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import verify_offline_bundle as vb  # noqa: E402


@pytest.mark.parametrize("name,ok", [
    ("six-1.17.0-py2.py3-none-any.whl", True),
    ("pillow-12.3.0-cp312-cp312-win_amd64.whl", True),
    ("PySide6-6.8.3-cp39-abi3-win_amd64.whl", True),
    ("pypdfium2-5.13.0-py3-none-win_amd64.whl", True),
    ("pillow-12.3.0-cp311-cp311-win_amd64.whl", False),      # wrong Python
    ("pillow-12.3.0-cp313-cp313-win_amd64.whl", False),
    ("pillow-12.3.0-cp312-cp312-win32.whl", False),          # 32-bit
    ("pillow-12.3.0-cp312-cp312-win_arm64.whl", False),      # ARM64 unsupported
    ("pillow-12.3.0-cp312-cp312-manylinux_2_28_x86_64.whl", False),
    ("cryptography-50.0.1-cp314-abi3-win_amd64.whl", False), # abi3 built for a newer minimum Python
    ("notawheel.whl", False),
])
def test_wheel_tag_compatibility(name, ok):
    assert (vb.wheel_problem(name) is None) == ok


def manifest(tmp_path, entries):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"entries": entries}))
    return p


def test_missing_ambiguous_unlisted_and_ok(tmp_path):
    b = tmp_path / "bundle"; b.mkdir()
    (b / "six-1.17.0-py2.py3-none-any.whl").write_bytes(b"a")
    (b / "extra-1.0-py3-none-any.whl").write_bytes(b"b")
    (b / "dup-1-py3-none-any.whl").write_bytes(b"c"); (b / "dup-2-py3-none-any.whl").write_bytes(b"d")
    m = {"entries": [{"id": "six", "glob": "six-*.whl"}, {"id": "gone", "glob": "gone-*.whl"},
                     {"id": "dup", "glob": "dup-*.whl"}]}
    res, ok = vb.check(b, m)
    st = {r["id"]: r["status"] for r in res}
    assert st["six"] == "UNRECORDED" and st["gone"] == "MISSING" and st["dup"] == "AMBIGUOUS"
    assert st["extra-1.0-py3-none-any.whl"] == "UNLISTED" and not ok


def test_record_then_detect_tampering(tmp_path):
    b = tmp_path / "bundle"; b.mkdir()
    f = b / "six-1.17.0-py2.py3-none-any.whl"; f.write_bytes(b"original")
    m = {"entries": [{"id": "six", "glob": "six-*.whl"}]}
    _, ok = vb.check(b, m, record=True)
    assert ok and m["entries"][0]["sha256"] == vb.sha256(f)
    assert vb.check(b, m)[1] is True
    f.write_bytes(b"tampered")
    res, ok = vb.check(b, m)
    assert not ok and res[0]["status"] == "HASH_MISMATCH"


def test_incompatible_wheel_is_rejected(tmp_path):
    b = tmp_path / "bundle"; b.mkdir()
    (b / "pillow-12.3.0-cp311-cp311-win_amd64.whl").write_bytes(b"x")
    res, ok = vb.check(b, {"entries": [{"id": "pillow", "glob": "pillow-*.whl"}]})
    assert not ok and res[0]["status"] == "INCOMPATIBLE"


def test_real_manifest_is_well_formed_and_cli_reports_missing(tmp_path, capsys):
    m = json.loads(vb.MANIFEST.read_text(encoding="utf-8"))
    ids = [e["id"] for e in m["entries"]]
    assert len(ids) == len(set(ids)) and {"vazirmatn-regular", "vazirmatn-bold", "vazirmatn-ofl",
                                         "arabic-reshaper", "python-bidi"} <= set(ids)
    assert all(e["glob"] and e["status"] in ("sandbox-version", "candidate") for e in m["entries"])
    assert vb.main(["--bundle", str(tmp_path)]) == 1 and "NOT OK" in capsys.readouterr().out
