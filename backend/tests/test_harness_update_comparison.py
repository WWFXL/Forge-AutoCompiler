"""本轮18项目比较的隔离、分母与授权边界；不调用Provider。"""

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_task import SIMPLE_PROMPT

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_harness_update_comparison as c  # noqa: E402


def test_schedule_covers_all_18_without_repeats():
    rows = c.schedule()
    assert len(rows) == 36
    assert Counter(r["method"] for r in rows) == Counter(dict.fromkeys(c.METHODS, 18))
    assert len({r["project"] for r in rows}) == 18
    assert sum(r["project"] == "libffi" for r in rows) == 2
    assert Counter(tuple(r["method"] for r in rows[i : i + 2]) for i in range(0, 36, 2)) == Counter({c.METHODS: 9, c.METHODS[::-1]: 9})
    for p in c.shared.load(c.FIXTURE)["projects"]:
        ref = c.BuildReference.model_validate(p["reference"])
        ref.require_main_build_verification()


def test_identical_tasks_independent_planning_and_isolated_tools(tmp_path, monkeypatch):
    calls = []
    item = c.shared.load(c.FIXTURE)["projects"][0]
    monkeypatch.setattr(c.shared, "run_simple_system", lambda **kw: calls.append(kw) or {})
    run = c.executor(object())
    for method in c.METHODS:
        run(slot=dict(method=method), item=item, folder=tmp_path / method, available=1, deadline="2099-01-01T00:00:00+00:00")
    old, new = calls
    for key in ("task", "reference", "source_archive", "model", "maximum_cost_usd", "harness", "enforce_planning_tools", "validation_scope", "replay_seconds"):
        assert old[key] == new[key]
    assert old["harness"].prompt(SIMPLE_PROMPT) == SIMPLE_PROMPT
    for key in ("recovery_environment_tools", "retain_recovery_diagnostics", "diagnose_dependencies", "inspect_planning_dependencies"):
        assert old[key] is False and new[key] is True
    assert "libltdl-dev" not in old["recovery_harness"].prompt(SIMPLE_PROMPT)
    assert "libltdl-dev" in new["recovery_harness"].prompt(SIMPLE_PROMPT)
    for call in calls:
        assert not {"initial_plan", "bank", "recipe"} & call.keys()


def test_default_material_check_does_not_read_credentials(monkeypatch, capsys):
    # CI不依赖服务器源码归档；真实CLI默认核对归档SHA。
    actual_validate = c.validate
    monkeypatch.setattr(c, "validate", lambda value: actual_validate(value, check_sources=False))
    monkeypatch.setattr(c, "run_paid", lambda *a: pytest.fail("不应读取凭据或调用Provider"))
    monkeypatch.setattr(sys, "argv", ["comparison", "--check-prepared"])
    c.main()
    assert json.loads(capsys.readouterr().out)["provider_calls"] == 0
    value = c.shared.load(c.MANIFEST)
    value["recipe_reuse"] = True
    with pytest.raises(PlanContractError):
        actual_validate(value, check_sources=False)


def test_missing_authorization_rejected_before_provider(monkeypatch):
    monkeypatch.setattr(c, "validate", lambda value: None)
    monkeypatch.setattr(c, "run_paid", lambda *a: pytest.fail("未授权不可调用Provider"))
    monkeypatch.setattr(sys, "argv", ["comparison", "--run"])
    with pytest.raises(PlanContractError, match="有效授权"):
        c.main()


def test_all_18_report_retains_unobserved_instead_of_failures(tmp_path):
    row = dict(
        slot=1,
        project="pocketsphinx",
        method=c.METHODS[0],
        status="primary_completed",
        layers=dict(main_build_task_completed=True),
        agent_usage=dict(model_requests=2, input_tokens=11, output_tokens=7, estimated_cost_usd_completed_responses="0.01"),
        arm_total_wall_seconds=3,
    )
    c.shared.save(tmp_path / "result.json", dict(rows=[row], unobserved=c.schedule()[1:], unclosed_slot=None, billing_complete=True, closed_slot_cost_usd="0.01"))
    result = c.analyze(tmp_path)
    assert set(result["arms"]) == set(c.METHODS)
    assert result["arms"][c.METHODS[0]]["observed"] == 1
    assert result["arms"][c.METHODS[0]]["unobserved"] == 17
    assert result["arms"][c.METHODS[1]]["unobserved"] == 18
    assert result["arms"][c.METHODS[0]]["main_build_completed"] == 1
    assert result["arms"][c.METHODS[0]]["estimated_cost_usd"] == "0.01"
