"""Issue #206 R2 Make 未执行候选的零 provider 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_make_candidate_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_make_candidate_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r2-make-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-r2-make-candidate.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module(
    "forge_opaque_provenance_make_candidate_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_opaque_provenance_make_candidate_runner_test",
    RUNNER_PATH,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _valid_snapshot(manifest: dict) -> dict:
    return {
        "schema_version": "forge-opaque-provenance-r2-make-candidate-preflight-1.0.0",
        "branch": "main",
        "head_commit": "a" * 40,
        "origin_main_commit": "a" * 40,
        "worktree_clean": True,
        "authorization_baseline_ancestor": True,
        "frozen_component_sha256": manifest["frozen_components"],
        "candidate_evidence_directory": manifest["evidence"]["directory"],
        "candidate_evidence_entries": 0,
        "checkpoint_status": "not_created",
        "docker_executed": False,
    }


def test_generated_manifest_schema_runtime_and_preregistration_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["runtime_adapter"]["file_sha256"] == protocol.file_sha256(RUNNER_PATH)
    preregistration = REPO_ROOT / manifest["preregistration"]["path"]
    assert manifest["preregistration"]["file_sha256"] == protocol.file_sha256(preregistration)


def test_hoextdown_case_is_result_blind_and_matches_make_lifecycle() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    source = manifest["source_protocol"]["source_case"]
    case = manifest["case"]
    artifact = source["artifact_oracle"]["required_artifacts"][0]
    assert source["id"] == "hoextdown"
    assert source["result_data_consulted"] is False
    assert case["repository_url"] == source["repository_url"]
    assert case["commit_sha"] == source["commit"]
    assert case["build_system"] == "make"
    assert case["target"] == artifact["producing_target"] == "libhoedown.a"
    assert case["build_output"] == artifact["build_output_path"]
    assert case["staged_artifact"] == artifact["staged_relative_path"]
    assert case["artifact_type"] == "static_library"


def test_frozen_components_are_current_and_include_make_lifecycle_and_r0() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["frozen_components"] == protocol.FROZEN_COMPONENT_SHA256
    for path, expected in manifest["frozen_components"].items():
        assert protocol.file_sha256(REPO_ROOT / path) == expected
    assert manifest["repair_packet"]["origin_path"] == ("scripts/forge_opaque_provenance_make_lifecycle_gate.py")
    assert manifest["r0_observability"]["companion_event"] == ("agent.tool_rejection_observed")
    assert manifest["r0_observability"]["atomic_fields"] == (protocol.R0_OBSERVATION_FIELDS)


def test_schedule_evidence_and_token_ceiling_are_new_and_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["schedule"] == [
        {
            "pair_id": protocol.PAIR_ID,
            "order": 1,
            "case_id": manifest["case"]["case_id"],
            "arm_order": ["baseline", "treatment"],
            "state_matched": True,
            "treatment_exposure_only": "repair_packet",
            "shared_measurement_policy": "runtime_parity_with_r0_observability_v1",
        }
    ]
    assert manifest["schedule_sha256"] == protocol.canonical_sha256(manifest["schedule"])
    evidence = manifest["evidence"]
    identity = {key: value for key, value in evidence.items() if key != "identity_sha256"}
    assert evidence["identity_sha256"] == protocol.canonical_sha256(identity)
    assert evidence["status"] == "not_created"
    budget = manifest["budget"]
    assert budget["phase_recorded_token_ceiling"] == 245000
    assert budget["phase_recorded_token_ceiling"] == (budget["reachability_recorded_tokens"] + budget["pair_recorded_tokens"])


def test_all_execution_authorizations_and_capabilities_are_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    assert authorization["candidate_generation_authorized"] is True
    assert authorization["zero_provider_preflight_authorized"] is True
    for key in (
        "checkpoint_creation_authorized",
        "reachability_request_authorized",
        "provider_calls_authorized",
        "formal_attempts_authorized",
        "pair_collection_authorized",
        "credential_read_authorized",
        "model_creation_authorized",
        "docker_execution_authorized",
        "evidence_write_authorized",
    ):
        assert authorization[key] is False
    assert authorization["model_tokens_authorized"] == 0
    runtime = manifest["runtime_adapter"]
    assert runtime["commands"] == ["validate", "plan", "preflight"]
    assert not any(value for key, value in runtime.items() if key.endswith("_supported"))


def test_plan_and_preflight_snapshot_are_zero_provider_and_zero_docker() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    snapshot = runner.validate_preflight_snapshot(manifest, _valid_snapshot(manifest))
    assert snapshot["checkpoint_status"] == "not_created"
    plan = runner.build_plan(manifest)
    assert plan["build_system"] == "make"
    assert plan["phase_recorded_token_ceiling"] == 245000
    assert plan["r0_companion_event"] == "agent.tool_rejection_observed"
    assert (
        plan["provider_calls"],
        plan["formal_attempts"],
        plan["model_tokens"],
        plan["evidence_writes"],
    ) == (0, 0, 0, 0)
    assert plan["credential_read"] is False
    assert plan["docker_executed"] is False
    assert plan["execution_authorized"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("branch", "research/206"),
        ("origin_main_commit", "b" * 40),
        ("worktree_clean", False),
        ("authorization_baseline_ancestor", False),
        ("frozen_component_sha256", {}),
        ("candidate_evidence_entries", 1),
        ("checkpoint_status", "created"),
        ("docker_executed", True),
    ],
)
def test_preflight_drift_fails_closed(field: str, value: object) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    snapshot = _valid_snapshot(manifest)
    snapshot[field] = value
    with pytest.raises(runner.RuntimeGateError):
        runner.validate_preflight_snapshot(manifest, snapshot)


def test_collector_is_pure_snapshot_and_does_not_create_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    candidate = tmp_path / ".compile-sessions" / Path(manifest["evidence"]["directory"]).name
    commands: list[tuple[str, ...]] = []

    def fake_command(command, _cwd: Path) -> str:
        key = tuple(command)
        commands.append(key)
        if key == ("git", "branch", "--show-current"):
            return "main"
        if key in (("git", "rev-parse", "HEAD"), ("git", "rev-parse", "origin/main")):
            return "c" * 40
        if key == ("git", "status", "--porcelain") or key[:3] == (
            "git",
            "merge-base",
            "--is-ancestor",
        ):
            return ""
        raise AssertionError(key)

    monkeypatch.setattr(
        runner.protocol,
        "validate_manifest",
        lambda _manifest, _repo_root=None: _manifest,
    )
    frozen_by_name = {Path(path).name: sha256 for path, sha256 in manifest["frozen_components"].items()}
    monkeypatch.setattr(runner, "_file_sha256", lambda path: frozen_by_name[path.name])
    snapshot = runner.collect_preflight_snapshot(
        manifest,
        repo_root=tmp_path,
        host_candidate_evidence_directory=candidate,
        command_runner=fake_command,
    )
    assert snapshot["candidate_evidence_entries"] == 0
    assert snapshot["docker_executed"] is False
    assert not candidate.exists()
    assert commands and all(command[0] == "git" for command in commands)


def test_execute_paths_are_rejected_and_source_reads_no_credentials_or_docker() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    for execute in (
        runner.execute_checkpoint,
        runner.execute_reachability,
        runner.execute_pair,
    ):
        with pytest.raises(runner.RuntimeGateError, match="not authorized"):
            execute(manifest)
    source = RUNNER_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "os.environ",
        "os.getenv",
        "create_chat_model",
        "ChatOpenAI",
        "ChatDeepSeek",
        "api_key=",
        '("docker",',
    ):
        assert forbidden not in source


def test_schema_and_protocol_reject_identity_authorization_or_budget_drift() -> None:
    schema = _load(SCHEMA_PATH)
    manifest = _load(MANIFEST_PATH)
    mutations = (
        ("case", "repository_url", "https://github.com/example/drift"),
        ("case", "target", "drift"),
        ("authorization", "provider_calls_authorized", True),
        ("budget", "phase_recorded_token_ceiling", 245001),
        ("r0_observability", "companion_required_for_classified_rejection", False),
        ("checkpoint", "status", "created"),
    )
    for section, field, value in mutations:
        drifted = copy.deepcopy(manifest)
        drifted[section][field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
            protocol.validate_manifest(drifted, REPO_ROOT)
