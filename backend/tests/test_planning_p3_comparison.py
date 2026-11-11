"""P3比较的干预隔离、预算门禁和分阶段计量；无真实Provider。"""

import copy
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_task import SIMPLE_PROMPT

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_planning_p3_comparison as comparison  # noqa: E402


@pytest.fixture(autouse=True)
def frozen_implementation(monkeypatch, tmp_path, request):
    from frozen_recovery_context import install_frozen_components

    if request.node.name != "test_manifest_guards_source_and_candidate":
        return
    manifest = comparison.shared.load(comparison.MANIFEST)
    install_frozen_components(monkeypatch, tmp_path, comparison, manifest["components"], "1aa4a3c99ba231ca75418a5028e4f32febbfa73c")


def test_schedule_balances_system_and_first_method():
    rows = comparison.schedule()
    assert len(rows) == 36
    assert Counter(r["method"] for r in rows) == Counter(P0_R2=18, P3_R2=18)
    items = {p["name"]: p for p in comparison.shared.load(comparison.SELECTION)["projects"]}
    for system in ("cmake", "make", "autotools"):
        assert Counter(r["method"] for r in rows[::2] if items[r["project"]]["proposed_build_system"] == system) == Counter(P0_R2=3, P3_R2=3)
    for a, b in zip(rows[::2], rows[1::2], strict=True):
        assert a["project"] == b["project"] and a["method"] != b["method"]


def test_excludes_optimizer_and_old_planning_evaluation_projects():
    excluded = {
        "yaml-cpp",
        "snappy",
        "simdutf",
        "md4c",
        "libtommath",
        "libhydrogen",
        "tinyxml2",
        "fse",
        "check",
        "libsodium",
        "libverto",
        "libsigcplusplus",
        "jsoncpp",
        "highwayhash",
        "libite",
        "double-conversion",
        "miniz",
        "libogg",
        "libsrtp",
        "xxhash",
        "pigz",
    }
    old = comparison.ROOT / "benchmarks/fixtures/recovery-harness-r2-comparison-v1/selection.json"
    excluded.update(p["name"].lower() for p in comparison.shared.load(old)["projects"])
    selected = {p["name"].lower() for p in comparison.shared.load(comparison.SELECTION)["projects"]}
    assert not selected & excluded
    assert len(selected) == 18


def test_planning_only_diff_and_shared_original_recovery():
    planning, recovery = comparison.harnesses()
    assert planning["P0_R2"].prompt(SIMPLE_PROMPT) == SIMPLE_PROMPT
    assert planning["P3_R2"].fingerprint() == comparison.P3_SHA
    assert planning["P3_R2"].prompt(SIMPLE_PROMPT, recovery=True) == SIMPLE_PROMPT
    original = comparison.shared.load(comparison.R2_FILE)
    assert recovery.recovery_guidance == original["recovery_guidance"]
    assert recovery.model_dump(mode="json") == original | dict(base_prompt_sha256=comparison._digest(SIMPLE_PROMPT))


def test_both_callbacks_independently_plan_with_identical_recovery(tmp_path, monkeypatch):
    item = comparison.shared.load(comparison.FIXTURE)["projects"][0]
    calls = []
    monkeypatch.setattr(comparison.shared, "run_simple_system", lambda **kwargs: calls.append(kwargs) or {})
    callback = comparison.executor(object())
    for method in comparison.METHODS:
        callback(slot=dict(method=method), item=item, folder=tmp_path / method, available=1, deadline="2099-01-01T00:00:00+00:00")
    assert calls[0]["harness"] != calls[1]["harness"]
    assert calls[0]["recovery_harness"] == calls[1]["recovery_harness"]
    for call in calls:
        assert "initial_plan" not in call
        assert "bank" not in call and "recipe" not in call
        assert call["maximum_cost_usd"] == "0.40"
        assert call["validation_scope"] == "main_build"
        assert call["state_router"].method == "rule"
    for key in ("task", "reference", "source_archive", "accepted_models", "model"):
        assert calls[0][key] == calls[1][key]


def test_authorization_gate_runs_before_credential_load(tmp_path, monkeypatch):
    value = comparison.shared.load(comparison.MANIFEST)
    auth = tmp_path / "auth.json"
    comparison.save(auth, dict(identity="old-experiment", candidate_sha256="old", user_reply="旧授权"))
    monkeypatch.setattr(comparison, "validate", lambda value: None)
    monkeypatch.setattr(comparison, "run_paid", lambda *args: pytest.fail("无效授权不可读取凭据/创建模型"))
    monkeypatch.setattr(sys, "argv", ["comparison", "--run", "--authorization", str(auth), "--output", str(tmp_path / "output")])
    with pytest.raises(PlanContractError, match="确切身份"):
        comparison.main()
    start = datetime.now(UTC) - timedelta(seconds=1)
    comparison.save(
        auth,
        dict(
            identity=comparison.IDENTITY,
            candidate_sha256=comparison.digest(comparison.MANIFEST),
            user_reply="测试授权非真实",
            authorized_at_utc=start.isoformat(),
            deadline_utc=(start + timedelta(hours=4)).isoformat(),
            automatic_retry=False,
            maximum_cost_usd="6.00",
        ),
    )
    with pytest.raises(PlanContractError, match="硬上限"):
        comparison.main()
    assert value["maximum_cost_usd"] == "5.00"


def test_manifest_guards_source_and_candidate(monkeypatch):
    value = comparison.shared.load(comparison.MANIFEST)
    hashes = {Path(p["source_archive"]): p["task"]["source_archive_sha256"] for p in value["projects"]}
    actual = comparison.digest
    monkeypatch.setattr(comparison, "digest", lambda p: hashes[p] if p in hashes else actual(p))
    comparison.validate(value)
    bad = copy.deepcopy(value)
    bad["planning_harnesses"]["P3_R2"]["planning_guidance"] += "变更"
    with pytest.raises(PlanContractError, match="指导"):
        comparison.validate(bad)
    bad = copy.deepcopy(value)
    bad["initial_plan"] = "shared_plan"
    with pytest.raises(PlanContractError, match="独立规划"):
        comparison.validate(bad)


def test_phase_cost_keeps_failure_and_recovery(tmp_path):
    events = [
        dict(event="agent.started", recovery=False),
        dict(event="model.request_completed", input_tokens=100, output_tokens=10),
        dict(event="model.cost_estimated", cost_usd="0.000042"),
        dict(event="tool.started", name="read_source", args=dict(path="README.md")),
        dict(event="agent.started", recovery=True),
        dict(event="model.request_completed", input_tokens=200, output_tokens=20),
        dict(event="model.cost_estimated", cost_usd="0.000084"),
        dict(event="tool.started", name="read_source", args=dict(path="README.md")),
        dict(event="tool.started", name="read_source", args=dict(path="README.md")),
    ]
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent/events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    result = comparison.phase_usage(tmp_path)
    assert result["initial"]["estimated_cost_usd"] == "0.000042"
    assert result["recovery"]["estimated_cost_usd"] == "0.000084"
    assert result["recovery"]["requests"] == 1
    assert result["recovery"]["exact_repeat_reads"] == 1
    assert result["initial"]["exact_repeat_reads"] == 0
