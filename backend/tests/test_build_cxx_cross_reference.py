"""跨构建系统参考资格：拒绝来源漂移与零Provider边界改变。"""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import forge_build_cxx_cross_reference as reference  # noqa: E402


@pytest.fixture
def protocol(monkeypatch):
    p = json.loads((ROOT / "benchmarks/manifests/cpp-build-cxx-cross-system-reference-v1.json").read_text())
    monkeypatch.setattr(reference, "before_deadline", lambda *a: None)
    return p


@pytest.mark.parametrize("field,value", [("identity", "other"), ("provider_calls", 1), ("credentials_read", True), ("deadline_utc", "2099-01-01T00:00:00Z"), ("new_project_reserve_seconds", 0)])
def test_boundary_rejected_before_evidence_access(protocol, field, value, monkeypatch):
    protocol[field] = value
    monkeypatch.setattr(reference, "audit", lambda *a: pytest.fail("不得越过身份/授权边界"))
    with pytest.raises(ValueError):
        reference.validate(protocol)


def test_parent_change_prevents_execution(protocol, monkeypatch):
    monkeypatch.setattr(reference, "audit", lambda *a: {"inventory_canonical_sha256": "changed"})
    with pytest.raises(ValueError, match="父来源"):
        reference.validate(protocol)


def test_full_author_tests_and_source_preparation_retained(protocol):
    tiny, config = protocol["projects"]
    for row in (tiny, config):
        steps = row["plan"]["steps"]
        assert steps[0]["step_id"] == "forge-source-prepare"
        check = next(s for s in steps if s["step_id"] == "check")
        assert "make" in check["command"] and "check" in check["command"]
        assert "FORGE_SOURCE_INDEX_VERIFIED=" in check["command"]
    command = next(s for s in config["plan"]["steps"] if s["step_id"] == "check")["command"]
    assert "XFAIL" in command and "actual==expected" in command
    assert config["plan"]["artifact_paths"] == ["libconfig.a", "libconfig++.a"]


def test_cleanup_failure_keeps_remaining_project_unobserved(protocol, tmp_path, monkeypatch):
    from forge_build_reference_repair_qualification import execute_schedule

    monkeypatch.setattr("forge_build_reference_repair_qualification.before_deadline", lambda *a: None)
    seen = []

    def failed(item, folder, p):
        seen.append(item["name"])
        return {"name": item["name"], "qualified": False, "status": "stopped", "cleanup": {"succeeded": False}}

    original = copy.deepcopy(protocol)
    rows, unseen, reason = execute_schedule(protocol, tmp_path, executor=failed)
    assert seen == ["tinyxml2"] and len(rows) == 1
    assert unseen == [{"name": "libconfig", "status": "not_observed", "reason": "cleanup_or_infrastructure_failure"}]
    assert reason == "cleanup_or_infrastructure_failure" and protocol == original
