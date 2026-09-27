"""Stage C v7 pre-freeze verifier authorized canary 合同门禁。"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_stage_c_v7_prefreeze_canary_authorized_protocol as protocol  # noqa: E402
import forge_stage_c_v7_prefreeze_canary_authorized_runner as runner  # noqa: E402
import forge_stage_c_v7_prefreeze_canary_protocol as parent  # noqa: E402

MANIFEST_PATH = REPO_ROOT / protocol.MANIFEST_RELATIVE_PATH
SCHEMA_PATH = REPO_ROOT / protocol.SCHEMA_RELATIVE_PATH


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_and_const_schema_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.validate_allowed_delta(manifest, REPO_ROOT)["status"] == "passed"
    assert manifest["parent_candidate"]["canonical_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256


def test_authorized_delta_preserves_parent_scientific_contract() -> None:
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
    ):
        assert manifest[key] == source[key]

    drifted = copy.deepcopy(manifest)
    drifted["schedule"]["attempts"].reverse()
    with pytest.raises(protocol.StageCV7AuthorizedProtocolError, match="父 candidate"):
        protocol.validate_allowed_delta(drifted, REPO_ROOT)


def test_authorization_has_no_token_ceiling_but_keeps_operation_limits() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    budget = manifest["budget"]

    assert all(authorization[field] is True for field in authorization if field.endswith("_authorized"))
    assert authorization["model_token_ceiling"] is None
    assert budget["per_attempt"]["max_recorded_tokens"] is None
    assert budget["reachability_max_recorded_tokens"] is None
    assert budget["canary_attempts_max_recorded_tokens"] is None
    assert budget["total_max_recorded_tokens"] is None
    assert budget["token_accounting"]["token_total_is_termination_condition"] is False
    assert budget["per_attempt"]["max_model_requests"] == 24
    assert budget["per_attempt"]["forge_max_commands"] == 32


def test_validate_is_zero_provider_and_does_not_read_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)

    monkeypatch.setattr(runner, "_provider_config_preflight", lambda *_args: (_ for _ in ()).throw(AssertionError("credential read")))
    monkeypatch.setattr(runner, "require_docker_identity", lambda *_args: (_ for _ in ()).throw(AssertionError("docker access")))
    result = runner.validate_runtime(manifest, REPO_ROOT)

    assert result == {
        "status": "valid",
        "manifest_sha256": protocol.parent.canonical_sha256(manifest),
        "runtime": "agent-workflow-runtime-v3",
        "external_evaluator": "external-evaluator-v4",
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "credential_read": False,
        "evidence_written": False,
    }


def test_preflight_checks_environment_without_writing_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    output_dir = tmp_path / "evidence"
    revision = "a" * 40

    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "_output_dir", lambda _manifest, path: path)
    monkeypatch.setattr(runner, "require_release_identity", lambda *_args, **_kwargs: {"revision": revision})
    monkeypatch.setattr(runner, "require_network_medium", lambda _manifest: "ethernet")
    monkeypatch.setattr(
        runner,
        "require_docker_identity",
        lambda _manifest: {
            "provider": "linux-native",
            "context": "default",
            "endpoint": "unix:///var/run/docker.sock",
            "image_id": manifest["environment"]["image_id"],
        },
    )
    monkeypatch.setattr(runner, "require_zero_managed_resources", lambda: None)
    monkeypatch.setattr(runner, "_provider_config_preflight", lambda _manifest: None)

    result = runner.collect_preflight(manifest, output_dir=output_dir, repo_root=REPO_ROOT, require_empty=True)

    assert result["ready"] is True
    assert result["credential_check"] == "environment_variable_presence_only"
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (0, 0, 0)
    assert not output_dir.exists()


class _ReachabilityModel:
    def invoke(self, prompt: str) -> AIMessage:
        assert prompt == "Reply with exactly STAGE_C_V7_CANARY_OK and nothing else."
        return AIMessage(
            content="STAGE_C_V7_CANARY_OK",
            response_metadata={"model_name": "deepseek-flash"},
            usage_metadata={"input_tokens": 9, "output_tokens": 3, "total_tokens": 12},
        )


def test_reachability_is_create_once_and_records_each_token_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "b" * 40
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *_args, **_kwargs: {"release_revision": revision, "network_access_medium": "ethernet"},
    )

    report = runner.execute_reachability(
        manifest,
        output_dir=tmp_path,
        repo_root=REPO_ROOT,
        model_factory=lambda _manifest, _thread_id: _ReachabilityModel(),
    )

    assert report["recorded_tokens"] == 12
    assert report["token_ledger"] == [{"request_sequence": 1, "input_tokens": 9, "output_tokens": 3, "total_tokens": 12}]
    assert runner.require_passed_reachability(manifest, tmp_path, revision) == report
    with pytest.raises(runner.StageCV7AuthorizedRunnerError, match="不可覆盖"):
        runner.execute_reachability(
            manifest,
            output_dir=tmp_path,
            repo_root=REPO_ROOT,
            model_factory=lambda _manifest, _thread_id: _ReachabilityModel(),
        )


def test_event_observations_capture_tokens_rejections_and_same_attempt_repair(tmp_path: Path) -> None:
    events = [
        {"event_type": "model.request_completed", "payload": {"request_sequence": 1, "input_tokens": 8, "output_tokens": 4, "recorded_tokens": 12}},
        {"event_type": "candidate.submit_rejected", "payload": {"rejection_codes": ["target_mapping_invalid"], "rejection_details": [{"path": "lib/a.a"}]}},
        {"event_type": "model.request_completed", "payload": {"request_sequence": 2, "input_tokens": 10, "output_tokens": 5, "recorded_tokens": 15}},
        {"event_type": "candidate.submit_accepted", "payload": {"candidate_id": "candidate-1"}},
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps(item) + "\n" for item in events), encoding="utf-8")

    result = runner._event_observations(path)

    assert result["token_ledger"] == [
        {"request_sequence": 1, "input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
        {"request_sequence": 2, "input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    ]
    assert result["submit_attempts"] == 2
    assert result["rejection_codes"] == ["target_mapping_invalid"]
    assert result["rejection_evidence_count"] == 1
    assert result["same_attempt_repair_observed"] is True


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
        "request_token_ledger": [{"request_sequence": 1, "input_tokens": tokens - 1, "output_tokens": 1, "total_tokens": tokens}],
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
    }


def test_batch_stops_on_first_failure_without_token_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "c" * 40
    reachability = {"recorded_tokens": 10}
    calls: list[str] = []

    monkeypatch.setattr(runner, "collect_preflight", lambda *_args, **_kwargs: {"release_revision": revision})
    monkeypatch.setattr(runner, "require_passed_reachability", lambda *_args, **_kwargs: reachability)
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
    assert report["observed_task_order"] == calls
    assert report["attempt_recorded_tokens"] == 2 * 10**9
    assert report["token_ceiling"] is None
    assert report["treatment_effect_estimated"] is False
    assert _load(tmp_path / manifest["execution"]["batch_marker"])["status"] == "stopped"


def test_completed_prefix_rejects_gap_and_accepts_unbounded_tokens(tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    revision = "d" * 40
    digest = protocol.parent.canonical_sha256(manifest)
    first, second = manifest["schedule"]["attempts"][:2]

    for attempt in (first, second):
        marker_path, result_path, _ledger_path = runner._attempt_paths(manifest, tmp_path, attempt)
        marker = {
            "status": "completed",
            "manifest_sha256": digest,
            "release_revision": revision,
            "attempt_id": attempt["attempt_id"],
        }
        result = _synthetic_outcome(attempt, passed=True, tokens=10**12)
        result.update(manifest_sha256=digest, release_revision=revision)
        runner._write_once(marker_path, marker)
        runner._write_once(result_path, result)

    completed, next_index = runner._completed_prefix(manifest, tmp_path, revision)
    assert len(completed) == next_index == 2

    first_marker, first_result, _ = runner._attempt_paths(manifest, tmp_path, first)
    first_marker.unlink()
    first_result.unlink()
    with pytest.raises(runner.StageCV7AuthorizedRunnerError, match="连续前缀"):
        runner._completed_prefix(manifest, tmp_path, revision)


def test_new_sources_do_not_embed_credentials() -> None:
    source = (SCRIPTS / "forge_stage_c_v7_prefreeze_canary_authorized_runner.py").read_text(encoding="utf-8")
    assert "sk-" not in source
    assert "OpenAI_AK" not in source
