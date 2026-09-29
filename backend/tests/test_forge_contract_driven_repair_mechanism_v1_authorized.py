"""Issue #355 release-bound identity 与零执行 preflight 门禁。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_authorized_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_authorized_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-authorized.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-authorized.schema.json"


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
    "forge_contract_driven_repair_mechanism_v1_authorized_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_contract_driven_repair_mechanism_v1_authorized_runner_test",
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
    assert manifest["parent_candidate"]["manifest_canonical_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256
    assert manifest["development_revision"]["scientific_contract_release_revision"] == protocol.SCIENTIFIC_CONTRACT_RELEASE_REVISION


def test_scientific_contract_and_schedule_are_inherited_without_change() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    parent = protocol.candidate.load_manifest(repo_root=REPO_ROOT)

    for field in protocol.SCIENTIFIC_CONTRACT_FIELDS:
        assert manifest[field] == parent[field]
    assert manifest["schedule"] == parent["schedule"]
    assert len(manifest["schedule"]["projects"]) == 6
    assert len(manifest["schedule"]["checkpoints"]) == 12
    assert sum(len(item["arms"]) for item in manifest["schedule"]["checkpoints"]) == 36


def test_execution_authorizations_remain_closed() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    authorization = manifest["authorization"]

    assert authorization["identity_implementation_authorized"] is True
    assert all(value is False for key, value in authorization.items() if key != "identity_implementation_authorized")
    assert manifest["development_revision"]["authorized_implementation_revision"] is None
    assert manifest["candidate_evidence"]["writes_authorized"] is False
    assert manifest["candidate_evidence"]["must_not_exist_before_authorized_marker"] is True


def test_environment_and_create_once_evidence_are_frozen() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)

    assert manifest["environment_identity"]["compile_image"] == "autocompiler:stage-c-v1"
    assert manifest["environment_identity"]["image_id"] == protocol.COMPILE_IMAGE_ID
    assert manifest["candidate_evidence"]["directory"] == protocol.EVIDENCE_DIRECTORY
    assert manifest["parent_candidate"]["historical_evidence_reused"] is False
    assert manifest["parent_candidate"]["historical_outcomes_imported"] is False


def _fake_preflight(monkeypatch: pytest.MonkeyPatch, *, dirty: bool = False, image_id: str | None = None, managed: bool = False) -> None:
    def fake_run(argv: list[str], *, cwd: Path) -> str:
        assert cwd == REPO_ROOT
        command = tuple(argv)
        if command == ("git", "rev-parse", "HEAD"):
            return "b" * 40
        if command[:3] == ("git", "merge-base", "--is-ancestor"):
            return ""
        if command[:2] == ("git", "status"):
            return " M tracked" if dirty else ""
        if command[0] == "bash":
            return "Docker runtime ready"
        if command[:3] == ("docker", "image", "inspect"):
            return image_id or protocol.COMPILE_IMAGE_ID
        if command[:3] == ("docker", "ps", "-a"):
            return "deerflow-compile-orphan" if managed else ""
        return ""

    monkeypatch.setattr(runner, "_run_checked", fake_run)


def test_non_model_preflight_reads_only_release_docker_and_empty_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    (tmp_path / ".compile-sessions").mkdir()
    _fake_preflight(monkeypatch)

    result = runner.collect_preflight(manifest, repo_root=REPO_ROOT, workspace_root=tmp_path)

    assert result["ready"] is True
    assert result["observed_clean_descendant_revision"] == "b" * 40
    assert result["compile_image_id"] == protocol.COMPILE_IMAGE_ID
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


@pytest.mark.parametrize("failure", ["dirty", "image", "managed", "evidence"])
def test_preflight_fails_closed_on_release_or_resource_drift(failure: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    (tmp_path / ".compile-sessions").mkdir()
    _fake_preflight(
        monkeypatch,
        dirty=failure == "dirty",
        image_id="sha256:" + "0" * 64 if failure == "image" else None,
        managed=failure == "managed",
    )
    if failure == "evidence":
        (tmp_path / protocol.EVIDENCE_DIRECTORY).mkdir()

    with pytest.raises(runner.AuthorizedRunnerError):
        runner.collect_preflight(manifest, repo_root=REPO_ROOT, workspace_root=tmp_path)


def test_availability_and_batch_fail_before_any_runtime_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("blocked command must not load identity or probe runtime")

    monkeypatch.setattr(protocol, "load_manifest", forbidden)
    monkeypatch.setattr(runner, "_run_checked", forbidden)
    for action in (runner.execute_availability, runner.run_batch):
        with pytest.raises(runner.AuthorizedRunnerError, match="尚未获得独立执行授权"):
            action()


def test_manifest_tamper_fails_closed() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    tampered = copy.deepcopy(manifest)
    tampered["authorization"]["provider_calls_authorized"] = True

    with pytest.raises(protocol.AuthorizedProtocolError, match="确定性生成结果"):
        protocol.validate_manifest(tampered, REPO_ROOT)


def test_runner_source_has_no_credential_or_provider_factory_access() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert "os.environ" not in source
    assert "get_app_config" not in source
    assert "create_chat_model" not in source
    assert "DEEPSEEK_API_KEY" not in source
    assert "ExperimentLedger" not in source
