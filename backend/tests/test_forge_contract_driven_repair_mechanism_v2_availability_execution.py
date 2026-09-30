"""Issue #371 mechanism v2 availability 授权执行身份与 marker 门禁。"""

from __future__ import annotations

import copy
import json
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

import forge_contract_driven_repair_mechanism_v2_availability_execution_protocol as protocol  # noqa: E402
import forge_contract_driven_repair_mechanism_v2_availability_execution_runner as runner  # noqa: E402

SCHEMA_PATH = REPO_ROOT / protocol.SCHEMA_PATH
PREREGISTRATION_PATH = REPO_ROOT / protocol.PREREGISTRATION_PATH


def _load_json(path: Path) -> dict[str, Any]:
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


@pytest.fixture(scope="session")
def manifest() -> dict[str, Any]:
    return protocol.load_manifest()


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
        runner.parent_runner.candidate_runner.base,
        "_require_zero_managed_resources",
        lambda: None,
    )


def test_manifest_schema_and_parent_release_are_deterministic(
    manifest: dict[str, Any],
) -> None:
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    schema = _load_json(SCHEMA_PATH)
    assert schema == protocol.generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)
    delta = protocol.validate_allowed_delta(manifest)
    assert delta["status"] == "passed"
    assert delta["parent_manifest_canonical_sha256"] == (protocol.PARENT_MANIFEST_CANONICAL_SHA256)
    assert delta["release_bound_identity_revision"] == (protocol.RELEASE_BOUND_IDENTITY_REVISION)


def test_science_schedule_ids_and_request_are_inherited(
    manifest: dict[str, Any],
) -> None:
    parent = protocol._parent_manifest(REPO_ROOT)
    for field in protocol.parent.candidate.source.parent.parent.parent.SCIENTIFIC_CONTRACT_FIELDS:
        assert manifest[field] == parent[field]
    assert manifest["schedule"] == parent["schedule"]
    assert manifest["independent_identity"] == parent["independent_identity"]
    assert manifest["formal_execution_tasks"] == parent["formal_execution_tasks"]
    assert manifest["formal_execution"] == parent["formal_execution"]
    assert manifest["availability_execution"]["contract"] == (parent["availability_execution"]["contract"])
    assert manifest["candidate_evidence"]["directory"] == (parent["candidate_evidence"]["directory"])
    assert manifest["parent_release_bound_identity"]["historical_evidence_reused"] is False


def test_only_availability_provider_and_marker_actions_are_authorized(
    manifest: dict[str, Any],
) -> None:
    authorization = manifest["authorization"]
    for field in (
        "identity_implementation_authorized",
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
        "availability_execution_completed",
        "docker_session_creation_authorized",
        "formal_collection_execution_authorized",
        "formal_attempts_authorized",
        "formal_evidence_write_authorized",
        "execution_started",
    ):
        assert authorization[field] is False
    execution = manifest["availability_execution"]
    assert execution["provider"] == "deepseek"
    assert execution["provider_profile"] == "deepseek-flash"
    assert execution["actual_model"] == "deepseek-flash"
    assert execution["max_recorded_tokens"] is None
    assert execution["sdk_retry_count"] == 0
    assert execution["formal_batch_creation_authorized"] is False
    assert manifest["candidate_evidence"]["authorized_write_paths"] == ["markers/availability.json"]


def test_availability_success_writes_one_safe_create_once_marker(
    manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_zero_response_zero_token_exception_allows_one_retry(
    manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


@pytest.mark.parametrize(
    ("response", "terminal_error"),
    [
        (_response("NOT_READY"), "AvailabilityResponseInvalid"),
        (_response(model="deepseek-chat"), "AvailabilityResponseInvalid"),
    ],
)
def test_observed_invalid_response_is_not_retried(
    manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: SimpleNamespace,
    terminal_error: str,
) -> None:
    output_dir = tmp_path / "evidence"
    _mock_execution_preflight(monkeypatch, output_dir)

    class Model:
        calls = 0

        def invoke(self, prompt: str):
            self.calls += 1
            return response

    model = Model()
    with pytest.raises(runner.AvailabilityExecutionRunnerError, match="formal batch 保持关闭"):
        runner.execute_availability(
            manifest,
            output_dir=output_dir,
            repo_root=REPO_ROOT,
            model_factory=lambda value: model,
        )

    marker = _load_json(output_dir / "markers/availability.json")
    assert model.calls == 1
    assert marker["status"] == "failed"
    assert marker["error_class"] == terminal_error
    assert marker["attempts"][0]["retry_eligible"] is False


def test_existing_marker_blocks_before_model_creation(
    manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "evidence"
    marker_path = output_dir / "markers/availability.json"
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text("{}\n", encoding="utf-8")
    _mock_execution_preflight(monkeypatch, output_dir)

    def forbidden(value):
        raise AssertionError("marker 存在时不得创建模型")

    with pytest.raises(runner.AvailabilityExecutionRunnerError, match="不可覆盖"):
        runner.execute_availability(
            manifest,
            output_dir=output_dir,
            repo_root=REPO_ROOT,
            model_factory=forbidden,
        )


def test_passed_marker_audit_is_read_only(
    manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    marker_path = output_dir / "markers/availability.json"
    before = marker_path.read_bytes()
    monkeypatch.setattr(runner, "_output_dir", lambda value, path, root: path)

    audit = runner.audit_availability(manifest, output_dir=output_dir, repo_root=REPO_ROOT)

    assert audit["availability_status"] == "passed"
    assert audit["request_attempt_count"] == 1
    assert audit["recorded_total_tokens"] == 11
    assert marker_path.read_bytes() == before


def test_audit_rejects_token_aggregate_tamper(
    manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    marker_path = output_dir / "markers/availability.json"
    marker = _load_json(marker_path)
    marker["recorded_total_tokens"] += 1
    marker_path.write_text(
        json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "_output_dir", lambda value, path, root: path)

    with pytest.raises(runner.AvailabilityExecutionRunnerError, match="token 汇总"):
        runner.audit_availability(manifest, output_dir=output_dir, repo_root=REPO_ROOT)


def test_preflight_includes_credential_presence_and_v1_inventory(
    manifest: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".compile-sessions").mkdir(parents=True)
    output_dir = workspace / manifest["candidate_evidence"]["directory"]
    monkeypatch.setattr(
        runner,
        "_require_execution_release",
        lambda _root: {
            "revision": "a" * 40,
            "branch": "main",
            "origin_main": "a" * 40,
        },
    )
    monkeypatch.setattr(
        runner.parent_runner.candidate_runner,
        "_require_docker_identity",
        lambda _manifest, _root: manifest["environment_identity"]["image_id"],
    )
    monkeypatch.setattr(
        runner.parent_runner.candidate_runner.base,
        "_require_zero_managed_resources",
        lambda: None,
    )
    monkeypatch.setattr(
        runner.parent_runner.candidate_runner,
        "_require_old_evidence_read_only",
        lambda _root: {
            "inventory_sha256": protocol.parent.candidate.FAILED_EVIDENCE_INVENTORY_SHA256,
            "read_only": True,
            "imported": False,
        },
    )
    monkeypatch.setattr(
        runner.parent_runner.candidate_runner,
        "_require_new_evidence_absent",
        lambda _manifest, _root: output_dir,
    )
    monkeypatch.setattr(runner, "_provider_config_preflight", lambda _manifest: None)
    monkeypatch.setattr(runner, "_output_dir", lambda value, path, root: output_dir)

    result = runner.collect_preflight(manifest, output_dir=output_dir, repo_root=REPO_ROOT)

    assert result["ready"] is True
    assert result["credential_check"] == "environment_variable_presence_only"
    assert result["old_evidence"]["inventory_sha256"] == (protocol.parent.candidate.FAILED_EVIDENCE_INVENTORY_SHA256)
    assert result["evidence_directory_absent"] is True
    assert result["provider_calls"] == result["formal_evidence_writes"] == 0


def test_execution_release_requires_clean_main_equal_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], *, cwd: Path) -> str:
        command = tuple(argv)
        if command == ("git", "rev-parse", "HEAD"):
            return "b" * 40
        if command == ("git", "rev-parse", "refs/remotes/origin/main"):
            return "c" * 40
        if command == ("git", "branch", "--show-current"):
            return "feature"
        if command[:3] == ("git", "merge-base", "--is-ancestor"):
            return ""
        if command[:2] == ("git", "status"):
            return ""
        raise AssertionError(command)

    monkeypatch.setattr(runner, "_run_checked", fake_run)

    with pytest.raises(runner.AvailabilityExecutionRunnerError, match="main == origin/main"):
        runner._require_execution_release(REPO_ROOT)


@pytest.mark.parametrize("command", runner.BLOCKED_COMMANDS)
def test_formal_commands_fail_before_manifest_or_runtime_probe(command: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("formal command 必须在 manifest/runtime probe 前失败")

    monkeypatch.setattr(protocol, "load_manifest", forbidden)
    monkeypatch.setattr(runner, "_run_checked", forbidden)

    with pytest.raises(runner.AvailabilityExecutionRunnerError, match="独立身份"):
        runner.main([command])


def test_manifest_tamper_fails_closed(manifest: dict[str, Any]) -> None:
    tampered = copy.deepcopy(manifest)
    tampered["authorization"]["formal_collection_execution_authorized"] = True

    with pytest.raises(protocol.AvailabilityExecutionProtocolError, match="确定性生成结果"):
        protocol.validate_manifest(tampered, REPO_ROOT)


def test_preregistration_records_authorization_and_claim_boundary() -> None:
    preregistration = PREREGISTRATION_PATH.read_text(encoding="utf-8")
    assert protocol.RELEASE_BOUND_IDENTITY_REVISION in preregistration
    assert protocol.PARENT_MANIFEST_CANONICAL_SHA256 in preregistration
    assert "仅当第一次为 0 response、0 recorded tokens、0 tool side effects" in preregistration
    assert "不能解释为模型能力、可靠性、arm outcome、treatment effect" in preregistration
