from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, tool

from deerflow.compile.evidence import ExperimentLedger, new_evidence_id
from deerflow.compile.schemas import VerificationResult

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_checkpoint_primary_canary.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-authorized.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_checkpoint_primary_canary_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


canary = _load_module()


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


class ReachabilityModel:
    def invoke(self, prompt: str) -> AIMessage:
        assert prompt == "Reply with exactly CANARY_OK and nothing else."
        return AIMessage(
            content="CANARY_OK",
            response_metadata={"model_name": "deepseek-v4-flash"},
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 12,
            },
        )


class SubmitModel(BaseChatModel):
    model_name: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "checkpoint-primary-fake"

    def bind_tools(
        self,
        tools: list[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.calls += 1
        if self.calls > 1:
            raise AssertionError("terminal submit 后不应再次调用 fake model")
        response = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "submit_build_result",
                    "args": {},
                    "id": "checkpoint-primary-submit",
                    "type": "tool_call",
                }
            ],
            response_metadata={"model_name": self.model_name},
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 10,
                "total_tokens": 110,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=response)])


def test_authorized_manifest_and_frozen_artifacts_are_valid() -> None:
    manifest = _manifest()
    assert canary.validate_manifest(manifest) == manifest
    canary.verify_frozen_artifacts(manifest, REPO_ROOT)
    assert manifest["scope"]["pilot_collection_authorized"] is False
    assert manifest["budget"]["stage_maximum_tokens"] == 245_000
    assert manifest["continuation"]["arm_order"] == ["baseline", "treatment"]


def test_manifest_rejects_pilot_or_retry_expansion() -> None:
    manifest = _manifest()
    manifest["scope"]["pilot_collection_authorized"] = True
    with pytest.raises(canary.CanaryError, match="授权范围"):
        canary.validate_manifest(manifest)

    manifest = _manifest()
    manifest["provider"]["max_retries"] = 1
    with pytest.raises(canary.CanaryError, match="provider"):
        canary.validate_manifest(manifest)


def test_release_identity_requires_clean_main_at_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    monkeypatch.setattr(canary, "verify_frozen_artifacts", lambda *_args: None)
    values = {
        ("branch", "--show-current"): "research/149-checkpoint-primary-canary",
        ("rev-parse", "HEAD"): "a" * 40,
        ("rev-parse", "origin/main"): "a" * 40,
        ("status", "--porcelain", "--untracked-files=normal"): "",
    }
    monkeypatch.setattr(canary, "_git", lambda _root, *arguments: values[arguments])
    with pytest.raises(canary.CanaryError, match="main"):
        canary.require_release_identity(manifest, REPO_ROOT)


def test_reachability_is_one_shot_and_records_no_response_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    monkeypatch.setattr(
        canary,
        "require_release_identity",
        lambda *_args: {
            "branch": "main",
            "revision": "a" * 40,
            "origin_main": "a" * 40,
        },
    )
    monkeypatch.setattr(canary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(canary, "require_authorized_output_dir", lambda *_args: None)
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "wifi")
    result = canary.run_reachability(
        manifest,
        output_dir=tmp_path,
        model_factory=lambda _provider: ReachabilityModel(),
    )
    assert result["passed"] is True
    assert result["request_count"] == 1
    assert result["actual_model"] == "deepseek-v4-flash"
    assert result["recorded_tokens"] == 12
    report_text = (tmp_path / "reports" / "reachability.json").read_text(encoding="utf-8")
    assert "CANARY_OK" not in report_text
    with pytest.raises(canary.CanaryError, match="已被消耗"):
        canary.run_reachability(
            manifest,
            output_dir=tmp_path,
            model_factory=lambda _provider: ReachabilityModel(),
        )


def test_reachability_failure_consumes_attempt_and_stops_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    release = {
        "branch": "main",
        "revision": "b" * 40,
        "origin_main": "b" * 40,
    }
    monkeypatch.setattr(canary, "require_release_identity", lambda *_args: release)
    monkeypatch.setattr(canary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(canary, "require_authorized_output_dir", lambda *_args: None)
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "mobile_hotspot")

    class WrongModel:
        def invoke(self, _prompt: str) -> AIMessage:
            return AIMessage(
                content="wrong",
                response_metadata={"model_name": "deepseek-v4-flash"},
                usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            )

    with pytest.raises(canary.CanaryError, match="reachability"):
        canary.run_reachability(
            manifest,
            output_dir=tmp_path,
            model_factory=lambda _provider: WrongModel(),
        )
    marker = json.loads((tmp_path / "markers" / canary.REACHABILITY_MARKER).read_text(encoding="utf-8"))
    assert marker["status"] == "failed"
    with pytest.raises(canary.CanaryError, match="未通过"):
        canary.require_passed_reachability(manifest, tmp_path, release["revision"])


def test_host_snapshot_root_translates_compose_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOST_PROJECT_ROOT", "/home/yiwei/Forge-AutoCompiler")
    assert canary.host_snapshot_root(Path("/workspace/.compile-sessions/benchmark-evidence/checkpoint/capture")) == "/home/yiwei/Forge-AutoCompiler/.compile-sessions/benchmark-evidence/checkpoint/capture"
    with pytest.raises(canary.CanaryError, match="共享"):
        canary.host_snapshot_root(Path("/tmp/checkpoint"))


def test_provider_model_applies_frozen_timeout_and_restores_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deerflow import config as config_module
    from deerflow.models import factory as factory_module

    provider = _manifest()["provider"]

    class FakeConfig:
        model = "deepseek-v4-flash"
        base_url = "https://api.deepseek.com"
        request_timeout = 30.0
        max_retries = 3

        def model_dump(self, *, exclude_none: bool) -> dict[str, Any]:
            assert exclude_none is True
            return {
                "model": self.model,
                "base_url": self.base_url,
                "request_timeout": self.request_timeout,
                "max_retries": self.max_retries,
            }

    configured = FakeConfig()
    observed: list[tuple[float, int]] = []

    def fake_create_chat_model(**_kwargs: Any) -> SimpleNamespace:
        observed.append((configured.request_timeout, configured.max_retries))
        return SimpleNamespace(
            request_timeout=configured.request_timeout,
            max_retries=configured.max_retries,
        )

    monkeypatch.setattr(
        config_module,
        "get_app_config",
        lambda: SimpleNamespace(get_model_config=lambda _name: configured),
    )
    monkeypatch.setattr(factory_module, "create_chat_model", fake_create_chat_model)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-placeholder")
    model = canary._create_provider_model(provider)
    assert model.request_timeout == 300.0
    assert model.max_retries == 0
    assert observed == [(300.0, 0)]
    assert configured.request_timeout == 30.0
    assert configured.max_retries == 3


def test_fake_model_continuation_records_actual_model_and_terminal_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from deerflow.compile import operations
    from deerflow.tools import bound_compile_tools

    manifest = _manifest()
    session = SimpleNamespace(
        session_id="baseline-session-test",
        thread_id="baseline-thread-test",
        image_id="sha256:" + "1" * 64,
        status="verification_failed",
        verification=VerificationResult(status="failed"),
        replay_attempts=[],
    )

    @tool
    def run_container_bash(
        command: str,
        timeout_seconds: int = 300,
        workdir: str | None = None,
        command_role: str = "other",
    ) -> str:
        """执行 fake-model rehearsal 命令。"""
        del command, timeout_seconds, workdir, command_role
        return "unused"

    @tool
    def submit_build_result() -> str:
        """提交已经恢复的 controlled artifact。"""
        session.status = "verified"
        session.verification = VerificationResult(status="passed", artifact_count=1, failed_checks=0)
        session.replay_attempts = [SimpleNamespace(status="passed")]
        return json.dumps(
            {
                "status": "passed",
                "message": "Build artifacts and clean replay accepted.",
                "candidate_status": "passed",
                "replay_status": "passed",
                "artifacts": [{"path": "accumulate_examples"}],
            }
        )

    monkeypatch.setattr(
        bound_compile_tools,
        "get_bound_compile_tools",
        lambda _session: [run_container_bash, submit_build_result],
    )
    monkeypatch.setattr(
        operations,
        "get_compile_services",
        lambda: SimpleNamespace(manager=SimpleNamespace(load_session=lambda _session_id, _thread_id: session)),
    )
    ledger = ExperimentLedger.create(
        tmp_path / "baseline.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("mechanism_attempt"),
        context={"scope": "fake-model-rehearsal"},
    )
    lifecycle_arm = SimpleNamespace(session=session, message_config={})
    message_state = {
        "messages": [
            HumanMessage(content="repair and submit"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "submit_build_result",
                        "args": {},
                        "id": "neutral-submit",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                content=json.dumps(
                    {
                        "status": "failed",
                        "candidate_status": "failed",
                    }
                ),
                tool_call_id="neutral-submit",
                name="submit_build_result",
            ),
        ]
    }
    result = asyncio.run(
        canary.run_arm_continuation(
            manifest,
            arm="baseline",
            lifecycle_arm=lifecycle_arm,
            message_state=message_state,
            ledger=ledger,
            model_factory=lambda _provider, _thread_id: SubmitModel(),
        )
    )
    assert result["status"] == "passed"
    assert result["model_requests"] == 1
    assert result["recorded_tokens"] == 110
    assert result["actual_model"] == "deepseek-v4-flash"
    assert ledger.read()[-1]["event"] == "experiment.completed"


def test_arm_evidence_rejects_missing_actual_model_or_token_overrun(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    session = SimpleNamespace(
        status="verified",
        verification=VerificationResult(status="passed"),
        replay_attempts=[SimpleNamespace(status="passed")],
    )
    ledger = ExperimentLedger.create(
        tmp_path / "invalid.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("mechanism_attempt"),
        context={"scope": "invalid-evidence"},
    )
    call_id = new_evidence_id("model_call")
    request_id = new_evidence_id("model_request")
    ledger.append(
        "model.request_started",
        {
            "model_call_id": call_id,
            "model_request_id": request_id,
            "role": "compiler",
            "attempt": 1,
            "max_attempts": 1,
            "configured_model": "deepseek-v4-flash",
            "observed_endpoint": "https://api.deepseek.com",
            "request_timeout_seconds": 300,
            "provider_max_retries": 0,
        },
    )
    ledger.append(
        "model.request_completed",
        {
            "model_call_id": call_id,
            "model_request_id": request_id,
            "attempt": 1,
            "latency_seconds": 1.0,
            "status_code": None,
            "actual_model": None,
            "token_usage": {
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 120001,
            },
        },
    )
    with pytest.raises(canary.CanaryError, match="actual model"):
        canary.validate_arm_evidence(manifest, arm="baseline", ledger=ledger, session=session)
