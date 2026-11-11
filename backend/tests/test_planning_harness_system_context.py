"""离线规划提案的材料隔离、单次调用和失败计量；不调用Provider。"""

import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_task import SIMPLE_PROMPT

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_planning_harness_system_context as context  # noqa: E402


@pytest.fixture
def prepared(tmp_path):
    folder = tmp_path / "prepared"
    shutil.copytree(context.FIXTURE, folder)
    return folder


def authorization(prepared):
    scope = context.load(prepared / "scope.json")
    start = datetime.now(UTC) - timedelta(minutes=1)
    return dict(
        **{k: scope[k] for k in ("identity", "requested_model", "maximum_requests", "maximum_cost_usd", "request_sha256")},
        started_at=start.isoformat(),
        deadline=(start + timedelta(hours=4)).isoformat(),
        automatic_retry=False,
        user_authorization="脚本测试，不是真实付费授权",
    )


def test_material_has_real_interfaces_all_projects_and_no_private_or_hidden_data():
    request = context.load(context.FIXTURE / "request.json")
    packet = request["packet"]
    corpus = packet["corpus"]
    trajectories = [e for e in corpus["episodes"] if e["role"] == "optimizer_development"]
    assert len(trajectories) == 18
    assert sum(e["downstream_branches"] for e in trajectories) == 36
    assert packet["old_planning_candidates"]
    assert packet["recovery_fixed_context"]["recovery_guidance"]
    reference = corpus["episodes"][-1]["evidence"][0]["content"]
    assert {s["function"]["name"] for s in reference["readonly_tool_schemas"]} == {"read_source", "list_source", "read_failure_log"}
    assert reference["output_schema"]["function"]["name"] == "SimpleBuildActions"
    for excerpt in reference["source_excerpts"]:
        path = context.ROOT / excerpt["path"]
        assert context.digest(path) == excerpt["file_sha256"]
        assert "".join(path.read_text().splitlines(keepends=True)[excerpt["start_line"] - 1 : excerpt["end_line"]]) == excerpt["content"]
    text = json.dumps(request, ensure_ascii=False)
    assert "reasoning_content" not in text
    assert all("private-reference.json" not in e.get("source_path", "") for ep in corpus["episodes"] for e in ep["evidence"])
    for ep in trajectories:
        project = ep["project"]
        original = context.SOURCE / "initial" / project / "agent"
        expected = len(list(original.glob("response-*.json")))
        actual = sum(e["kind"] == "visible_response" and ":initial:" in e["evidence_id"] for e in ep["evidence"])
        assert expected == actual
        assert sum(e["kind"] == "downstream_outcome_not_planning_causality" for e in ep["evidence"]) == 2


@pytest.mark.parametrize("change", [dict(identity="old"), dict(maximum_requests=2), dict(maximum_cost_usd="2.00"), dict(automatic_retry=True), dict(deadline="2020-01-01T00:00:00+00:00")])
def test_bad_authorization_never_reads_credentials_or_starts_attempt(prepared, tmp_path, change):
    def forbidden():
        pytest.fail("不得建立Provider")

    with pytest.raises(PlanContractError):
        context.generate(prepared, tmp_path / "run", {**authorization(prepared), **change}, forbidden)
    assert not (prepared / "attempt-started.json").exists()


def response(*, model=context.MODEL, usage=True):
    proposal = dict(
        diagnoses=[dict(evidence_ids=["SYS:implementation"], problem="仅测试接口", proposed_change="仅测试附加策略", expected_behavior="待验证")], planning_guidance="依据现有作者证据区分必要前置与可留待执行反馈的问题。", no_change=False
    )
    return AIMessage(content=json.dumps(proposal, ensure_ascii=False), usage_metadata=dict(input_tokens=100, output_tokens=50, total_tokens=150) if usage else None, response_metadata=dict(model_name=model))


class FakeModel:
    def __init__(self, message):
        self.message = message
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        assert len(messages) == 2
        return self.message


def test_single_call_outputs_reviewable_candidate_and_preserves_recovery(prepared, tmp_path):
    model = FakeModel(response())
    auth = authorization(prepared)
    out = tmp_path / "run"
    candidate = context.generate(prepared, out, auth, lambda: model)
    assert model.calls == 1
    assert candidate.name == "P3_system_context"
    assert candidate.prompt(SIMPLE_PROMPT, recovery=True) == SIMPLE_PROMPT
    assert (out / "diff-P0-P3.patch").read_text()
    assert context.load(out / "completed.json")["comparisons_started"] == 0
    with pytest.raises(FileExistsError):
        context.generate(prepared, tmp_path / "second", auth, lambda: model)
    assert model.calls == 1


@pytest.mark.parametrize("message,unknown", [(response(model="other"), False), (response(usage=False), True)])
def test_failure_keeps_response_and_usage_without_retry(prepared, tmp_path, message, unknown):
    model = FakeModel(message)
    out = tmp_path / "failed"
    with pytest.raises(PlanContractError):
        context.generate(prepared, out, authorization(prepared), lambda: model)
    assert model.calls == 1
    assert (out / "response.json").exists()
    assert context.load(out / "failure.json")["unknown_usage"] is unknown
    assert (out / "usage.json").exists() is (not unknown)
    assert not (out / "candidate.json").exists()
