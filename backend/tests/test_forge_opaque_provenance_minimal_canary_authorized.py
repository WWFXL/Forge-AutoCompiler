"""Issue #182 授权候选与零 provider runtime adapter 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_minimal_canary_authorized_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_minimal_canary_authorized_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-minimal-canary-authorized.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-minimal-canary-authorized.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_opaque_provenance_minimal_canary_authorized_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_opaque_provenance_minimal_canary_authorized_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _valid_snapshot(manifest: dict) -> dict:
    return {
        "schema_version": "forge-opaque-provenance-minimal-canary-preflight-1.0.0",
        "branch": "main",
        "head_commit": "a" * 40,
        "origin_main_commit": "a" * 40,
        "worktree_clean": True,
        "authorization_baseline_ancestor": True,
        "docker_provider": "ubuntu-native",
        "docker_context": "default",
        "docker_endpoint": "/var/run/docker.sock",
        "network_medium": "wifi",
        "evidence_directory": manifest["evidence"]["directory"],
        "evidence_entries": 0,
        "managed_orphans": [],
    }


def test_generated_manifest_schema_parent_and_runtime_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["parent"]["canonical_sha256"] == protocol.PARENT_MANIFEST_SHA256
    assert manifest["runtime_adapter"]["file_sha256"] == protocol.file_sha256(RUNNER_PATH)


def test_evidence_and_single_opportunity_identity_are_immutable() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    evidence = manifest["evidence"]
    identity = {key: value for key, value in evidence.items() if key != "identity_sha256"}
    assert evidence["identity_sha256"] == protocol.canonical_sha256(identity)
    assert evidence["directory"].endswith("authorized-v1")
    assert evidence["zero_provider_preflight_writes_evidence"] is False
    assert manifest["opportunities"]["maximum_reachability_requests"] == 1
    assert manifest["opportunities"]["maximum_canary_pairs"] == 1
    assert manifest["opportunities"]["required_order"] == ["reachability", manifest["schedule"][0]["pair_id"]]


def test_all_real_execution_authorizations_are_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    assert authorization["runtime_adapter_candidate_authorized"] is True
    assert authorization["zero_provider_preflight_authorized"] is True
    assert authorization["reachability_request_authorized"] is False
    assert authorization["provider_calls_authorized"] is False
    assert authorization["formal_attempts_authorized"] is False
    assert authorization["canary_collection_authorized"] is False
    assert authorization["model_tokens_authorized"] == 0
    assert manifest["runtime_adapter"]["credential_read_supported"] is False
    assert manifest["runtime_adapter"]["provider_model_creation_supported"] is False


def test_valid_preflight_snapshot_and_plan_are_zero_provider() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert runner.validate_preflight_snapshot(manifest, _valid_snapshot(manifest))["network_medium"] == "wifi"
    plan = runner.build_plan(manifest)
    assert plan["provider_calls"] == 0
    assert plan["formal_attempts"] == 0
    assert plan["model_tokens"] == 0
    assert plan["evidence_writes"] == 0
    assert plan["execution_authorized"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("branch", "research/issue-182"),
        ("origin_main_commit", "b" * 40),
        ("worktree_clean", False),
        ("authorization_baseline_ancestor", False),
        ("docker_provider", "desktop-linux"),
        ("docker_endpoint", "npipe:////./pipe/docker_engine"),
        ("network_medium", "unknown"),
        ("evidence_entries", 1),
        ("managed_orphans", ["deerflow-compile-stale"]),
    ],
)
def test_preflight_drift_fails_closed(field: str, value: object) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    snapshot = _valid_snapshot(manifest)
    snapshot[field] = value
    with pytest.raises(runner.RuntimeGateError):
        runner.validate_preflight_snapshot(manifest, snapshot)


def test_collector_uses_read_only_git_docker_and_evidence_checks() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    evidence_dir = REPO_ROOT / ".compile-sessions" / Path(manifest["evidence"]["directory"]).name
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
        repo_root=REPO_ROOT,
        host_evidence_directory=evidence_dir,
        network_medium="wifi",
        command_runner=fake_command,
    )
    assert snapshot["evidence_entries"] == 0
    assert snapshot["managed_orphans"] == []
    assert all(command[0] in {"git", "bash", "docker"} for command in commands)

    with pytest.raises(runner.RuntimeGateError, match="not bound"):
        runner.collect_preflight_snapshot(
            manifest,
            repo_root=REPO_ROOT,
            host_evidence_directory=REPO_ROOT.parent / evidence_dir.name,
            network_medium="wifi",
            command_runner=fake_command,
        )


def test_execute_paths_are_mechanically_rejected_and_source_reads_no_credentials() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    with pytest.raises(runner.RuntimeGateError, match="not authorized"):
        runner.execute_reachability(manifest)
    with pytest.raises(runner.RuntimeGateError, match="not authorized"):
        runner.execute_canary(manifest)
    source = RUNNER_PATH.read_text(encoding="utf-8")
    for forbidden in ("os.environ", "create_chat_model", "ChatOpenAI", "DEEPSEEK_API_KEY", "api_key="):
        assert forbidden not in source


def test_schema_and_semantics_reject_authorization_or_evidence_drift() -> None:
    schema = _load(SCHEMA_PATH)
    manifest = _load(MANIFEST_PATH)
    drifted = copy.deepcopy(manifest)
    drifted["authorization"]["provider_calls_authorized"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(drifted)
    with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
        protocol.validate_manifest(drifted, REPO_ROOT)

    drifted = copy.deepcopy(manifest)
    drifted["evidence"]["canary_report"] = "reports/other.json"
    with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
        protocol.validate_manifest(drifted, REPO_ROOT)
