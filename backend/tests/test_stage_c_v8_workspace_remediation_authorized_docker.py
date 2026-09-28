"""Stage C v8 authorized runner 的 opt-in 零 Provider Docker lifecycle 门禁。"""

from __future__ import annotations

import asyncio
import copy
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import test_stage_c_v8_workspace_remediation_docker as candidate_docker

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

import forge_stage_c_v8_workspace_remediation_authorized_protocol as protocol  # noqa: E402
import forge_stage_c_v8_workspace_remediation_authorized_runner as runner  # noqa: E402

DOCKER_ENABLED = os.getenv("FORGE_RUN_STAGE_C_V8_AUTHORIZED_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_STAGE_C_V8_AUTHORIZED_DOCKER=1 to run the authorized Stage C v8 Docker gate",
)


@pytest.fixture(scope="module")
def authorized_fixture_repository(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[str, str, str]]:
    yield from candidate_docker.fixture_repository.__wrapped__(tmp_path_factory)


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
    candidate_docker._assert_zero_managed_resources()
    yield
    candidate_docker._assert_zero_managed_resources()


@pytest.fixture(autouse=True)
def forbid_provider_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("Docker gate 禁止创建 Provider-backed model")

    monkeypatch.setattr(model_factory, "create_chat_model", forbidden)


def _gate_manifest(repository_url: str, commit_sha: str, source_snapshot_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = copy.deepcopy(protocol.load_manifest())
    image_id = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            manifest["environment"]["compile_image"],
            "--format",
            "{{.Id}}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    manifest["environment"]["image_id"] = image_id
    task = {
        "task_id": "stage-c-v8-authorized-docker-fixture",
        "repository_url": repository_url,
        "commit_sha": commit_sha,
        "source_snapshot_sha256": source_snapshot_sha256,
        "build_system_capabilities": ["make"],
        "selected_build_system": "make",
        "qualification_receipt": {"receipt_sha256": "b" * 64},
        "target_contract": {
            "target_id": "sample-static-library",
            "artifact_types": ["support_file", "static_library"],
            "required_artifacts": [
                "include/sample/api.h",
                "include/sample/detail.h",
                "lib/libsample.a",
            ],
        },
        "oracle": {
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <sample/api.h>\nint main(void){ return sample_add(2, 3) == 5 ? 0 : 1; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libsample.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
    }
    attempt = {
        "sequence": 1,
        "task_id": task["task_id"],
        "attempt_id": "stage-c-v8-authorized-docker-fixture-b-canary",
        "canary_id": "stage-c-v8-authorized-docker-fixture-canary",
    }
    manifest["tasks"] = [task]
    manifest["schedule"]["attempts"] = [attempt]
    manifest["schedule"]["canary_attempt_count"] = 1
    return manifest, attempt


def test_authorized_attempt_uses_explicit_workspace_runtime_v3_and_evaluator_v4(
    authorized_fixture_repository: tuple[str, str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_url, commit_sha, source_snapshot_sha256 = authorized_fixture_repository
    manifest, attempt = _gate_manifest(repository_url, commit_sha, source_snapshot_sha256)
    release_root = tmp_path / "release"
    release_root.mkdir()
    (release_root / ".compile-sessions").mkdir()
    evidence = release_root / manifest["execution"]["evidence_directory_relative"]
    decoy = tmp_path / "implicit-workspace"
    candidate_docker._make_root_owned_decoy(decoy, manifest["environment"]["compile_image"])
    assert not os.access(decoy, os.W_OK)

    original_paths = Paths(
        base_dir=tmp_path / ".deer-flow",
        workspace_root=decoy,
        host_workspace_root=str(decoy),
    )
    manager = CompileSessionManager(
        paths=original_paths,
        default_image=manifest["environment"]["compile_image"],
    )
    runtime = CompileDockerRuntime(manager=manager)
    monkeypatch.setattr(
        operations,
        "_services",
        CompileOperationsServices(manager=manager, runtime=runtime),
    )
    monkeypatch.setenv("COMPILE_RUNTIME_NO_PROXY", "host.docker.internal,127.0.0.1,localhost")
    model = candidate_docker.DeterministicCanaryModel()

    try:
        result = asyncio.run(
            runner.execute_attempt(
                manifest,
                attempt,
                release_revision="c" * 40,
                output_dir=evidence,
                repo_root=release_root,
                model_factory=lambda _manifest, _thread_id: model,
            )
        )
        assert manager.paths is original_paths
    finally:
        candidate_docker._normalize_tree(tmp_path, manifest["environment"]["compile_image"])

    assert result["method"] == "forge-agent-workflow-node-v3"
    assert result["candidate_submitted"] is True
    assert result["strict_reproducible_build_success"] is True
    assert result["bitwise_reproducible"] is True
    assert result["canary_passed"] is True
    assert result["recorded_tokens"] == 36
    assert result["request_token_ledger"] == [
        {
            "request_sequence": 1,
            "input_tokens": 8,
            "output_tokens": 4,
            "total_tokens": 12,
        },
        {
            "request_sequence": 2,
            "input_tokens": 8,
            "output_tokens": 4,
            "total_tokens": 12,
        },
        {
            "request_sequence": 3,
            "input_tokens": 8,
            "output_tokens": 4,
            "total_tokens": 12,
        },
    ]
    assert result["cleanup_succeeded"] is True
    assert model.calls == 3
    assert model.bind_kwargs and model.bind_kwargs[-1]["parallel_tool_calls"] is False
    candidate_docker._assert_zero_managed_resources()
