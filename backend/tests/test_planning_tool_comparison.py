"""三组干预隔离、运行前门禁与分阶段工具计量；零Provider。"""

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_task import SIMPLE_PROMPT

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_planning_tool_comparison as c  # noqa: E402


@pytest.fixture(autouse=True)
def recorded_source_hashes(monkeypatch):
    # CI无需下载研究源码；真实入口的--check-prepared仍核对实际归档。
    value = c.shared.load(c.MANIFEST)
    hashes = {Path(p["source_archive"]): p["task"]["source_archive_sha256"] for p in value["projects"]}
    actual = c.digest
    monkeypatch.setattr(c, "digest", lambda p: hashes[p] if p in hashes else actual(p))


def test_three_arm_schedule_and_author_references():
    rows = c.schedule()
    assert len(rows) == 36
    assert Counter(r["method"] for r in rows) == Counter(dict.fromkeys(c.METHODS, 12))
    assert len({r["project"] for r in rows}) == 12
    for project in {r["project"] for r in rows}:
        assert {r["method"] for r in rows if r["project"] == project} == set(c.METHODS)
    orders = [tuple(r["method"] for r in rows[i : i + 3]) for i in range(0, 36, 3)]
    assert set(Counter(orders).values()) == {2}
    for p in c.shared.load(c.FIXTURE)["projects"]:
        c.BuildReference.model_validate(p["reference"]).require_main_build_verification()


def test_initial_only_policy_and_identical_recovery(tmp_path, monkeypatch):
    item = c.shared.load(c.FIXTURE)["projects"][0]
    calls = []
    monkeypatch.setattr(c.shared, "run_simple_system", lambda **kw: calls.append(kw) or {})
    run = c.executor(object())
    for m in c.METHODS:
        run(slot=dict(method=m), item=item, folder=tmp_path / m, available=1, deadline="2099-01-01T00:00:00+00:00")
    assert [x["enforce_planning_tools"] for x in calls] == [False, True, True]
    assert calls[0]["harness"] == calls[1]["harness"] != calls[2]["harness"]
    assert calls[0]["harness"].prompt(SIMPLE_PROMPT) == SIMPLE_PROMPT
    for k in ("task", "reference", "model", "recovery_harness", "validation_scope", "source_archive", "maximum_cost_usd"):
        assert calls[0][k] == calls[1][k] == calls[2][k]
    assert all("initial_plan" not in x for x in calls)


def test_prepared_no_provider_and_changed_policy_rejected(monkeypatch, capsys):
    monkeypatch.setattr(c, "run_paid", lambda *a: pytest.fail("不应读取凭据或调用Provider"))
    monkeypatch.setattr(sys, "argv", ["comparison", "--check-prepared"])
    c.main()
    assert json.loads(capsys.readouterr().out)["provider_calls"] == 0
    value = c.shared.load(c.MANIFEST)
    value["enforce_planning_tools"][c.METHODS[0]] = True
    with pytest.raises(PlanContractError, match="工具约束"):
        c.validate(value)


def test_missing_authorization_before_provider(monkeypatch):
    monkeypatch.setattr(c, "run_paid", lambda *a: pytest.fail("未授权不可调用Provider"))
    monkeypatch.setattr(sys, "argv", ["comparison", "--run"])
    with pytest.raises(PlanContractError, match="有效授权"):
        c.main()


def test_tool_behavior_separates_recovery_and_denials(tmp_path):
    (tmp_path / "agent").mkdir()
    events = [
        dict(event="agent.started", recovery=False),
        dict(event="planning.context", finalize_only=True),
        dict(event="tool.started", name="read_source"),
        dict(event="planning.tool_rejected"),
        dict(event="tool.completed", name="read_source", executed=False),
        dict(event="agent.started", recovery=True),
        dict(event="tool.started", name="read_source"),
        dict(event="tool.completed", name="read_source"),
    ]
    (tmp_path / "agent/events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    b = c.tool_behavior(tmp_path)
    assert b["initial"] == dict(finalize_only_requests=1, rejected_tool_calls=1, executed_read_calls=0, attempted_read_calls=1)
    assert b["recovery"] == dict(finalize_only_requests=0, rejected_tool_calls=0, executed_read_calls=1, attempted_read_calls=1)
