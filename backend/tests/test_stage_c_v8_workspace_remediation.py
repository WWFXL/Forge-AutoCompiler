"""Stage C v8 workspace remediation candidate 合同门禁。"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_stage_c_v7_prefreeze_canary_authorized_protocol as parent  # noqa: E402
import forge_stage_c_v8_workspace_remediation_protocol as protocol  # noqa: E402
import forge_stage_c_v8_workspace_remediation_runner as runner  # noqa: E402

MANIFEST_PATH = REPO_ROOT / protocol.MANIFEST_RELATIVE_PATH
SCHEMA_PATH = REPO_ROOT / protocol.SCHEMA_RELATIVE_PATH


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _workspace_root(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    root.mkdir()
    (root / ".compile-sessions").mkdir()
    return root


def test_manifest_and_const_schema_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.validate_allowed_delta(manifest, REPO_ROOT)["status"] == "passed"
    jsonschema.validate(manifest, schema)


def test_failure_audit_is_fixed_and_old_batch_cannot_resume() -> None:
    audit = protocol.validate_failure_audit(REPO_ROOT)

    assert audit["identity"]["manifest_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256
    assert audit["reachability"]["total_tokens"] == 70
    assert audit["theora_attempt"]["model_requests"] == 0
    assert audit["theora_attempt"]["recorded_tokens"] == 0
    assert audit["decision"] == {
        "historical_outcomes_imported": False,
        "next_identity": "stage_c_v8_workspace_remediation_candidate",
        "old_batch_resumable": False,
        "provider_execution_authorized": False,
        "replacement_authorized": False,
        "retry_authorized": False,
    }


def test_candidate_preserves_parent_scientific_contract() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    source = parent.load_manifest(repo_root=REPO_ROOT)

    for key in (
        "provider",
        "environment",
        "budget",
        "methods",
        "candidate_contract",
        "external_evaluator",
        "tasks",
        "analysis",
        "historical_inputs",
    ):
        assert manifest[key] == source[key]
    assert [item["task_id"] for item in manifest["schedule"]["attempts"]] == [item["task_id"] for item in source["schedule"]["attempts"]]

    drifted = copy.deepcopy(manifest)
    drifted["tasks"][0]["selected_build_system"] = "cmake"
    with pytest.raises(protocol.StageCV8ProtocolError, match="父科学合同"):
        protocol.validate_allowed_delta(drifted, REPO_ROOT)


def test_candidate_is_fully_unauthorized_and_has_no_token_ceiling() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]

    assert authorization["candidate_identity_only"] is True
    assert all(
        authorization[field] is False
        for field in (
            "credential_read_authorized",
            "provider_calls_authorized",
            "model_creation_authorized",
            "reachability_request_authorized",
            "docker_execution_authorized",
            "formal_stage_c_attempts_authorized",
            "evidence_write_authorized",
            "model_tokens_authorized",
            "stage_c_execution_started",
        )
    )
    assert authorization["model_token_ceiling"] is None
    assert manifest["budget"]["per_attempt"]["max_recorded_tokens"] is None
    assert manifest["execution"]["commands"] == ["validate", "preflight", "show-plan"]
    assert manifest["execution"]["docker"] == parent.load_manifest(repo_root=REPO_ROOT)["execution"]["docker"]


def test_validate_is_zero_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)

    monkeypatch.setattr(runner, "require_workspace_identity", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("workspace access")))
    monkeypatch.setattr(runner.parent_runner, "require_docker_identity", lambda *_args: (_ for _ in ()).throw(AssertionError("docker access")))
    result = runner.validate_runtime(manifest, REPO_ROOT)

    assert result["status"] == "valid"
    assert result["credential_read"] is False
    assert result["evidence_written"] is False
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)


def test_preflight_checks_workspace_before_docker_without_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    root = _workspace_root(tmp_path)
    observed: list[str] = []

    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_args, **_kwargs: observed.append("frozen"))
    monkeypatch.setattr(runner, "_validate_all_node_inputs", lambda *_args: observed.append("node"))
    monkeypatch.setattr(runner.parent_runner, "require_docker_identity", lambda *_args: observed.append("docker"))
    monkeypatch.setattr(runner.parent_runner, "require_zero_managed_resources", lambda: observed.append("resources"))

    result = runner.collect_preflight(manifest, repo_root=root)

    assert observed == ["frozen", "node", "docker", "resources"]
    assert result["workspace"]["repository_root"] == str(root)
    assert result["evidence_files"] == []
    assert result["credential_read"] is False
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)
    assert not (root / manifest["execution"]["evidence_directory_relative"]).exists()


def test_workspace_identity_rejects_symlink_and_output_drift(tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    root = _workspace_root(tmp_path)
    linked_root = tmp_path / "linked-release"
    linked_root.symlink_to(root, target_is_directory=True)

    with pytest.raises(runner.StageCV8RunnerError, match="release repository root"):
        runner.require_workspace_identity(manifest, repo_root=linked_root)
    with pytest.raises(runner.StageCV8RunnerError, match="candidate evidence"):
        runner.require_workspace_identity(manifest, repo_root=root, output_dir=root / ".compile-sessions" / "other")

    (root / ".compile-sessions").rmdir()
    (root / "real-sessions").mkdir()
    (root / ".compile-sessions").symlink_to(root / "real-sessions", target_is_directory=True)
    with pytest.raises(runner.StageCV8RunnerError, match="符号链接"):
        runner.require_workspace_identity(manifest, repo_root=root)


def test_workspace_identity_rejects_unwritable_compile_root(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root 的目录写权限语义不同")
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    root = _workspace_root(tmp_path)
    compile_root = root / ".compile-sessions"
    compile_root.chmod(0o555)
    try:
        with pytest.raises(runner.StageCV8RunnerError, match="不可写"):
            runner.require_workspace_identity(manifest, repo_root=root)
    finally:
        compile_root.chmod(0o755)


@pytest.mark.parametrize("command", ["reachability", "run"])
def test_real_commands_are_rejected_before_runtime_side_effects(command: str, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    monkeypatch.setattr(runner.protocol, "load_manifest", lambda *_args, **_kwargs: manifest)
    monkeypatch.setattr(runner, "collect_preflight", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("preflight")))
    monkeypatch.setattr(runner, "get_compile_services", lambda: (_ for _ in ()).throw(AssertionError("runtime")))

    with pytest.raises(runner.StageCV8RunnerError, match=f"未授权 {command}"):
        runner.main([command])


def test_runtime_identity_restores_manager_and_runtime_after_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    root = _workspace_root(tmp_path)
    original_paths = SimpleNamespace(name="implicit")
    manager = SimpleNamespace(paths=original_paths, default_image="old-image", parallel_jobs=99)
    runtime = SimpleNamespace(config=SimpleNamespace(image="old-runtime-image", parallel_jobs=88, replay_timeout_seconds=77))
    services = SimpleNamespace(manager=manager, runtime=runtime)
    monkeypatch.setattr(runner, "get_compile_services", lambda: services)

    with pytest.raises(RuntimeError, match="sentinel"):
        with runner._runtime_identity(manifest, root):
            assert manager.paths.compile_sessions_dir == root / ".compile-sessions"
            assert manager.paths.host_compile_sessions_dir == root / ".compile-sessions"
            raise RuntimeError("sentinel")

    assert manager.paths is original_paths
    assert (manager.default_image, manager.parallel_jobs) == ("old-image", 99)
    assert (runtime.config.image, runtime.config.parallel_jobs, runtime.config.replay_timeout_seconds) == ("old-runtime-image", 88, 77)


def test_gate_cleanup_uses_explicit_paths_then_restores_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    root = _workspace_root(tmp_path)
    original_paths = SimpleNamespace(name="implicit")
    manager = SimpleNamespace(paths=original_paths, default_image="old-image", parallel_jobs=99)
    runtime = SimpleNamespace(config=SimpleNamespace(image="old-runtime-image", parallel_jobs=88, replay_timeout_seconds=77))
    services = SimpleNamespace(manager=manager, runtime=runtime)
    session = SimpleNamespace(thread_id="thread", session_id="session")
    ledger = SimpleNamespace(experiment_id="experiment_test", physical_attempt_id="physical_attempt_test")
    cleanup_paths: list[Path] = []

    monkeypatch.setattr(runner, "get_compile_services", lambda: services)
    monkeypatch.setattr(runner.ExperimentLedger, "create", lambda *_args, **_kwargs: ledger)
    monkeypatch.setattr(runner, "activate_experiment", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "deactivate_experiment", lambda *_args: None)
    monkeypatch.setattr(runner, "prepare_compile_session_impl", lambda **_kwargs: session)
    monkeypatch.setattr(runner, "clone_repository_impl", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("clone sentinel")))

    def cleanup(*, session: Any) -> tuple[Any, Any]:
        assert session is not None
        cleanup_paths.append(manager.paths.compile_sessions_dir)
        return session, SimpleNamespace(succeeded=True)

    monkeypatch.setattr(runner, "cleanup_and_finalize_compile_session_impl", cleanup)
    monkeypatch.setattr(runner.parent_runner, "require_zero_managed_resources", lambda: None)

    with pytest.raises(RuntimeError, match="clone sentinel"):
        asyncio.run(
            runner.execute_zero_provider_gate_attempt(
                manifest,
                manifest["schedule"]["attempts"][0],
                repo_root=root,
                ledger_path=tmp_path / "gate.jsonl",
                model=object(),
            )
        )

    assert cleanup_paths == [root / ".compile-sessions"]
    assert manager.paths is original_paths


def test_new_sources_do_not_embed_credentials() -> None:
    source = (SCRIPTS / "forge_stage_c_v8_workspace_remediation_runner.py").read_text(encoding="utf-8")
    assert "sk-" not in source
    assert "OpenAI_AK" not in source
