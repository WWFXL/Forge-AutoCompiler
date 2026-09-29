"""Issue #357 availability qualification 候选 amendment 门禁。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_availability_candidate_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_availability_candidate_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-availability-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-availability-candidate.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module(
    "forge_contract_driven_repair_mechanism_v1_availability_candidate_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_contract_driven_repair_mechanism_v1_availability_candidate_runner_test",
    RUNNER_PATH,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_and_parent_release_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.load_manifest(repo_root=REPO_ROOT) == manifest
    assert manifest["parent_authorized"]["manifest_canonical_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256
    assert manifest["development_revision"]["authorized_implementation_revision"] == protocol.IMPLEMENTATION_RELEASE_REVISION


def test_scientific_contract_schedule_and_evidence_identity_are_unchanged() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    parent = protocol.parent.load_manifest(repo_root=REPO_ROOT)

    for field in protocol.parent.SCIENTIFIC_CONTRACT_FIELDS:
        assert manifest[field] == parent[field]
    assert manifest["candidate_evidence"] == parent["candidate_evidence"]
    assert manifest["schedule"] == parent["schedule"]
    assert sum(len(item["arms"]) for item in manifest["schedule"]["checkpoints"]) == 36


def test_availability_contract_is_exact_and_execution_remains_closed() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    availability = manifest["availability_candidate"]
    contract = availability["contract"]

    assert availability["provider_profile"] == "deepseek-flash"
    assert availability["actual_model"] == "deepseek-flash"
    assert availability["max_recorded_tokens"] is None
    assert contract == {
        "before_formal_marker": True,
        "logical_request_count": 1,
        "max_request_attempts_including_transport_retry": 2,
        "request": "Reply exactly with FORGE_READY.",
        "expected_response": "FORGE_READY",
        "experiment_content_included": False,
        "transport_retry_policy_applies": True,
        "failure_creates_batch": False,
        "request_attempts_count_toward_formal_arm_budget": False,
    }
    assert manifest["authorization"]["availability_execution_authorized"] is False
    assert manifest["authorization"]["formal_collection_execution_authorized"] is False
    for field in (
        "credential_read_authorized",
        "provider_calls_authorized",
        "model_creation_authorized",
        "docker_session_creation_authorized",
        "formal_attempts_authorized",
        "formal_evidence_write_authorized",
        "model_tokens_authorized",
        "execution_started",
    ):
        assert manifest["authorization"][field] is False


def _fake_git_preflight(monkeypatch: pytest.MonkeyPatch, *, dirty: bool = False) -> None:
    def fake_run(argv: list[str], *, cwd: Path) -> str:
        assert cwd == REPO_ROOT
        command = tuple(argv)
        if command == ("git", "rev-parse", "HEAD"):
            return "b" * 40
        if command[:3] == ("git", "merge-base", "--is-ancestor"):
            assert command[3] == protocol.IMPLEMENTATION_RELEASE_REVISION
            return ""
        if command[:2] == ("git", "status"):
            return " M tracked" if dirty else ""
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(runner, "_run_checked", fake_run)


def test_non_model_preflight_binds_implementation_and_parent_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    evidence = tmp_path / manifest["candidate_evidence"]["directory"]
    _fake_git_preflight(monkeypatch)
    monkeypatch.setattr(
        runner.parent_runner,
        "_require_docker_identity",
        lambda value, root: protocol.parent.COMPILE_IMAGE_ID,
    )
    monkeypatch.setattr(runner.parent_runner, "_require_zero_managed_resources", lambda root: None)
    monkeypatch.setattr(
        runner.parent_runner,
        "_require_evidence_absent",
        lambda value, root: evidence,
    )

    result = runner.collect_preflight(manifest, repo_root=REPO_ROOT, workspace_root=tmp_path)

    assert result["ready"] is True
    assert result["observed_clean_descendant_revision"] == "b" * 40
    assert result["compile_image_id"] == protocol.parent.COMPILE_IMAGE_ID
    assert result["availability_execution_authorized"] is False
    for field in (
        "provider_calls",
        "credential_reads",
        "docker_sessions_created",
        "formal_attempts",
        "formal_evidence_writes",
        "model_tokens",
    ):
        assert result[field] == 0
    assert not Path(result["evidence_directory"]).exists()


def test_preflight_fails_closed_on_dirty_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_git_preflight(monkeypatch, dirty=True)

    with pytest.raises(runner.AvailabilityCandidateRunnerError, match="干净工作树"):
        runner._require_release(REPO_ROOT)


def test_availability_and_batch_fail_before_manifest_or_runtime_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("blocked command must not load identity or probe runtime")

    monkeypatch.setattr(protocol, "load_manifest", forbidden)
    monkeypatch.setattr(runner, "_run_checked", forbidden)
    for action in (runner.execute_availability, runner.run_batch):
        with pytest.raises(
            runner.AvailabilityCandidateRunnerError,
            match="尚未获得独立执行授权",
        ):
            action()


def test_manifest_tamper_fails_closed() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    tampered = copy.deepcopy(manifest)
    tampered["authorization"]["provider_calls_authorized"] = True

    with pytest.raises(protocol.AvailabilityCandidateProtocolError, match="确定性生成结果"):
        protocol.validate_manifest(tampered, REPO_ROOT)


def test_runner_source_has_no_credential_or_provider_factory_access() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert "os.environ" not in source
    assert "get_app_config" not in source
    assert "create_chat_model" not in source
    assert "DEEPSEEK_API_KEY" not in source
    assert "ExperimentLedger" not in source
