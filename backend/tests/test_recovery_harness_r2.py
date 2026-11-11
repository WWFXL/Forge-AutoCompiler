"""R2 只提案：真实交接保留、一次调用与失败计费，无 Provider。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import SIMPLE_PROMPT

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_recovery_harness_r2 as r2  # noqa: E402

FIXTURE = r2.FIXTURE


def authorization():
    now = datetime.now(UTC)
    return dict(
        identity=r2.IDENTITY,
        requested_model=r2.MODEL,
        maximum_requests=1,
        maximum_cost_usd="1.00",
        request_sha256=r2.load(FIXTURE / "scope.json")["request_sha256"],
        started_at=now.isoformat(),
        deadline=(now + timedelta(hours=4)).isoformat(),
        user_authorization="仅脚本测试，不是真实Provider授权",
    )


def test_corpus_preserves_all_recoveries_contract_feedback_and_state():
    material = r2.load(FIXTURE / "corpus.json")
    recoveries = [e for e in material["episodes"] if e["role"] == "optimizer_development_recovery"]
    assert len(recoveries) == 13
    assert len({e["slot"] for e in recoveries}) == 7
    assert sum(e["requests"] for e in recoveries) == 51
    assert {method: sum(e["requests"] for e in recoveries if e["method"] == method) for method in ("H0", "R1")} == dict(H0=19, R1=32)
    first = recoveries[0]["evidence"][0]["content"]["handoff"]
    assert "step_id" in first and "configuration_state" in first and "successful_dependencies" in first
    feedback = [e["content"] for row in recoveries for e in row["evidence"] if e["kind"] == "proposal_acceptance_and_rejection"]
    assert any("discard_dependencies" in json.dumps(value) for value in feedback)
    assert len([e for e in material["episodes"] if e["role"] == "normal_success_boundary"]) == 3
    assert material["holdout"] is False


@pytest.mark.parametrize("change", [dict(requested_model="gpt-6-astra"), dict(maximum_cost_usd="2.00"), dict(deadline="2026-01-01T00:00:00+00:00")])
def test_unauthorized_request_cannot_create_attempt_or_read_credentials(tmp_path, change):
    auth = authorization() | change
    output = tmp_path / "not-started"

    def forbidden():
        pytest.fail("不得读取凭据或建立模型")

    with pytest.raises(PlanContractError):
        r2.generate(FIXTURE, output, auth, forbidden)
    assert not output.exists()


@pytest.mark.parametrize("response_model,known_usage", [(r2.MODEL, True), ("gpt-5.6", True), (r2.MODEL, False)])
def test_failed_response_preserved_and_no_second_call(tmp_path, response_model, known_usage):
    calls = []

    class Model:
        def invoke(self, messages):
            calls.append(messages)
            return AIMessage(content="invalid JSON", usage_metadata=dict(input_tokens=100, output_tokens=2, total_tokens=102) if known_usage else None, response_metadata=dict(model_name=response_model))

    output = tmp_path / "attempt"
    with pytest.raises(ValueError):
        r2.generate(FIXTURE, output, authorization(), Model)
    assert len(calls) == 1 and (output / "response.json").exists()
    assert r2.load(output / "failure.json")["unknown_usage"] != known_usage
    assert (output / "usage.json").exists() == known_usage
    assert not (output / "candidate.json").exists()
    with pytest.raises(FileExistsError):
        r2.generate(FIXTURE, output, authorization(), Model)
    assert len(calls) == 1


def test_valid_proposal_exports_actual_h0_r1_diffs_without_comparison(tmp_path):
    material = r2.load(FIXTURE / "corpus.json")
    cited = material["episodes"][0]["evidence"][0]["evidence_id"]

    class Model:
        def invoke(self, messages):
            packet = json.loads(messages[1].content)
            assert packet["base_prompt"] == SIMPLE_PROMPT
            assert "successful-rebuild-v1" in packet["common_repairs"]
            return AIMessage(
                content=json.dumps(dict(no_change=False, recovery_guidance="先使用失败交接。", diagnoses=[dict(evidence_ids=[cited], problem="脚本测试", proposed_change="测试更新", expected_behavior="等待比较")]), ensure_ascii=False),
                usage_metadata=dict(input_tokens=100, output_tokens=2, total_tokens=102),
                response_metadata=dict(model_name=r2.MODEL),
            )

    output = tmp_path / "success"
    result = r2.generate(FIXTURE, output, authorization(), Model)
    assert result.name == "R2_recovery"
    assert (output / "prompt-H0.txt").read_text() == SIMPLE_PROMPT
    assert (output / "prompt-R2.txt").read_text() == result.prompt(SIMPLE_PROMPT)
    assert all((output / f"diff-{name}-R2.patch").read_text() for name in ("H0", "R1"))
    receipt = r2.load(output / "completed.json")
    assert receipt["comparisons_started"] == 0 and receipt["thesis_updated"] is False
    assert RecoveryHarness.model_validate(r2.load(output / "candidate.json")) == result


@pytest.fixture(autouse=True)
def frozen_historical_implementation(monkeypatch, tmp_path):
    from frozen_recovery_context import install_frozen_recovery_context

    install_frozen_recovery_context(monkeypatch, tmp_path, r2, sys.modules[__name__], scoped=True)
