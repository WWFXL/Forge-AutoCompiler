"""独立header修订只改变configure环境；保留原失败和完整验收。"""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import forge_build_cxx_header_reference as header  # noqa: E402


def test_only_configure_environment_changes_and_original_is_immutable():
    old = json.loads((ROOT / "benchmarks/manifests/cpp-build-cxx-cross-system-reference-v1.json").read_text())["projects"]
    saved = copy.deepcopy(old)
    repaired = header.repaired_project(old)
    source = next(row for row in old if row["name"] == "libconfig")
    expected = copy.deepcopy(source)
    configure = next(s for s in expected["plan"]["steps"] if s["step_id"] == "configure")
    configure["command"] = "AUTOHEADER=true " + configure["command"]
    assert repaired == expected and old == saved
    assert [s for s in repaired["plan"]["steps"] if s["role"] == "smoke"] == [s for s in source["plan"]["steps"] if s["role"] == "smoke"]


@pytest.mark.parametrize("field,value", [("identity", "old"), ("provider_calls", 1), ("credentials_read", True), ("deadline_utc", "2099-01-01T00:00:00Z"), ("new_project_reserve_seconds", 1)])
def test_rejects_reusing_identity_or_widening_window(field, value, monkeypatch):
    p = dict(identity=header.IDENTITY, provider_calls=0, credentials_read=False, deadline_utc="2026-10-20T22:07:35Z", new_project_reserve_seconds=3300)
    p[field] = value
    monkeypatch.setattr(header, "audit", lambda *a: pytest.fail("越过新身份边界"))
    with pytest.raises(ValueError):
        header.validate(p)
