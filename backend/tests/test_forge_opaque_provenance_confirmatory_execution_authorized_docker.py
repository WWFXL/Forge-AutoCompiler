"""Issue #237 authorized runner 的 opt-in 零 provider Docker 门禁。"""

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
SCRIPT_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_confirmatory_execution_authorized_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-execution-authorized.json"
DOCKER_ENABLED = os.getenv("FORGE_RUN_OPAQUE_CONFIRMATORY_AUTHORIZED_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_OPAQUE_CONFIRMATORY_AUTHORIZED_DOCKER=1 inside Forge Compose",
)


def _load_module():
    scripts = REPO_ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(
        "forge_confirmatory_execution_authorized_docker_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_module()


class ProvenanceRepairModel(BaseChatModel):
    model_name: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    arm: str
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "opaque-confirmatory-authorized-docker-fake"

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
        tool_call: dict[str, Any] | None
        if self.arm == "baseline":
            tool_call = (
                {
                    "name": "submit_build_result",
                    "args": {},
                    "id": "baseline-submit",
                    "type": "tool_call",
                }
                if self.calls == 1
                else None
            )
        else:
            actions = (
                {
                    "name": "run_container_bash",
                    "args": {
                        "command": "cmake --build /workspace/repo/build --target gitlike -j2",
                        "timeout_seconds": 300,
                        "workdir": "/workspace/repo",
                        "command_role": "build",
                    },
                    "id": "treatment-build",
                    "type": "tool_call",
                },
                {
                    "name": "run_container_bash",
                    "args": {
                        "command": "cp /workspace/repo/build/gitlike /artifacts/gitlike",
                        "timeout_seconds": 60,
                        "workdir": "/workspace/repo",
                        "command_role": "artifact_stage",
                    },
                    "id": "treatment-stage",
                    "type": "tool_call",
                },
                {
                    "name": "submit_build_result",
                    "args": {},
                    "id": "treatment-submit",
                    "type": "tool_call",
                },
            )
            tool_call = actions[self.calls - 1] if self.calls <= len(actions) else None
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="" if tool_call else "Done.",
                        tool_calls=[] if tool_call is None else [tool_call],
                        response_metadata={"model_name": self.model_name},
                        usage_metadata={
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "total_tokens": 120,
                        },
                    )
                )
            ]
        )


def test_authorized_runner_reuses_real_checkpoint_p2_replay_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner.primary.require_compose_dood()
    runner.require_zero_managed_containers()
    paths = Paths()
    output_dir = paths.compile_sessions_dir / f"issue-237-confirmatory-docker-{uuid.uuid4().hex[:12]}"
    created_session_dirs: list[Path] = []
    manager = CompileSessionManager(paths=paths, default_image=runner.COMPILE_IMAGE)
    original_create_session = manager.create_session

    def create_session(*args: Any, **kwargs: Any):
        session = original_create_session(*args, **kwargs)
        created_session_dirs.append(Path(session.metadata_path).parent)
        return session

    manager.create_session = create_session  # type: ignore[method-assign]
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=runtime),
    )
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "wifi")
    manifest = runner.protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    pair = next(item for item in manifest["schedule"]["pairs"] if item["case_id"] == "args" and item["replicate"] == 1)
    release = {
        "branch": "main",
        "revision": "e" * 40,
        "origin_main": "e" * 40,
    }
    reachability = {"recorded_tokens": 17}

    def model_factory(_provider: dict[str, Any], thread_id: str) -> Any:
        arm = "treatment" if thread_id.startswith("treatment-") else "baseline"
        return ProvenanceRepairModel(arm=arm)

    try:
        with asyncio.Runner() as async_runner:
            result = runner.execute_real_pair(
                manifest,
                pair,
                output_dir,
                async_runner,
                reachability,
                release,
                model_factory=model_factory,
            )
        assert result["terminal"] == "model_behavior_outcome"
        assert result["primary_mechanism_eligible"] is True
        assert result["provenance_conversion"] == {
            "baseline": False,
            "treatment": True,
        }, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        assert result["paired_conversion_delta"] == 1
        assert result["arms"]["treatment"]["verification_outcome"]["status"] == "passed"
        assert result["arms"]["treatment"]["p2"]["status"] == "proven"
        assert result["arms"]["baseline"]["p2"]["status"] == "unproven"
        runner.require_zero_managed_containers()
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
