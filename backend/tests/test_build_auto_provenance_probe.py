"""独立接口探针的完整配对、未知用量停止和无参数门禁。"""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
spec = importlib.util.spec_from_file_location("auto_provenance_probe", Path(__file__).resolve().parents[2] / "scripts/forge_build_auto_provenance_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def protocol():
    names = ["libsndfile", "buffer", "libverto"]
    return {"projects": [{"name": name} for name in names], "schedule": probe.make_schedule(names), "gate_schedule": probe.make_schedule(names, 1), "deadline_utc": "2099-01-01T00:00:00Z"}


def row(*, cost="0.1", unknown=0, strict=True):
    return {
        "strict_completed": strict,
        "cleanup": {"succeeded": True},
        "agent_usage": {"estimated_cost_usd_completed_responses": cost, "unknown_usage_requests": unknown, "cost_and_usage_complete": not unknown, "model_requests": 1, "recorded_tokens": 100, "commands": 3},
    }


def test_complete_schedule_keeps_method_failure_and_common_limits(tmp_path):
    calls = []

    def execute(**kwargs):
        calls.append(kwargs)
        return {**row(strict=False), "arm": kwargs["arm"]}

    rows, missing, reason = probe.execute_schedule(protocol(), tmp_path, None, {}, executor=execute)
    assert len(rows) == 12 and not missing and reason is None
    assert all(item["command_timeout_seconds"] == 300 and item["replay_timeout_seconds"] == 600 for item in calls)
    assert len({(item["project"], item["repetition"], item["arm"]) for item in rows}) == 12
    analysis = probe.analyze(protocol(), {"arms": rows, "unobserved_schedule": []})
    assert analysis["paired_description_permitted"]
    assert analysis["observed_totals"]["plan"]["strict_completed"] == 0
    assert analysis["observed_totals"]["plan"]["cost_usd"] == pytest.approx(0.6)


def test_stage_reserves_whole_next_arm_and_unknown_usage_stops(tmp_path):
    rows, missing, reason = probe.execute_schedule(protocol(), tmp_path, None, {}, executor=lambda **kwargs: row(cost="1.4"))
    assert len(rows) == 4 and len(missing) == 8 and reason == "stage_cost_reservation"
    rows, missing, reason = probe.execute_schedule(protocol(), tmp_path, None, {}, executor=lambda **kwargs: row(unknown=1))
    assert len(rows) == 1 and len(missing) == 11 and reason == "cleanup_or_unknown_usage"
    assert not probe.analyze(protocol(), {"arms": [{**rows[0], "arm": "plan"}], "unobserved_schedule": missing})["paired_description_permitted"]


def test_unexpected_executor_exception_keeps_prior_observations(tmp_path):
    rows = []

    def execute(**kwargs):
        if rows:
            raise RuntimeError("夹具异常")
        return row()

    with pytest.raises(RuntimeError, match="夹具异常"):
        probe.execute_schedule(protocol(), tmp_path, None, {}, executor=execute, results=rows)
    assert len(rows) == 1


def test_scripted_gate_submits_without_manual_ids():
    from langchain_core.messages import HumanMessage

    reference = {"steps": [{"role": "build", "command": "make", "workdir": "/workspace/repo"}, {"role": "smoke", "command": "fixed", "workdir": "/workspace/repo"}]}
    model = probe.automatic_gate_model(reference)
    first = model.invoke([HumanMessage(content="gate")])
    assert [call["name"] for call in first.tool_calls] == ["run_build_command", "run_fixed_tests", "submit_verified_build"]
    assert first.tool_calls[-1]["args"] == {}
    assert first.usage_metadata["total_tokens"] == 0
