"""Issue #359 availability 授权执行身份、marker 与 retry 门禁。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_availability_execution_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_availability_execution_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-availability-execution.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-availability-execution.schema.json"


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
    "forge_contract_driven_repair_mechanism_v1_availability_execution_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_contract_driven_repair_mechanism_v1_availability_execution_runner_test",
    RUNNER_PATH,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _response(
    content: str = "FORGE_READY",
    *,
    model: str = "deepseek-flash",
    input_tokens: int = 8,
    output_tokens: int = 3,
    total_tokens: int = 11,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        response_metadata={"model_name": model},
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    )


def _mock_execution_preflight(monkeypatch: pytest.MonkeyPatch, output_dir: Path) -> None:
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda manifest, *, output_dir, repo_root: {
            "ready": True,
            "observed_execution_revision": "b" * 40,
        },
    )
    monkeypatch.setattr(
        runner.candidate_runner.parent_runner,
        "_require_zero_managed_resources",
        lambda root: None,
    )


def test_manifest_schema_and_parent_release_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.load_manifest(repo_root=REPO_ROOT) == manifest
    assert manifest["parent_availability_candidate"]["manifest_canonical_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256
    assert manifest["development_revision"]["availability_candidate_release_revision"] == protocol.AVAILABILITY_CANDIDATE_RELEASE_REVISION


def test_scientific_contract_and_availability_request_are_inherited() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    parent = protocol.parent.load_manifest(repo_root=REPO_ROOT)

    for field in protocol.parent.parent.SCIENTIFIC_CONTRACT_FIELDS:
        assert manifest[field] == parent[field]
    assert manifest["availability_execution"]["contract"] == parent["availability_candidate"]["contract"]
    assert manifest["candidate_evidence"]["directory"] == parent["candidate_evidence"]["directory"]


def test_only_availability_provider_and_marker_actions_are_authorized() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    authorization = manifest["authorization"]
    execution = manifest["availability_execution"]

    for field in (
        "availability_execution_implementation_authorized",
        "availability_execution_authorized",
        "credential_read_authorized",
        "provider_calls_authorized",
        "model_creation_authorized",
        "model_tokens_authorized",
        "availability_marker_write_authorized",
    ):
        assert authorization[field] is True
    for field in (
        "formal_collection_execution_authorized",
        "docker_session_creation_authorized",
        "formal_attempts_authorized",
        "formal_evidence_write_authorized",
        "execution_started",
    ):
        assert authorization[field] is False
    assert manifest["candidate_evidence"]["authorized_write_paths"] == ["markers/availability.json"]
    assert execution["provider"] == "deepseek"
    assert execution["provider_profile"] == "deepseek-flash"
    assert execution["actual_model"] == "deepseek-flash"
    assert execution["max_recorded_tokens"] is None
    assert execution["sdk_retry_count"] == 0
    assert execution["formal_batch_creation_authorized"] is False


def test_availability_success_writes_one_safe_create_once_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    output_dir = tmp_path / "evidence"
    _mock_execution_preflight(monkeypatch, output_dir)

    class Model:
        streaming = False

        def invoke(self, prompt: str):
            assert prompt == "Reply exactly with FORGE_READY."
            return _response()

    marker = runner.execute_availability(
        manifest,
        output_dir=output_dir,
        repo_root=REPO_ROOT,
        model_factory=lambda value: Model(),
    )

    assert marker["status"] == "passed"
    assert marker["request_attempt_count"] == 1
    assert marker["recorded_total_tokens"] == 11
    assert marker["attempts"][0]["response_sha256"] is not None
    assert "FORGE_READY" not in json.dumps(marker)
    assert "credential" not in json.dumps(marker).lower()


def test_zero_response_zero_token_exception_allows_one_transport_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    output_dir = tmp_path / "evidence"
    _mock_execution_preflight(monkeypatch, output_dir)

    class Model:
        calls = 0

        def invoke(self, prompt: str):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("private provider detail")
            return _response()

    model = Model()
    marker = runner.execute_availability(
        manifest,
        output_dir=output_dir,
        repo_root=REPO_ROOT,
        model_factory=lambda value: model,
    )

    assert model.calls == 2
    assert marker["status"] == "passed"
    assert marker["request_attempt_count"] == 2
    assert marker["attempts"][0]["retry_eligible"] is True
    assert marker["attempts"][0]["error_class"] == "TimeoutError"
    assert "private provider detail" not in json.dumps(marker)


def test_nonempty_wrong_response_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    output_dir = tmp_path / "evidence"
    _mock_execution_preflight(monkeypatch, output_dir)

    class Model:
        calls = 0

        def invoke(self, prompt: str):
            self.calls += 1
            return _response("NOT_READY")

    model = Model()
    with pytest.raises(runner.AvailabilityExecutionRunnerError, match="formal batch 保持关闭"):
        runner.execute_availability(
            manifest,
            output_dir=output_dir,
            repo_root=REPO_ROOT,
            model_factory=lambda value: model,
        )

    marker = _load(output_dir / "markers/availability.json")
    assert model.calls == 1
    assert marker["status"] == "failed"
    assert marker["request_attempt_count"] == 1
    assert marker["attempts"][0]["retry_eligible"] is False


def test_existing_marker_blocks_before_model_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    output_dir = tmp_path / "evidence"
    marker_path = output_dir / "markers/availability.json"
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text("{}\n", encoding="utf-8")
    _mock_execution_preflight(monkeypatch, output_dir)

    def forbidden(value):
        raise AssertionError("model must not be created when marker exists")

    with pytest.raises(runner.AvailabilityExecutionRunnerError, match="不可覆盖"):
        runner.execute_availability(
            manifest,
            output_dir=output_dir,
            repo_root=REPO_ROOT,
            model_factory=forbidden,
        )


def test_passed_marker_audit_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    output_dir = tmp_path / "evidence"
    _mock_execution_preflight(monkeypatch, output_dir)

    class Model:
        def invoke(self, prompt: str):
            return _response()

    runner.execute_availability(
        manifest,
        output_dir=output_dir,
        repo_root=REPO_ROOT,
        model_factory=lambda value: Model(),
    )
    before = (output_dir / "markers/availability.json").read_bytes()
    monkeypatch.setattr(runner, "_output_dir", lambda value, path, root: path)

    audit = runner.audit_availability(manifest, output_dir=output_dir, repo_root=REPO_ROOT)

    assert audit["availability_status"] == "passed"
    assert audit["request_attempt_count"] == 1
    assert audit["recorded_total_tokens"] == 11
    assert (output_dir / "markers/availability.json").read_bytes() == before


def test_execution_release_requires_clean_main_equal_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], *, cwd: Path) -> str:
        command = tuple(argv)
        if command == ("git", "rev-parse", "HEAD"):
            return "b" * 40
        if command == ("git", "rev-parse", "origin/main"):
            return "c" * 40
        if command == ("git", "branch", "--show-current"):
            return "feature"
        if command[:3] == ("git", "merge-base", "--is-ancestor"):
            return ""
        if command[:2] == ("git", "status"):
            return ""
        raise AssertionError(command)

    monkeypatch.setattr(runner, "_run_checked", fake_run)

    with pytest.raises(runner.AvailabilityExecutionRunnerError, match="HEAD == origin/main"):
        runner._require_execution_release(REPO_ROOT)


def test_batch_fails_before_manifest_or_runtime_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("batch must fail before manifest or runtime access")

    monkeypatch.setattr(protocol, "load_manifest", forbidden)
    monkeypatch.setattr(runner, "_run_checked", forbidden)

    with pytest.raises(runner.AvailabilityExecutionRunnerError, match="独立身份"):
        runner.main(["batch"])


def test_manifest_tamper_fails_closed() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    tampered = copy.deepcopy(manifest)
    tampered["authorization"]["formal_collection_execution_authorized"] = True

    with pytest.raises(protocol.AvailabilityExecutionProtocolError, match="确定性生成结果"):
        protocol.validate_manifest(tampered, REPO_ROOT)
