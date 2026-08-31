"""Issue #245 independent replication lifecycle 的 opt-in 零 provider Docker 门禁。"""

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
SCRIPTS = REPO_ROOT / "scripts"
GATE_PATH = SCRIPTS / "forge_opaque_provenance_confirmatory_replication_lifecycle_gate.py"
DOCKER_ENABLED = os.getenv("FORGE_RUN_OPAQUE_CONFIRMATORY_REPLICATION_LIFECYCLE_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_OPAQUE_CONFIRMATORY_REPLICATION_LIFECYCLE_DOCKER=1 inside Forge Compose",
)


def _load_gate():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("forge_confirmatory_replication_lifecycle_gate_docker_test", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


class MakeRepairModel(BaseChatModel):
    model_name: str = gate.ZERO_PROVIDER_MODEL
    base_url: str = gate.ZERO_PROVIDER_ENDPOINT
    arm: str
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "opaque-confirmatory-replication-lifecycle-zero-provider"

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
        if self.arm == "baseline":
            tool_call = {"name": "submit_build_result", "args": {}, "id": "baseline-submit", "type": "tool_call"} if self.calls == 1 else None
        else:
            actions = (
                {
                    "name": "run_container_bash",
                    "args": {
                        "command": "make library -j2",
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
                        "command": "cp /workspace/repo/libsqlparser.so /artifacts/libsqlparser.so",
                        "timeout_seconds": 60,
                        "workdir": "/workspace/repo",
                        "command_role": "artifact_stage",
                    },
                    "id": "treatment-stage",
                    "type": "tool_call",
                },
                {"name": "submit_build_result", "args": {}, "id": "treatment-submit", "type": "tool_call"},
            )
            tool_call = actions[self.calls - 1] if self.calls <= len(actions) else None
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="" if tool_call else "Done.",
                        tool_calls=[] if tool_call is None else [tool_call],
                        response_metadata={"model_name": self.model_name},
                        usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                    )
                )
            ]
        )


def _services(monkeypatch: pytest.MonkeyPatch) -> tuple[Paths, CompileDockerRuntime, list[Any]]:
    paths = Paths()
    manager = CompileSessionManager(paths=paths, default_image=gate.repair.v1.COMPILE_IMAGE)
    created_sessions: list[Any] = []
    original_create_session = manager.create_session

    def create_session(*args: Any, **kwargs: Any) -> Any:
        session = original_create_session(*args, **kwargs)
        created_sessions.append(session)
        return session

    manager.create_session = create_session  # type: ignore[method-assign]
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    return paths, runtime, created_sessions


def _cleanup(runtime: CompileDockerRuntime, sessions: list[Any], output_dir: Path) -> None:
    for session in reversed(sessions):
        runtime.stop_and_remove_container(session)
        session_dir = Path(session.metadata_path).parent
        shutil.rmtree(session_dir, ignore_errors=True)
        try:
            session_dir.parent.rmdir()
        except OSError:
            pass
    shutil.rmtree(output_dir, ignore_errors=True)


def _preflight(manifest: dict[str, Any]) -> None:
    gate.repair.v1.primary.require_compose_dood()
    gate.repair.v1.require_zero_managed_containers()
    assert gate.require_empty_formal_evidence(manifest) == []


def test_cmake_capture_before_commit_failure_cleans_only_created_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = gate.load_candidate(REPO_ROOT)
    _preflight(manifest)
    paths, runtime, sessions = _services(monkeypatch)
    output_dir = paths.compile_sessions_dir / f"issue-245-replication-cmake-failure-{uuid.uuid4().hex[:12]}"
    pair = next(item for item in manifest["schedule"]["pairs"] if item["case_id"] == "args" and item["replicate"] == 1)

    def fail_before_commit(_history: Any) -> str:
        raise RuntimeError("replication capture evidence failed before commit")

    monkeypatch.setattr(gate.repair.lifecycle.cmake_reference, "command_history_sha256", fail_before_commit)
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "wifi")
    try:
        with asyncio.Runner() as async_runner:
            with pytest.raises(RuntimeError, match="before commit"):
                gate.execute_zero_provider_pair(
                    manifest,
                    pair,
                    output_dir,
                    async_runner,
                    {"branch": "main", "revision": "e" * 40, "origin_main": "e" * 40},
                    model_factory=lambda *_args: pytest.fail("capture failure 不得调用 fake model"),
                    repo_root=REPO_ROOT,
                )
        assert sessions
        gate.repair.v1.require_zero_managed_containers()
        assert gate.require_empty_formal_evidence(manifest) == []
    finally:
        _cleanup(runtime, sessions, output_dir)


def test_make_pair_reaches_checkpoint_p2_replay_finalize_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = gate.load_candidate(REPO_ROOT)
    _preflight(manifest)
    paths, runtime, sessions = _services(monkeypatch)
    output_dir = paths.compile_sessions_dir / f"issue-245-replication-make-success-{uuid.uuid4().hex[:12]}"
    pair = next(item for item in manifest["schedule"]["pairs"] if item["case_id"] == "sql-parser-shared" and item["replicate"] == 1)
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "wifi")

    def model_factory(provider: dict[str, Any], thread_id: str) -> Any:
        assert provider["endpoint"] == gate.ZERO_PROVIDER_ENDPOINT
        assert provider["credential_env"] == gate.ZERO_PROVIDER_CREDENTIAL_ENV
        arm = "treatment" if thread_id.startswith("treatment-") else "baseline"
        return MakeRepairModel(arm=arm)

    try:
        with asyncio.Runner() as async_runner:
            result = gate.execute_zero_provider_pair(
                manifest,
                pair,
                output_dir,
                async_runner,
                {"branch": "main", "revision": "e" * 40, "origin_main": "e" * 40},
                model_factory=model_factory,
                repo_root=REPO_ROOT,
            )
        assert result["primary_mechanism_eligible"] is True
        assert result["provenance_conversion"] == {"baseline": False, "treatment": True}, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        assert result["paired_conversion_delta"] == 1
        assert result["recorded_tokens"] == 0
        assert result["arms"]["treatment"]["verification_outcome"]["status"] == "passed"
        assert result["arms"]["treatment"]["p2"]["status"] == "proven"
        assert result["cleanup_succeeded"] is True
        gate.repair.v1.require_zero_managed_containers()
        assert gate.require_empty_formal_evidence(manifest) == []
    finally:
        _cleanup(runtime, sessions, output_dir)
