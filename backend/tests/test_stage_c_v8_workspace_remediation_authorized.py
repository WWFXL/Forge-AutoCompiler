"""Stage C v8 workspace remediation authorized canary 合同门禁。"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jsonschema
import pytest
from langchain_core.messages import AIMessage

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_stage_c_v8_workspace_remediation_authorized_protocol as protocol  # noqa: E402
import forge_stage_c_v8_workspace_remediation_authorized_runner as runner  # noqa: E402
import forge_stage_c_v8_workspace_remediation_protocol as parent  # noqa: E402

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


def test_authorized_delta_preserves_candidate_and_workspace_contract() -> None:
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
        "schedule",
        "historical_inputs",
        "failure_audit",
        "parent_authorized_v7",
    ):
        assert manifest[key] == source[key]
    assert manifest["execution"]["workspace"] == source["execution"]["workspace"]
    assert manifest["parent_candidate"]["canonical_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256

    drifted = copy.deepcopy(manifest)
    drifted["execution"]["workspace"]["binding"] = "implicit"
    with pytest.raises(protocol.StageCV8AuthorizedProtocolError, match="workspace"):
        protocol.validate_allowed_delta(drifted, REPO_ROOT)


def test_authorization_has_no_token_ceiling_but_keeps_operation_limits() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    budget = manifest["budget"]

    assert all(authorization[field] is True for field in authorization if field.endswith("_authorized"))
    assert authorization["model_token_ceiling"] is None
    assert budget["reachability_max_recorded_tokens"] is None
    assert budget["canary_attempts_max_recorded_tokens"] is None
    assert budget["total_max_recorded_tokens"] is None
    assert budget["per_attempt"]["max_recorded_tokens"] is None
    assert budget["token_accounting"]["token_total_is_termination_condition"] is False
    assert budget["per_attempt"]["max_model_requests"] == 24
    assert budget["per_attempt"]["forge_max_commands"] == 32


def test_validate_is_zero_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    monkeypatch.setattr(
        runner,
        "_provider_config_preflight",
        lambda *_args: (_ for _ in ()).throw(AssertionError("credential read")),
    )
    monkeypatch.setattr(
        runner,
        "require_docker_identity",
        lambda *_args: (_ for _ in ()).throw(AssertionError("docker access")),
    )
    result = runner.validate_runtime(manifest, REPO_ROOT)

    assert result["status"] == "valid"
    assert result["workspace_binding"] == "release_repository_root"
    assert result["credential_read"] is False
    assert result["evidence_written"] is False
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)


def test_preflight_checks_workspace_before_release_credential_and_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    root = _workspace_root(tmp_path)
    output_dir = root / manifest["execution"]["evidence_directory_relative"]
    observed: list[str] = []

    monkeypatch.setattr(
        runner.protocol,
        "verify_frozen_components",
        lambda *_args, **_kwargs: observed.append("frozen"),
    )
    monkeypatch.setattr(runner, "_validate_all_node_inputs", lambda *_args: observed.append("node"))

    def workspace(*_args: Any, **_kwargs: Any) -> dict[str, str]:
        observed.append("workspace")
        return {"repository_root": str(root), "evidence_directory": str(output_dir)}

    monkeypatch.setattr(runner, "require_workspace_identity", workspace)
    monkeypatch.setattr(
        runner,
        "require_release_identity",
        lambda *_args, **_kwargs: observed.append("release") or {"revision": "a" * 40},
    )
    monkeypatch.setattr(
        runner,
        "require_network_medium",
        lambda *_args: observed.append("network") or "ethernet",
    )
    monkeypatch.setattr(
        runner,
        "require_docker_identity",
        lambda *_args: observed.append("docker") or {},
    )
    monkeypatch.setattr(
        runner,
        "require_zero_managed_resources",
        lambda: observed.append("resources"),
    )
    monkeypatch.setattr(
        runner,
        "_provider_config_preflight",
        lambda *_args: observed.append("credential"),
    )

    result = runner.collect_preflight(
        manifest,
        output_dir=output_dir,
        repo_root=root,
        require_empty=True,
    )

    assert observed == [
        "frozen",
        "node",
        "workspace",
        "release",
        "network",
        "docker",
        "resources",
        "credential",
    ]
    assert result["evidence_files"] == []
    assert not output_dir.exists()


def test_output_directory_must_be_frozen_direct_child(tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    root = _workspace_root(tmp_path)
    expected = root / manifest["execution"]["evidence_directory_relative"]

    assert runner._output_dir(manifest, expected, root) == expected
    with pytest.raises(runner.StageCV8AuthorizedRunnerError, match="冻结直属目录"):
        runner._output_dir(manifest, root / ".compile-sessions" / "other", root)


class _ReachabilityModel:
    def invoke(self, prompt: str) -> AIMessage:
        assert prompt == "Reply with exactly STAGE_C_V8_WORKSPACE_OK and nothing else."
        return AIMessage(
            content="STAGE_C_V8_WORKSPACE_OK",
            response_metadata={"model_name": "deepseek-flash"},
            usage_metadata={"input_tokens": 9, "output_tokens": 3, "total_tokens": 12},
        )


def test_reachability_is_create_once_and_records_each_token_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "b" * 40
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *_args, **_kwargs: {"release_revision": revision},
    )

    report = runner.execute_reachability(
        manifest,
        output_dir=tmp_path,
        repo_root=REPO_ROOT,
        model_factory=lambda _manifest, _thread_id: _ReachabilityModel(),
    )

    assert report["recorded_tokens"] == 12
    assert report["token_ledger"] == [
        {
            "request_sequence": 1,
            "input_tokens": 9,
            "output_tokens": 3,
            "total_tokens": 12,
        }
    ]
    assert runner.require_passed_reachability(manifest, tmp_path, revision) == report
    with pytest.raises(runner.StageCV8AuthorizedRunnerError, match="不可覆盖"):
        runner.execute_reachability(
            manifest,
            output_dir=tmp_path,
            repo_root=REPO_ROOT,
            model_factory=lambda _manifest, _thread_id: _ReachabilityModel(),
        )


def _synthetic_outcome(attempt: dict[str, Any], *, passed: bool, tokens: int) -> dict[str, Any]:
    return {
        "manifest_sha256": "unused-by-current-batch",
        "release_revision": "c" * 40,
        "sequence": attempt["sequence"],
        "task_id": attempt["task_id"],
        "attempt_id": attempt["attempt_id"],
        "canary_passed": passed,
        "strict_reproducible_build_success": passed,
        "bitwise_reproducible": passed,
        "s0_s5": [{"layer": layer, "status": "passed" if passed else "failed"} for layer in ("S0", "S1", "S2", "S3", "S4", "S5")],
        "recorded_tokens": tokens,
        "request_token_ledger": [
            {
                "request_sequence": 1,
                "input_tokens": tokens - 1,
                "output_tokens": 1,
                "total_tokens": tokens,
            }
        ],
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
    }


def test_batch_stops_on_first_failure_without_token_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "c" * 40
    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *_args, **_kwargs: {"release_revision": revision},
    )
    monkeypatch.setattr(
        runner,
        "require_passed_reachability",
        lambda *_args, **_kwargs: {"recorded_tokens": 10},
    )
    monkeypatch.setattr(runner, "require_zero_managed_resources", lambda: None)

    async def execute(_manifest: dict[str, Any], attempt: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        calls.append(attempt["task_id"])
        return _synthetic_outcome(attempt, passed=attempt["sequence"] == 1, tokens=10**9)

    report = runner.run_batch(
        manifest,
        output_dir=tmp_path,
        repo_root=REPO_ROOT,
        attempt_executor=execute,
    )

    assert calls == ["theora", "json-c"]
    assert report["status"] == "stopped_on_first_failure"
    assert report["attempt_recorded_tokens"] == 2 * 10**9
    assert report["token_ceiling"] is None
    assert report["treatment_effect_estimated"] is False


def test_completed_prefix_rejects_gap_and_accepts_unbounded_tokens(
    tmp_path: Path,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "d" * 40
    digest = protocol.canonical_sha256(manifest)
    first, second = manifest["schedule"]["attempts"][:2]
    for attempt in (first, second):
        marker_path, result_path, _ledger_path = runner._attempt_paths(manifest, tmp_path, attempt)
        runner._write_once(
            marker_path,
            {
                "status": "completed",
                "manifest_sha256": digest,
                "release_revision": revision,
                "attempt_id": attempt["attempt_id"],
            },
        )
        result = _synthetic_outcome(attempt, passed=True, tokens=10**12)
        result.update(manifest_sha256=digest, release_revision=revision)
        runner._write_once(result_path, result)

    completed, next_index = runner._completed_prefix(manifest, tmp_path, revision)
    assert len(completed) == next_index == 2

    first_marker, first_result, _ = runner._attempt_paths(manifest, tmp_path, first)
    first_marker.unlink()
    first_result.unlink()
    with pytest.raises(runner.StageCV8AuthorizedRunnerError, match="连续前缀"):
        runner._completed_prefix(manifest, tmp_path, revision)


def test_attempt_cleanup_runs_inside_explicit_workspace_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    root = _workspace_root(tmp_path)
    output_dir = root / manifest["execution"]["evidence_directory_relative"]
    original_paths = SimpleNamespace(name="implicit")
    manager = SimpleNamespace(paths=original_paths)
    session = SimpleNamespace(
        session_id="session",
        finalized_at=None,
        status="failed",
    )
    ledger = SimpleNamespace(
        experiment_id="experiment_test",
        physical_attempt_id="physical_attempt_test",
        append=lambda *_args, **_kwargs: None,
    )
    cleanup_paths: list[Path] = []

    @contextmanager
    def runtime_identity(_manifest: dict[str, Any], _repo_root: Path):
        manager.paths = SimpleNamespace(compile_sessions_dir=root / ".compile-sessions")
        try:
            yield SimpleNamespace(manager=manager)
        finally:
            manager.paths = original_paths

    monkeypatch.setattr(runner, "_runtime_identity", runtime_identity)
    monkeypatch.setattr(runner.ExperimentLedger, "create", lambda *_args, **_kwargs: ledger)
    monkeypatch.setattr(runner, "activate_experiment", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "deactivate_experiment", lambda *_args: None)
    monkeypatch.setattr(runner, "prepare_compile_session_impl", lambda **_kwargs: session)
    monkeypatch.setattr(
        runner,
        "clone_repository_impl",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("clone sentinel")),
    )

    def cleanup(*, session: Any) -> tuple[Any, Any]:
        cleanup_paths.append(manager.paths.compile_sessions_dir)
        session.finalized_at = "done"
        return session, SimpleNamespace(succeeded=True)

    monkeypatch.setattr(runner, "cleanup_and_finalize_compile_session_impl", cleanup)
    monkeypatch.setattr(runner, "require_zero_managed_resources", lambda: None)

    result = asyncio.run(
        runner.execute_attempt(
            manifest,
            manifest["schedule"]["attempts"][0],
            release_revision="e" * 40,
            output_dir=output_dir,
            repo_root=root,
            model_factory=lambda *_args: object(),
        )
    )

    assert result["canary_passed"] is False
    assert result["error_class"] == "RuntimeError"
    assert cleanup_paths == [root / ".compile-sessions"]
    assert manager.paths is original_paths


def test_new_sources_do_not_embed_credentials() -> None:
    source = (SCRIPTS / "forge_stage_c_v8_workspace_remediation_authorized_runner.py").read_text(encoding="utf-8")
    assert "sk-" not in source
    assert "OpenAI_AK" not in source
