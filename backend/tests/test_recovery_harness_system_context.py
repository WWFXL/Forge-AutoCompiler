"""实现上下文、同源材料与独立一次复分析；全部零Provider。"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.simple_build_task import SIMPLE_PROMPT

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_recovery_harness_system_context as context  # noqa: E402


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 10, 15, 0, tzinfo=UTC)

    monkeypatch.setattr(context, "datetime", FixedDateTime)


def authorization():
    scope = context.load(context.FIXTURE / "scope.json")
    return dict(
        identity=context.IDENTITY,
        requested_model=context.MODEL,
        maximum_requests=1,
        shared_maximum_cost_usd="1.00",
        prior_paid_usd=scope["prior_paid_usd"],
        started_at=context.SHARED_START,
        deadline=context.SHARED_DEADLINE,
        request_sha256=scope["request_sha256"],
        user_authorization="仅脚本测试，不是真实Provider授权",
    )


def test_context_preserves_original_trajectories_and_exposes_real_interfaces():
    old = context.load(context.PREVIOUS_INPUT / "corpus.json")
    material = context.load(context.FIXTURE / "corpus.json")
    assert material["episodes"][:-1] == old["episodes"]
    reference = material["episodes"][-1]
    assert reference["role"] == "implementation_reference_not_trajectory"
    implementation = reference["evidence"][0]["content"]
    names = {t["function"]["name"] for t in implementation["readonly_tool_schemas"]}
    assert names == {"read_source", "list_source", "read_failure_log"}
    schema = implementation["output_schema"]["function"]
    assert schema["name"] == "SimpleBuildActions"
    assert set(schema["parameters"]["properties"]) == {"reason", "steps", "build_directory", "discard_dependencies"}
    for excerpt in implementation["source_excerpts"]:
        path = context.ROOT / excerpt["path"]
        actual = "".join(path.read_text().splitlines(keepends=True)[excerpt["start_line"] - 1 : excerpt["end_line"]])
        assert excerpt["content"] == actual
        assert context.digest(path) == excerpt["file_sha256"]
    request = context.load(context.FIXTURE / "request.json")
    assert request["packet"]["prior_R2_proposal"] == context.load(context.PREVIOUS_OUTPUT / "proposal.json")
    assert request["packet"]["base_prompt"] == SIMPLE_PROMPT


@pytest.mark.parametrize("change", [dict(identity="old-R2"), dict(deadline="2026-11-11T18:24:13+00:00"), dict(prior_paid_usd="0"), dict(shared_maximum_cost_usd="2.00")])
def test_no_credentials_or_attempt_when_new_instruction_does_not_match(tmp_path, change):
    def forbidden():
        pytest.fail("不得建立模型或读取凭据")

    output = tmp_path / "not-started"
    with pytest.raises(PlanContractError):
        context.generate(context.FIXTURE, output, authorization() | change, forbidden)
    assert not output.exists()


@pytest.mark.parametrize("model,usage", [(context.MODEL, None), ("gpt-5.6", dict(input_tokens=100, output_tokens=2, total_tokens=102)), (context.MODEL, dict(input_tokens=900000, output_tokens=2, total_tokens=900002))])
def test_failure_preserves_response_and_counts_shared_cost_without_retry(tmp_path, model, usage):
    calls = []

    class Model:
        def invoke(self, messages):
            calls.append(messages)
            return AIMessage(content="invalid JSON", usage_metadata=usage, response_metadata=dict(model_name=model))

    output = tmp_path / "failed"
    with pytest.raises(ValueError):
        context.generate(context.FIXTURE, output, authorization(), Model)
    assert len(calls) == 1 and (output / "response.json").exists()
    assert context.load(output / "failure.json")["unknown_usage"] == (usage is None)
    if usage:
        paid = context.load(output / "usage.json")
        assert paid["shared_cumulative_cost_usd"] != paid["estimated_cost_usd_completed_responses"]
    with pytest.raises(FileExistsError):
        context.generate(context.FIXTURE, output, authorization(), Model)
    assert len(calls) == 1


def test_valid_new_proposal_keeps_original_r2_and_exports_three_diffs(tmp_path):
    class Model:
        def invoke(self, messages):
            packet = json.loads(messages[1].content)
            assert packet["corpus"]["episodes"][-1]["evidence"][0]["evidence_id"] == "SYS:implementation"
            return AIMessage(
                content=json.dumps(
                    dict(
                        no_change=False, recovery_guidance="仅在当前只读接口内定位真实失败并返回方案。", diagnoses=[dict(evidence_ids=["SYS:implementation"], problem="测试接口诊断", proposed_change="测试建议", expected_behavior="尚待比较")]
                    ),
                    ensure_ascii=False,
                ),
                usage_metadata=dict(input_tokens=100, output_tokens=2, total_tokens=102),
                response_metadata=dict(model_name=context.MODEL),
            )

    previous = (context.PREVIOUS_OUTPUT / "proposal.json").read_bytes()
    output = tmp_path / "success"
    result = context.generate(context.FIXTURE, output, authorization(), Model)
    assert result.name == "R2_system_context"
    assert (output / "prompt-R2-system-context.txt").read_text() == result.prompt(SIMPLE_PROMPT)
    assert all((output / f"diff-{name}-R2-system-context.patch").read_text() for name in ("H0", "R1", "R2-original"))
    assert (context.PREVIOUS_OUTPUT / "proposal.json").read_bytes() == previous
    receipt = context.load(output / "completed.json")
    assert receipt["shared_cumulative_cost_usd"] == "0.106909"
    assert receipt["comparisons_started"] == 0 and receipt["thesis_updated"] is False
