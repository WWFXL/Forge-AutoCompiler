"""Issue #149 primary canary 的 opt-in Ubuntu 原生 Docker fake-model rehearsal。"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from deerflow.compile import operations
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices
from deerflow.config.paths import Paths

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_checkpoint_primary_canary.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-authorized.json"
DOCKER_ENABLED = os.getenv("FORGE_RUN_CHECKPOINT_PRIMARY_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_CHECKPOINT_PRIMARY_DOCKER=1 to run this rehearsal",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_checkpoint_primary_canary_docker_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


canary = _load_module()


class RestoreAndSubmitModel(BaseChatModel):
    model_name: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "checkpoint-primary-docker-fake"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
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
            raise AssertionError("successful automatic submit 后不应再次调用模型")
        response = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "run_container_bash",
                    "args": {
                        "command": "cp build/accumulate_examples /artifacts/accumulate_examples",
                        "timeout_seconds": 60,
                        "workdir": "/workspace/repo",
                        "command_role": "artifact_stage",
                    },
                    "id": "restore-controlled-artifact",
                    "type": "tool_call",
                }
            ],
            response_metadata={"model_name": self.model_name},
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=response)])


class ReachabilityModel:
    def invoke(self, _prompt: str) -> AIMessage:
        return AIMessage(
            content="CANARY_OK",
            response_metadata={"model_name": "deepseek-v4-flash"},
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 12,
            },
        )


def test_fake_model_controlled_pair_uses_real_checkpoint_verifier_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    paths = Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=workspace,
        host_workspace_root=str(workspace),
    )
    manager = CompileSessionManager(paths=paths, default_image=canary.COMPILE_IMAGE)
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=runtime),
    )
    release = {
        "branch": "main",
        "revision": "c" * 40,
        "origin_main": "c" * 40,
    }
    monkeypatch.setattr(canary, "require_release_identity", lambda *_args: release)
    monkeypatch.setattr(canary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(canary, "require_authorized_output_dir", lambda *_args: None)
    monkeypatch.setattr(canary, "host_snapshot_root", lambda path: str(path))
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "wifi")
    manifest = canary.load_manifest(MANIFEST_PATH)
    canary.run_reachability(
        manifest,
        output_dir=tmp_path,
        model_factory=lambda _provider: ReachabilityModel(),
    )
    result = canary.run_controlled_pair(
        manifest,
        output_dir=tmp_path,
        model_factory=lambda _provider, _thread_id: RestoreAndSubmitModel(),
    )
    assert result["passed"] is True
    assert result["complete_pair"] is True
    assert result["cleanup_succeeded"] is True
    assert result["pilot_denominator_contribution"] == 0
    assert [arm["recorded_tokens"] for arm in result["arms"]] == [120, 120]
    assert result["stage_recorded_tokens"] == 252
