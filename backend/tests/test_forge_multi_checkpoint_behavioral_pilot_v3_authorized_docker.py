"""Issue #172 authorized runner 的 opt-in Make fake-model Docker 门禁。"""

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
SCRIPT_PATH = REPO_ROOT / "scripts/forge_multi_checkpoint_behavioral_pilot_v3_authorized_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-verifier-multi-checkpoint-behavioral-pilot-v3-authorized.json"
DOCKER_ENABLED = os.getenv("FORGE_RUN_MULTI_CHECKPOINT_BEHAVIORAL_V3_AUTHORIZED_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_MULTI_CHECKPOINT_BEHAVIORAL_V3_AUTHORIZED_DOCKER=1 inside Forge Compose",
)


def _load_module():
    scripts = REPO_ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("forge_multi_checkpoint_behavioral_v3_authorized_docker_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_module()


class RestoreJanetArtifactModel(BaseChatModel):
    model_name: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "multi-checkpoint-behavioral-v3-authorized-docker-fake"

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
                                    "command": "cp build/libjanet.a /artifacts/libjanet.a",
                                    "timeout_seconds": 60,
                                    "workdir": "/workspace/repo",
                                    "command_role": "artifact_stage",
                                },
                                "id": "restore-janet-artifact",
                                "type": "tool_call",
                            }
                        ],
                        response_metadata={"model_name": self.model_name},
                        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                    )
                )
            ]
        )


def test_authorized_runner_maps_janet_through_real_verifier_replay_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    runner.primary.require_compose_dood()
    paths = Paths()
    output_dir = paths.compile_sessions_dir / f"issue-172-janet-{uuid.uuid4().hex[:12]}"
    created_session_dirs: list[Path] = []
    manager = CompileSessionManager(paths=paths, default_image=runner.COMPILE_IMAGE)
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
    manifest = runner.protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    pair = next(item for item in manifest["schedule"] if item["case_id"] == "janet")

    try:
        with asyncio.Runner() as async_runner:
            result = runner.execute_real_pair(
                manifest,
                pair,
                output_dir,
                async_runner,
                model_factory=lambda _provider, _thread_id: RestoreJanetArtifactModel(),
            )
        assert result["status"] == "observed"
        assert result["case_id"] == "janet"
        assert result["build_system"] == "make"
        assert result["primary_mechanism_eligible"] is True
        assert result["repair_success"] == {"baseline": True, "treatment": True}
        assert all(item["verification_outcome"]["status"] == "passed" for item in result["arms"].values())
    finally:
        for session_dir in reversed(created_session_dirs):
            shutil.rmtree(session_dir, ignore_errors=True)
            try:
                session_dir.parent.rmdir()
            except OSError:
                pass
        shutil.rmtree(output_dir, ignore_errors=True)


def test_manifest_file_is_json() -> None:
    assert isinstance(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")), dict)
