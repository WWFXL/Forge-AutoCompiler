"""Stage C v7 authorized runner 的 opt-in 零 Provider Docker lifecycle 门禁。"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from deerflow.compile import operations
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import CompileOperationsServices
from deerflow.config.paths import Paths
from deerflow.models import factory as model_factory

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_stage_c_v7_prefreeze_canary_authorized_protocol as protocol  # noqa: E402
import forge_stage_c_v7_prefreeze_canary_authorized_runner as runner  # noqa: E402

DOCKER_ENABLED = os.getenv("FORGE_RUN_STAGE_C_V7_AUTHORIZED_DOCKER") == "1"
COMMAND_ID_PATTERN = re.compile(r"^command_id=(command_[0-9a-f]+)$", re.MULTILINE)
COMMAND_ROLE_PATTERN = re.compile(r"^command_role=([a-z_]+)$", re.MULTILINE)

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_STAGE_C_V7_AUTHORIZED_DOCKER=1 to run the authorized Stage C v7 Docker gate",
)

FIXTURE_FILES = {
    "Makefile": "CC ?= cc\nAR ?= ar\nCFLAGS ?= -O2\nlibsample.a: lib.o\n\t$(AR) rcs $@ $^\nlib.o: lib.c include/sample/api.h include/sample/detail.h\n\t$(CC) $(CFLAGS) -Iinclude -c -o $@ lib.c\n",
    "lib.c": '#include "sample/api.h"\nint sample_add(int left, int right) { return left + right + SAMPLE_OFFSET; }\n',
    "include/sample/api.h": '#ifndef SAMPLE_API_H\n#define SAMPLE_API_H\n#include "detail.h"\nint sample_add(int left, int right);\n#endif\n',
    "include/sample/detail.h": "#ifndef SAMPLE_DETAIL_H\n#define SAMPLE_DETAIL_H\n#define SAMPLE_OFFSET 0\n#endif\n",
}


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=30)
    return completed.stdout.strip()


@pytest.fixture(scope="module")
def fixture_repository(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, str, str]]:
    root = tmp_path_factory.mktemp("stage-c-v7-authorized-docker")
    source = root / "source"
    bare = root / "fixture.git"
    source.mkdir()
    for relative_path, content in FIXTURE_FILES.items():
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git("init", "--quiet", cwd=source)
    _git("config", "user.name", "Forge Stage C v7 Gate", cwd=source)
    _git("config", "user.email", "stage-c-v7@example.invalid", cwd=source)
    _git("add", ".", cwd=source)
    _git("commit", "--quiet", "-m", "stage c v7 fixture", cwd=source)
    commit_sha = _git("rev-parse", "HEAD", cwd=source)
    source_archive = root / "source.tar"
    _git("archive", "--format=tar", "--output", str(source_archive), "HEAD", cwd=source)
    source_snapshot_sha256 = hashlib.sha256(source_archive.read_bytes()).hexdigest()
    _git("clone", "--quiet", "--bare", str(source), str(bare), cwd=root)
    _git("update-server-info", cwd=bare)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    daemon = subprocess.Popen(
        ["git", "daemon", "--reuseaddr", "--export-all", f"--base-path={root}", "--listen=0.0.0.0", f"--port={port}", str(root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 5
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            if daemon.poll() is not None or time.monotonic() >= deadline:
                daemon.terminate()
                raise RuntimeError("Stage C v7 fixture git daemon 启动失败")
            time.sleep(0.05)
    try:
        yield f"git://host.docker.internal:{port}/fixture.git", commit_sha, source_snapshot_sha256
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=5)


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
        usage_metadata={"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
    )


def _command_evidence(messages: Sequence[BaseMessage]) -> list[tuple[str, str]]:
    evidence: list[tuple[str, str]] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        content = message.content if isinstance(message.content, str) else json.dumps(message.content)
        command_id = COMMAND_ID_PATTERN.search(content)
        role = COMMAND_ROLE_PATTERN.search(content)
        if command_id is not None and role is not None:
            evidence.append((command_id.group(1), role.group(1)))
    return evidence


class DeterministicCanaryModel(BaseChatModel):
    calls: int = 0
    bind_kwargs: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "stage-c-v7-authorized-zero-provider"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice
        self.bind_kwargs.append(kwargs)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        if self.calls == 0:
            response = _tool_call(
                "run_container_bash",
                {"command": "make", "command_role": "build", "timeout_seconds": 300, "workdir": "/workspace/repo"},
                "build",
            )
        elif self.calls == 1:
            response = _tool_call(
                "run_container_bash",
                {
                    "command": "mkdir -p /artifacts/include/sample /artifacts/lib && cp include/sample/api.h include/sample/detail.h /artifacts/include/sample/ && cp libsample.a /artifacts/lib/libsample.a",
                    "command_role": "artifact_stage",
                    "timeout_seconds": 300,
                    "workdir": "/workspace/repo",
                },
                "stage",
            )
        else:
            evidence = _command_evidence(messages)
            supporting = [command_id for command_id, role in evidence if role == "build"]
            recipe = [command_id for command_id, role in evidence if role in {"build", "artifact_stage"}]
            response = _tool_call(
                "submit_candidate_v1",
                {
                    "candidate_id": "stage-c-v7-docker-candidate",
                    "build_system": "make",
                    "supporting_command_ids": supporting,
                    "artifact_paths": ["include/sample/api.h", "include/sample/detail.h", "lib/libsample.a"],
                    "target_mapping": {"sample-static-library": "lib/libsample.a"},
                    "recipe_command_ids": recipe,
                    "agent_summary": "Stage C v7 authorized 零 Provider Docker gate",
                    "known_limitations": [],
                },
                "submit",
            )
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def _assert_zero_managed_resources() -> None:
    for command in (
        ["docker", "ps", "-aq", "--filter", "label=deerflow.compile.managed=true"],
        ["docker", "ps", "-q", "--filter", "status=paused", "--filter", "label=deerflow.compile.managed=true"],
        ["docker", "images", "-q", "--filter", "label=deerflow.compile.managed=true"],
    ):
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""


@pytest.fixture(scope="module", autouse=True)
def require_docker_gate() -> Iterator[None]:
    if not DOCKER_ENABLED:
        yield
        return
    required = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "require-docker-runtime.sh")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if required.returncode != 0:
        pytest.fail(required.stderr.strip() or required.stdout.strip())
    manifest = protocol.load_manifest()
    image = subprocess.run(
        ["docker", "image", "inspect", manifest["environment"]["compile_image"]],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if image.returncode != 0:
        pytest.fail(f"缺少冻结镜像 {manifest['environment']['compile_image']}")
    _assert_zero_managed_resources()
    yield
    _assert_zero_managed_resources()


@pytest.fixture(autouse=True)
def forbid_provider_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("Docker gate 禁止创建 Provider-backed model")

    monkeypatch.setattr(model_factory, "create_chat_model", forbidden)


def _gate_manifest(repository_url: str, commit_sha: str, source_snapshot_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = copy.deepcopy(protocol.load_manifest())
    image_id = subprocess.run(
        ["docker", "image", "inspect", manifest["environment"]["compile_image"], "--format", "{{.Id}}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    manifest["environment"]["image_id"] = image_id
    task = {
        "task_id": "stage-c-v7-docker-fixture",
        "repository_url": repository_url,
        "commit_sha": commit_sha,
        "source_snapshot_sha256": source_snapshot_sha256,
        "build_system_capabilities": ["make"],
        "selected_build_system": "make",
        "qualification_receipt": {"receipt_sha256": "b" * 64},
        "target_contract": {
            "target_id": "sample-static-library",
            "artifact_types": ["support_file", "static_library"],
            "required_artifacts": ["include/sample/api.h", "include/sample/detail.h", "lib/libsample.a"],
        },
        "oracle": {
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <sample/api.h>\nint main(void){ return sample_add(2, 3) == 5 ? 0 : 1; }\n",
            "compile_argv": ["cc", "-std=c11", "-I/artifacts/include", "{source}", "/artifacts/lib/libsample.a", "-o", "{executable}"],
            "run_argv": ["{executable}"],
        },
    }
    attempt = {
        "sequence": 1,
        "task_id": task["task_id"],
        "attempt_id": "stage-c-v7-docker-fixture-b-canary",
        "canary_id": "stage-c-v7-docker-fixture-canary",
    }
    manifest["tasks"] = [task]
    manifest["schedule"]["attempts"] = [attempt]
    manifest["schedule"]["canary_attempt_count"] = 1
    return manifest, attempt


def _normalize_tree(path: Path, image: str) -> None:
    result = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{path}:/target", image, "sh", "-c", f"chown -R {os.getuid()}:{os.getgid()} /target && chmod -R u+rwX /target"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_authorized_runner_runtime_v3_evaluator_v4_and_cleanup(
    fixture_repository: tuple[str, str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_url, commit_sha, source_snapshot_sha256 = fixture_repository
    manifest, attempt = _gate_manifest(repository_url, commit_sha, source_snapshot_sha256)
    workspace = tmp_path / "workspace"
    paths = Paths(base_dir=tmp_path / ".deer-flow", workspace_root=workspace, host_workspace_root=str(workspace))
    manager = CompileSessionManager(paths=paths, default_image=manifest["environment"]["compile_image"])
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(operations, "_services", CompileOperationsServices(manager=manager, runtime=runtime))
    monkeypatch.setenv("COMPILE_RUNTIME_NO_PROXY", "host.docker.internal,127.0.0.1,localhost")
    model = DeterministicCanaryModel()

    try:
        result = asyncio.run(
            runner.execute_attempt(
                manifest,
                attempt,
                release_revision="c" * 40,
                output_dir=tmp_path / "evidence",
                model_factory=lambda _manifest, _thread_id: model,
            )
        )
    finally:
        _normalize_tree(tmp_path, manifest["environment"]["compile_image"])

    assert result["method"] == "forge-agent-workflow-node-v3"
    assert result["candidate_submitted"] is True
    assert result["strict_reproducible_build_success"] is True
    assert result["bitwise_reproducible"] is True
    assert result["canary_passed"] is True
    assert result["recorded_tokens"] == 36
    assert result["request_token_ledger"] == [
        {"request_sequence": 1, "input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
        {"request_sequence": 2, "input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
        {"request_sequence": 3, "input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
    ]
    assert result["cleanup_succeeded"] is True
    assert model.calls == 3
    assert model.bind_kwargs and model.bind_kwargs[-1]["parallel_tool_calls"] is False
    _assert_zero_managed_resources()
