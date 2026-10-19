"""SDK 真实序列化的离线验证；不访问 Provider。"""

import json
from dataclasses import replace

import httpx
import pytest

from deerflow.compile.plan_agent import PlanAgentLedger, PlanProposal, PlanTask, propose_plan, trial_budget
from deerflow.compile.plan_agent_v2 import PlanAgentMeterV2, PlanThinkingDeepSeek
from deerflow.compile.plan_workflow import PlanStep


def model_with_transport(handler):
    return PlanThinkingDeepSeek(
        model="deepseek-v4-pro",
        api_key="synthetic-offline-client-key",
        base_url="https://api.deepseek.com",
        max_tokens=8192,
        max_retries=0,
        timeout=120,
        extra_body={"thinking": {"type": "enabled"}},
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_thinking_structured_tools_use_auto_in_actual_http_payload():
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-v4-pro",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "offline"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    model_with_transport(handler).bind_tools([PlanProposal], tool_choice="any", parallel_tool_calls=False).invoke("offline serialization check")
    assert len(captured) == 1 and captured[0]["tool_choice"] == "auto"
    assert captured[0]["thinking"]["type"] == "enabled"
    assert captured[0]["parallel_tool_calls"] is False


def test_provider_error_preserves_body_and_unknown_usage_without_retry(tmp_path):
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(400, json={"error": {"message": "synthetic provider rejection", "type": "invalid_request_error", "param": "tool_choice"}})

    task = PlanTask(
        plan_id="offline",
        repository_url="https://example.com/offline.git",
        commit_sha="a" * 40,
        image_id="sha256:" + "1" * 64,
        source_archive_sha256="2" * 64,
        build_system="cmake",
        artifact_paths=("sample.a",),
        verification_steps=(PlanStep(step_id="check", role="smoke", command="ctest --test-dir build", source="任务", expected="测试通过", required_output=("tests passed",)),),
    )
    usage = PlanAgentMeterV2(PlanAgentLedger(tmp_path / "agent"), accepted_models=("deepseek-v4-pro",), budget=replace(trial_budget(), max_model_requests=11, max_recorded_tokens=100_000))
    with pytest.raises(Exception):
        propose_plan(model=model_with_transport(handler), task=task, source_root=tmp_path, meter=usage)
    assert len(attempts) == 1
    summary = usage.summary()
    assert summary["unknown_usage_requests"] == 1 and not summary["cost_and_usage_complete"]
    assert summary["estimated_cost_usd"] is None
    events = (tmp_path / "agent/events.jsonl").read_text()
    assert "synthetic provider rejection" in events and "invalid_request_error" in events
    assert "synthetic-offline-client-key" not in events


def test_actual_sdk_and_graph_accept_auto_structured_plan_and_meter_once(tmp_path):
    check = PlanStep(step_id="check", role="smoke", command="ctest --test-dir build", source="任务", expected="测试通过", required_output=("tests passed",))
    task = PlanTask(
        plan_id="offline", repository_url="https://example.com/offline.git", commit_sha="a" * 40, image_id="sha256:" + "1" * 64, source_archive_sha256="2" * 64, build_system="cmake", artifact_paths=("sample.a",), verification_steps=(check,)
    )
    proposal = PlanProposal(
        reason="离线接线验证",
        steps=[
            PlanStep(step_id="build", role="build", command="cmake --build build", source="README", expected="编译"),
            check,
            PlanStep(step_id="stage", role="artifact_stage", command="cp build/sample.a /artifacts/", source="任务", expected="交付"),
        ],
    )
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload["tool_choice"])
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-v4-pro",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "proposal", "type": "function", "function": {"name": "PlanProposal", "arguments": proposal.model_dump_json()}}]},
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    usage = PlanAgentMeterV2(PlanAgentLedger(tmp_path / "agent"), accepted_models=("deepseek-v4-pro",))
    plan, _ = propose_plan(model=model_with_transport(handler), task=task, source_root=tmp_path, meter=usage)
    assert seen == ["auto"] and plan.steps == tuple(proposal.steps)
    assert usage.summary()["recorded_tokens"] == 5
    assert usage.summary()["cost_and_usage_complete"]
