from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from langgraph.errors import GraphBubbleUp

from deerflow.agents.middlewares.llm_error_handling_middleware import (
    LLMErrorHandlingMiddleware,
)
from deerflow.compile.evidence import (
    AttemptBudgetExceeded,
    ExperimentAttemptBudget,
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
)


class FakeError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.body = body
        self.response = SimpleNamespace(status_code=status_code, headers=headers or {}) if status_code is not None or headers else None


def _build_middleware(**attrs: int) -> LLMErrorHandlingMiddleware:
    middleware = LLMErrorHandlingMiddleware()
    for key, value in attrs.items():
        setattr(middleware, key, value)
    return middleware


def test_successful_model_call_registers_tool_origins_before_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str | None, object, str]] = []

    def register(thread_id, response, *, model_request_id):
        captured.append((thread_id, response, model_request_id))
        return 1

    monkeypatch.setattr(
        "deerflow.agents.middlewares.llm_error_handling_middleware.record_model_tool_call_origins",
        register,
    )
    request = SimpleNamespace(runtime=SimpleNamespace(context={"thread_id": "thread-observability", "agent_name": "compiler"}))
    response = AIMessage(
        content="",
        tool_calls=[{"name": "run_container_bash", "id": "call-1", "args": {"command": "pwd"}}],
    )

    assert LLMErrorHandlingMiddleware().wrap_model_call(request, lambda _request: response) is response
    assert len(captured) == 1
    assert captured[0][0] == "thread-observability"
    assert captured[0][1] is response
    assert captured[0][2].startswith("model_request_")


def test_async_model_call_retries_busy_provider_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    middleware = _build_middleware(retry_max_attempts=3, retry_base_delay_ms=25, retry_cap_delay_ms=25)
    attempts = 0
    waits: list[float] = []
    events: list[dict] = []

    async def fake_sleep(delay: float) -> None:
        waits.append(delay)

    def fake_writer():
        return events.append

    async def handler(_request) -> AIMessage:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise FakeError("当前服务集群负载较高，请稍后重试，感谢您的耐心等待。 (2064)")
        return AIMessage(content="ok")

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "langgraph.config.get_stream_writer",
        fake_writer,
    )

    result = asyncio.run(middleware.awrap_model_call(SimpleNamespace(), handler))

    assert isinstance(result, AIMessage)
    assert result.content == "ok"
    assert attempts == 3
    assert waits == [0.025, 0.025]
    assert [event["type"] for event in events] == ["llm_retry", "llm_retry"]


def test_async_model_call_returns_user_message_for_quota_errors() -> None:
    middleware = _build_middleware(retry_max_attempts=3)

    async def handler(_request) -> AIMessage:
        raise FakeError(
            "insufficient_quota: account balance is empty",
            status_code=429,
            code="insufficient_quota",
        )

    result = asyncio.run(middleware.awrap_model_call(SimpleNamespace(), handler))

    assert isinstance(result, AIMessage)
    assert "out of quota" in str(result.content)


def test_sync_model_call_uses_retry_after_header(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = _build_middleware(retry_max_attempts=2, retry_base_delay_ms=10, retry_cap_delay_ms=10)
    waits: list[float] = []
    attempts = 0

    def fake_sleep(delay: float) -> None:
        waits.append(delay)

    def handler(_request) -> AIMessage:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise FakeError(
                "server busy",
                status_code=503,
                headers={"Retry-After": "2"},
            )
        return AIMessage(content="ok")

    monkeypatch.setattr("time.sleep", fake_sleep)

    result = middleware.wrap_model_call(SimpleNamespace(), handler)

    assert isinstance(result, AIMessage)
    assert result.content == "ok"
    assert waits == [2.0]


def test_sync_model_call_propagates_graph_bubble_up() -> None:
    middleware = _build_middleware()

    def handler(_request) -> AIMessage:
        raise GraphBubbleUp()

    with pytest.raises(GraphBubbleUp):
        middleware.wrap_model_call(SimpleNamespace(), handler)


def test_async_model_call_propagates_graph_bubble_up() -> None:
    middleware = _build_middleware()

    async def handler(_request) -> AIMessage:
        raise GraphBubbleUp()

    with pytest.raises(GraphBubbleUp):
        asyncio.run(middleware.awrap_model_call(SimpleNamespace(), handler))


def test_active_experiment_records_one_429_attempt_without_exception_text(
    tmp_path: Path,
) -> None:
    thread_id = new_evidence_id("thread")
    ledger = ExperimentLedger.create(
        tmp_path / "attempt.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": thread_id},
    )
    policy = ExperimentPolicy(
        benchmark_id="forge-cpp-pilot-v1",
        manifest_sha256="1" * 64,
        case_id="fmt",
        condition="baseline",
        repetition=1,
        expected_repo_url="https://github.com/fmtlib/fmt.git",
        expected_commit_sha="2" * 40,
        expected_build_system="cmake",
        compile_image="autocompiler:gcc13",
        image_id=f"sha256:{'3' * 64}",
        model_name="gpt-5.6-sol",
        endpoint="https://example.invalid/v1",
        credential_env="OpenAI_AK",
        request_timeout_seconds=120,
        model_max_retries=0,
        compiler_max_turns=36,
        subagent_timeout_seconds=180,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
    )
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    request = SimpleNamespace(
        runtime=SimpleNamespace(context={"thread_id": thread_id, "agent_name": "compiler"}),
        model=SimpleNamespace(model_name=policy.model_name, base_url=policy.endpoint),
    )
    sentinel = "provider-secret-sentinel-that-must-not-be-persisted"

    def handler(_request) -> AIMessage:
        raise FakeError(f"rate limited: {sentinel}", status_code=429)

    try:
        result = LLMErrorHandlingMiddleware().wrap_model_call(request, handler)
    finally:
        deactivate_experiment(thread_id)

    assert isinstance(result, AIMessage)
    events = ledger.read()
    assert [event["event"] for event in events] == [
        "experiment.started",
        "model.request_started",
        "model.request_failed",
        "failure.recorded",
    ]
    assert events[1]["payload"]["role"] == "compiler"
    assert events[1]["payload"]["max_attempts"] == 1
    assert events[2]["payload"]["classification"] == "rate_limited"
    assert events[2]["payload"]["retry_exhausted"] is True
    assert events[3]["payload"]["domain"] == "model_endpoint"
    assert sentinel not in ledger.path.read_text(encoding="utf-8")


def test_attempt_budget_rejects_provider_before_handler(
    tmp_path: Path,
) -> None:
    thread_id = new_evidence_id("thread")
    ledger = ExperimentLedger.create(
        tmp_path / "attempt-budget.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"thread_id": thread_id},
    )
    policy = ExperimentPolicy(
        benchmark_id="forge-cpp-pilot-v1",
        manifest_sha256="1" * 64,
        case_id="fmt",
        condition="baseline",
        repetition=1,
        expected_repo_url="https://github.com/fmtlib/fmt.git",
        expected_commit_sha="2" * 40,
        expected_build_system="cmake",
        compile_image="autocompiler:gcc13",
        image_id=f"sha256:{'3' * 64}",
        model_name="gpt-5.6-sol",
        endpoint="https://example.invalid/v1",
        credential_env="OpenAI_AK",
        request_timeout_seconds=120,
        model_max_retries=0,
        compiler_max_turns=36,
        subagent_timeout_seconds=180,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
    )
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
        attempt_budget=ExperimentAttemptBudget(
            total_wall_clock_seconds=60,
            cleanup_reserve_seconds=10,
            max_compiler_invocations=2,
            max_model_requests=1,
        ),
    )
    request = SimpleNamespace(
        runtime=SimpleNamespace(context={"thread_id": thread_id, "agent_name": "lead"}),
        model=SimpleNamespace(model_name=policy.model_name, base_url=policy.endpoint),
    )
    handler_calls = 0

    def handler(_request) -> AIMessage:
        nonlocal handler_calls
        handler_calls += 1
        return AIMessage(content="ok")

    middleware = LLMErrorHandlingMiddleware()
    try:
        assert middleware.wrap_model_call(request, handler).content == "ok"
        with pytest.raises(AttemptBudgetExceeded):
            middleware.wrap_model_call(request, handler)
    finally:
        deactivate_experiment(thread_id)

    assert handler_calls == 1
    checkpoints = [event["payload"] for event in ledger.read() if event["event"] == "attempt.budget_checkpoint"]
    assert [payload["allowed"] for payload in checkpoints] == [True, False]
