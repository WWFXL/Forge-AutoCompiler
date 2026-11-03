"""实际Agent消息链验证任务快照及纠错/恢复边界；全部使用脚本响应，零Provider。"""

import copy
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from test_conditioned_experience import entry, trace
from test_goal_state import task
from test_plan_candidate_reception import COMMON, GateModel, candidate

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_action_experience as runner  # noqa: E402
from forge_analyze_action_experience import exploration  # noqa: E402
from forge_build_rtorrent_fixed_contract import FixedVerifierRegistry  # noqa: E402
from forge_build_rtorrent_shared_values import restore_values  # noqa: E402

from deerflow.compile.action_experience import ActionBank, TaskExperience, validate_action_extraction
from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.recovery_text_factors import restore_factor_packet


class CountingBank:
    sources, entries = {}, []

    def __init__(self):
        self.calls = []

    def retrieve(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return dict(mode=kwargs["mode"], sources=["history"], items=[dict(stage=kwargs["stage"])], bytes=30)


def test_empty_selection_is_cached_but_dynamic_state_and_new_task_change(tmp_path):
    bank = CountingBank()
    bank.retrieve = lambda **kw: bank.calls.append(kw) or dict(mode="structured", sources=[], items=[], bytes=0)
    cache = TaskExperience(task=task(), family="target", bank=bank, mode="structured", ledger=PlanAgentLedger(tmp_path / "ledger"))
    with pytest.raises(RuntimeError, match="必须先开始"):
        cache.attach({})
    cache.begin(dict(handoff=None))
    first = cache.attach(dict(state={"current": 1}))
    first["historical_build_experience"]["items"].append("外部修改")
    second = cache.attach(dict(state={"current": 2}, latest_tool="真实新反馈"))
    assert second["state"]["current"] == 2 and second["latest_tool"] == "真实新反馈"
    assert second["historical_build_experience"]["items"] == [] and len(bank.calls) == 1
    cache.begin(dict(handoff=dict(stage="configure", reason="新的失败")))
    assert len(bank.calls) == 2 and bank.calls[-1]["stage"] == "configure"


def test_actual_initial_read_correction_and_recovery_share_one_selection_per_task(tmp_path):
    value, bank = task(), CountingBank()
    item = dict(name="target", task=value.model_dump(mode="json"), common_test_preparation={})
    registry = FixedVerifierRegistry(value.model_dump(mode="json"))
    context = dict(task=value.model_dump(mode="json"), source_packet=[], current_plan=None, handoff=None)
    meter = runner.meter_class(item, value, bank, "structured")(
        PlanAgentLedger(tmp_path / "agent"), registry=registry, obligation={}, accepted_models=("scripted-common",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: context
    )
    (tmp_path / "README.md").write_text("当前项目构建说明\n")
    invalid = candidate()
    invalid["steps"][0]["required_output"] = ["错误字段"]
    responses = [
        AIMessage(content="", tool_calls=[dict(name="read_source", args=dict(path="README.md"), id="read")], **COMMON),
        AIMessage(content=json.dumps(invalid), **COMMON),
        AIMessage(content=json.dumps(candidate()), **COMMON),
        AIMessage(content=json.dumps(candidate("make changed-target")), **COMMON),
    ]
    model = GateModel(responses=responses)
    with runner.task_interfaces():
        # 在context内查找被包装入口，走真实候选反馈和工具消息链。
        from deerflow.compile import unified_plan_equivalent_observed as observed

        planner = observed.observed_planner("model")
        kwargs = dict(task=value, source_root=tmp_path, session_root=tmp_path, model=model, meter=meter)
        plan, _ = planner(**kwargs)
        assert len(bank.calls) == 1 and meter.summary()["model_requests"] == 3
        handoff = dict(handoff_id="actual-failure", plan_sha256=plan.fingerprint(), step_id="build", recent_commands=[], reason="missing target")
        context.update(current_plan=plan.model_dump(mode="json"), handoff=handoff)
        changed, _ = planner(**kwargs, current_plan=plan, handoff=handoff)
        assert changed.revision == 2 and len(bank.calls) == 2
    raw = json.loads((tmp_path / "agent/request-3.json").read_text())
    packet = json.loads(raw["messages"][0]["content"])
    packet.pop("remaining_budget")
    restored = registry.restore(restore_values(restore_factor_packet(packet)))
    assert restored["read_index"][-1]["request"]["path"] == "README.md"
    assert restored["rejected_candidate"]["arguments"] == invalid
    events = [json.loads(line) for line in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    selected = [e for e in events if e["event"] == "experience.task_selected"]
    used = [e for e in events if e["event"] == "experience.context_used"]
    assert len(selected) == 2 and [e["episode"] for e in used] == [1, 1, 1, 2]
    assert len({e["context_sha256"] for e in used[:3]}) == 1
    assert selected[-1]["stage"] == "build"
    measured = exploration(events)
    assert measured["phases"]["initial"]["read_source"] == 1
    assert measured["phases"]["initial"]["requests"] == 3
    assert measured["phases"]["recovery"]["requests"] == 1
    assert meter.summary()["unknown_usage_requests"] == 0


def action():
    return entry() | dict(check_before_action=["核对作者测试选项"], expected_observation="配置实际启用原测试")


def test_short_action_retains_failure_scope_and_rejects_invented_evidence():
    rows = validate_action_extraction(dict(experiences=[action()]), trace())
    assert rows[0]["observed_validation"]["tests"] == "unobserved"
    assert rows[0]["expected_observation"] == "配置实际启用原测试"
    assert rows[0]["observed_revision"] is None
    with pytest.raises(ValueError, match="不存在"):
        validate_action_extraction(dict(experiences=[action() | dict(evidence_ids=["invented"])]), trace())


def test_action_selection_requires_current_signal_and_excludes_same_family():
    row = action() | dict(applicability=dict(required_files=[], declaration_terms=[], error_markers=["not found"]))
    entries = validate_action_extraction(dict(experiences=[row]), trace())
    bank = ActionBank([trace() | dict(retrieval_text="", raw_context={})], entries, dict(target=dict(files=[], declarations=[]), **{"seed": dict(files=[], declarations=[])}))
    args = dict(build_system="cmake", family="target", stage="configure", mode="structured")
    assert bank.retrieve(**args, text='{"handoff":{}}')["items"] == []
    assert bank.retrieve(**args, text='{"handoff":{"output":"dependency not found"}}')["sources"] == [trace()["source_id"]]
    assert bank.retrieve(**(args | dict(family=trace()["family"])), text='{"handoff":{"output":"not found"}}')["items"] == []


def test_missing_new_authorization_stops_before_paid_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "SESSION", tmp_path)
    monkeypatch.setattr(runner, "check_prepared", lambda: {})
    monkeypatch.setattr(runner.previous, "extract", lambda: pytest.fail("不能进入付费入口"))
    with pytest.raises(FileNotFoundError):
        runner.extract()
    assert list(tmp_path.iterdir()) == []
