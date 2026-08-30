"""Issue #188 runtime-parity provider amendment 候选的零 provider 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_provider_amendment_candidate_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_provider_amendment_candidate_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-runtime-parity-provider-amendment-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-runtime-parity-provider-amendment-candidate.schema.json"
PARENT_MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-minimal-canary-execution.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_opaque_provenance_provider_amendment_candidate_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_opaque_provenance_provider_amendment_candidate_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _valid_snapshot(manifest: dict) -> dict:
    return {
        "schema_version": "forge-opaque-provenance-runtime-parity-amendment-preflight-1.0.0",
        "branch": "main",
        "head_commit": "a" * 40,
        "origin_main_commit": "a" * 40,
        "worktree_clean": True,
        "authorization_baseline_ancestor": True,
        "docker_provider": "ubuntu-native",
        "docker_context": "default",
        "docker_endpoint": "/var/run/docker.sock",
        "network_medium": "wifi",
        "candidate_evidence_directory": manifest["evidence"]["directory"],
        "candidate_evidence_entries": 0,
        "historical_canary_report_sha256": manifest["historical_evidence"]["canary_report_sha256"],
        "managed_orphans": [],
    }


def test_generated_manifest_schema_parent_runtime_and_preregistration_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["parent"]["canonical_sha256"] == protocol.PARENT_MANIFEST_SHA256
    assert manifest["runtime_adapter"]["file_sha256"] == protocol.file_sha256(RUNNER_PATH)
    assert manifest["preregistration"]["file_sha256"] == protocol.file_sha256(REPO_ROOT / manifest["preregistration"]["path"])


def test_new_pair_and_evidence_are_independent_from_frozen_184_identity() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    parent = _load(PARENT_MANIFEST_PATH)
    assert manifest["schedule"][0]["pair_id"] != parent["schedule"][0]["pair_id"]
    assert manifest["evidence"]["directory"] != parent["evidence"]["directory"]
    assert manifest["historical_evidence"]["directory"] == parent["evidence"]["directory"]
    assert manifest["historical_evidence"]["reuse_forbidden"] is True
    assert manifest["schedule"][0]["historical_pair_relationship"] == "independent_amendment_not_retry_replacement_backfill_or_extension"
    evidence = manifest["evidence"]
    identity = {key: value for key, value in evidence.items() if key != "identity_sha256"}
    assert evidence["identity_sha256"] == protocol.canonical_sha256(identity)


def test_runtime_parity_contract_and_budget_are_frozen() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    parity = manifest["runtime_parity"]
    assert parity["measurement_classification"] == "measurement_policy_censored"
    assert parity["intervention_classification"] == "intervention_delivery_failure"
    assert parity["parent_submit_uses_bound_wrapper"] is True
    assert parity["fence_released_before_capture"] is True
    assert parity["action_limits"] == {"inspection": 4, "repair_build": 2, "artifact_stage": 2, "submit": 2}
    assert parity["atomic_budget_claim"] is True
    assert parity["parallel_tool_calls"] is False
    assert parity["repair_build_directory"] == manifest["case"]["build_directory"]
    assert parity["repair_build_target"] == manifest["case"]["target"]
    assert manifest["budget"]["stage_maximum_recorded_tokens"] == 245_000


def test_all_real_execution_authorizations_and_runtime_capabilities_are_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    assert authorization["candidate_generation_authorized"] is True
    assert authorization["zero_provider_preflight_authorized"] is True
    for key in (
        "reachability_request_authorized",
        "provider_calls_authorized",
        "formal_attempts_authorized",
        "canary_collection_authorized",
        "credential_read_authorized",
    ):
        assert authorization[key] is False
    assert authorization["model_tokens_authorized"] == 0
    runtime = manifest["runtime_adapter"]
    assert runtime["commands"] == ["validate", "plan", "preflight"]
    assert runtime["credential_read_supported"] is False
    assert runtime["provider_model_creation_supported"] is False
    assert runtime["reachability_execute_supported"] is False
    assert runtime["pair_execute_supported"] is False


def test_valid_preflight_snapshot_and_plan_are_zero_provider() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert runner.validate_preflight_snapshot(manifest, _valid_snapshot(manifest))["network_medium"] == "wifi"
    plan = runner.build_plan(manifest)
    assert plan["action_limits"] == manifest["runtime_parity"]["action_limits"]
    assert plan["parallel_tool_calls"] is False
    assert (plan["provider_calls"], plan["formal_attempts"], plan["model_tokens"], plan["evidence_writes"]) == (0, 0, 0, 0)
    assert plan["execution_authorized"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("branch", "research/188"),
        ("origin_main_commit", "b" * 40),
        ("worktree_clean", False),
        ("authorization_baseline_ancestor", False),
        ("docker_provider", "desktop-linux"),
        ("docker_endpoint", "npipe:////./pipe/docker_engine"),
        ("network_medium", "unknown"),
        ("candidate_evidence_entries", 1),
        ("historical_canary_report_sha256", "0" * 64),
        ("managed_orphans", ["deerflow-compile-stale"]),
    ],
)
def test_preflight_drift_fails_closed(field: str, value: object) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    snapshot = _valid_snapshot(manifest)
    snapshot[field] = value
    with pytest.raises(runner.RuntimeGateError):
        runner.validate_preflight_snapshot(manifest, snapshot)


def test_collector_is_read_only_and_checks_historical_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    sessions = tmp_path / ".compile-sessions"
    candidate = sessions / Path(manifest["evidence"]["directory"]).name
    historical = sessions / Path(manifest["historical_evidence"]["directory"]).name
    report = historical / manifest["historical_evidence"]["canary_report"]
    report.parent.mkdir(parents=True)
    report.write_bytes(b"frozen historical evidence")
    monkeypatch.setattr(runner.protocol, "validate_manifest", lambda _manifest, _repo_root=None: _manifest)
    monkeypatch.setattr(runner, "_file_sha256", lambda _path: manifest["historical_evidence"]["canary_report_sha256"])
    commands: list[tuple[str, ...]] = []

    def fake_command(command, _cwd: Path) -> str:
        key = tuple(command)
        commands.append(key)
        if key == ("git", "branch", "--show-current"):
            return "main"
        if key in (("git", "rev-parse", "HEAD"), ("git", "rev-parse", "origin/main")):
            return "c" * 40
        if key == ("docker", "ps", "-a", "--format", "{{.Names}}"):
            return "deer-flow-langgraph\nunrelated-service"
        if key[0:3] == ("git", "merge-base", "--is-ancestor") or key == ("git", "status", "--porcelain"):
            return ""
        if key[0] == "bash":
            return "OK: Forge Docker daemon provider=ubuntu-native; context=default; endpoint=/var/run/docker.sock"
        raise AssertionError(key)

    snapshot = runner.collect_preflight_snapshot(
        manifest,
        repo_root=tmp_path,
        host_candidate_evidence_directory=candidate,
        host_historical_evidence_directory=historical,
        network_medium="wifi",
        command_runner=fake_command,
    )
    assert snapshot["candidate_evidence_entries"] == 0
    assert snapshot["managed_orphans"] == []
    assert all(command[0] in {"git", "bash", "docker"} for command in commands)
    assert not candidate.exists()

    with pytest.raises(runner.RuntimeGateError, match="not bound"):
        runner.collect_preflight_snapshot(
            manifest,
            repo_root=tmp_path,
            host_candidate_evidence_directory=tmp_path / candidate.name,
            host_historical_evidence_directory=historical,
            network_medium="wifi",
            command_runner=fake_command,
        )


def test_execute_paths_are_mechanically_rejected_and_source_reads_no_credentials() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    with pytest.raises(runner.RuntimeGateError, match="not authorized"):
        runner.execute_reachability(manifest)
    with pytest.raises(runner.RuntimeGateError, match="not authorized"):
        runner.execute_pair(manifest)
    source = RUNNER_PATH.read_text(encoding="utf-8")
    for forbidden in ("os.environ", "os.getenv", "create_chat_model", "ChatOpenAI", "ChatDeepSeek", "api_key="):
        assert forbidden not in source


def test_schema_and_semantics_reject_authorization_runtime_or_evidence_drift() -> None:
    schema = _load(SCHEMA_PATH)
    manifest = _load(MANIFEST_PATH)
    for mutation in (
        ("authorization", "provider_calls_authorized", True),
        ("runtime_parity", "parallel_tool_calls", True),
        ("historical_evidence", "canary_report_sha256", "0" * 64),
    ):
        drifted = copy.deepcopy(manifest)
        drifted[mutation[0]][mutation[1]] = mutation[2]
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
            protocol.validate_manifest(drifted, REPO_ROOT)
