"""Issue #165 v2 适配器的 opt-in Compose/DooD 零 provider gate。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import sys
import uuid
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

REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_checkpoint_behavioral_pilot_v2_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-behavioral-pilot-v2.json"
DOCKER_ENABLED = os.getenv("FORGE_RUN_CHECKPOINT_BEHAVIORAL_V2_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_CHECKPOINT_BEHAVIORAL_V2_DOCKER=1 inside Forge Compose",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_checkpoint_behavioral_pilot_v2_docker_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_module()


class RestoreAndSubmitModel(BaseChatModel):
    model_name: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "checkpoint-behavior-v2-docker-fake"

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
            raise AssertionError("successful automatic submit 后不应再次调用 fake model")
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "run_container_bash",
                                "args": {
                                    "command": "cp .forge-cmake-build/accumulate_examples /artifacts/accumulate_examples",
                                    "timeout_seconds": 60,
                                    "workdir": "/workspace/repo",
                                    "command_role": "artifact_stage",
                                },
                                "id": "restore-controlled-artifact",
                                "type": "tool_call",
                            }
                        ],
                        response_metadata={"model_name": self.model_name},
                        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                    )
                )
            ]
        )


def test_v2_adapter_runs_real_checkpoint_verifier_replay_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    runner.primary.require_compose_dood()
    paths = Paths()
    output_dir = paths.compile_sessions_dir / f"issue-165-v2-docker-{uuid.uuid4().hex[:12]}"
    created_session_dirs: list[Path] = []
    manager = CompileSessionManager(paths=paths, default_image=runner.primary.COMPILE_IMAGE)
    original_create_session = manager.create_session

    def create_session(*args: Any, **kwargs: Any):
        session = original_create_session(*args, **kwargs)
        created_session_dirs.append(Path(session.metadata_path).parent)
        return session

    manager.create_session = create_session  # type: ignore[method-assign]
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    monkeypatch.setattr(
        runner,
        "require_release_identity",
        lambda *_args: {"branch": "main", "revision": "e" * 40, "origin_main": "e" * 40},
    )
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "wifi")
    manifest = runner.protocol.validate_manifest(json_load(MANIFEST_PATH))
    pair = manifest["schedule"][0]

    try:
        with asyncio.Runner() as async_runner:
            result = runner.execute_real_pair(
                manifest,
                pair,
                output_dir,
                async_runner,
                model_factory=lambda _provider, _thread_id: RestoreAndSubmitModel(),
            )
        assert result["status"] == "observed"
        assert result["primary_mechanism_eligible"] is True
        assert result["repair_success"] == {"baseline": True, "treatment": True}
        assert all(item["infrastructure"]["status"] == "valid" for item in result["arms"].values())
        assert all(item["verification_outcome"]["status"] == "passed" for item in result["arms"].values())
    finally:
        for session_dir in reversed(created_session_dirs):
            shutil.rmtree(session_dir, ignore_errors=True)
            try:
                session_dir.parent.rmdir()
            except OSError:
                pass
        shutil.rmtree(output_dir, ignore_errors=True)


def json_load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
