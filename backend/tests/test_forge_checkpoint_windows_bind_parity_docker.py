"""Issue #151 的 opt-in Compose + Windows bind 零 provider parity gate。"""

from __future__ import annotations

import importlib.util
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
SCRIPTS_ROOT = REPO_ROOT / "scripts"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-authorized.json"
DOCKER_ENABLED = os.getenv("FORGE_RUN_CHECKPOINT_WINDOWS_BIND_PARITY") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_CHECKPOINT_WINDOWS_BIND_PARITY=1 inside Forge Compose",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


primary = _load_module(
    "forge_checkpoint_primary_canary_windows_bind_test",
    SCRIPTS_ROOT / "forge_checkpoint_primary_canary.py",
)
layout = _load_module(
    "forge_checkpoint_windows_build_layout_docker_test",
    SCRIPTS_ROOT / "forge_checkpoint_windows_build_layout.py",
)


class RestoreAndSubmitModel(BaseChatModel):
    model_name: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "checkpoint-windows-bind-fake"

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
                                    "command": ("cp .forge-cmake-build/accumulate_examples /artifacts/accumulate_examples"),
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
                )
            ]
        )


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


def test_safe_layout_matches_real_compose_windows_bind_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary.require_compose_dood()
    paths = Paths()
    shared_root = paths.compile_sessions_dir
    run_suffix = uuid.uuid4().hex[:12]
    output_dir = shared_root / f"issue-151-parity-{run_suffix}"
    probe_dir = shared_root / f"issue-151-casefold-probe-{run_suffix}"
    created_session_dirs: list[Path] = []
    manager = CompileSessionManager(paths=paths, default_image=primary.COMPILE_IMAGE)
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
    release = {
        "branch": "main",
        "revision": "d" * 40,
        "origin_main": "d" * 40,
    }
    monkeypatch.setattr(primary, "require_release_identity", lambda *_args: release)
    monkeypatch.setattr(primary, "require_authorized_output_dir", lambda *_args: None)
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "wifi")

    try:
        probe_dir.mkdir(parents=True)
        tracked_build = probe_dir / "BUILD"
        tracked_build.write_text("tracked Bazel file\n", encoding="utf-8")
        legacy_binary_dir = probe_dir / "build"
        assert legacy_binary_dir.is_file()
        with pytest.raises(FileExistsError):
            legacy_binary_dir.mkdir()

        manifest = primary.load_manifest(MANIFEST_PATH)
        with layout.use_windows_safe_build_layout(primary):
            primary.run_reachability(
                manifest,
                output_dir=output_dir,
                model_factory=lambda _provider: ReachabilityModel(),
            )
            result = primary.run_controlled_pair(
                manifest,
                output_dir=output_dir,
                model_factory=lambda _provider, _thread_id: RestoreAndSubmitModel(),
            )

        assert result["passed"] is True
        assert result["complete_pair"] is True
        assert result["cleanup_succeeded"] is True
        assert result["pilot_denominator_contribution"] == 0
        assert [arm["recorded_tokens"] for arm in result["arms"]] == [120, 120]
        assert result["stage_recorded_tokens"] == 252
    finally:
        for session_dir in reversed(created_session_dirs):
            shutil.rmtree(session_dir, ignore_errors=True)
            thread_dir = session_dir.parent
            try:
                thread_dir.rmdir()
            except OSError:
                pass
        shutil.rmtree(output_dir, ignore_errors=True)
        shutil.rmtree(probe_dir, ignore_errors=True)
