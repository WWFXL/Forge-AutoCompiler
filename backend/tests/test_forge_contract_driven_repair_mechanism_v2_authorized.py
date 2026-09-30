"""Issue #369 mechanism v2 release-bound identity 测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forge_contract_driven_repair_mechanism_v2_authorized_protocol as protocol  # noqa: E402
import forge_contract_driven_repair_mechanism_v2_authorized_runner as runner  # noqa: E402

SCHEMA_PATH = REPO_ROOT / protocol.SCHEMA_PATH
PREREGISTRATION_PATH = REPO_ROOT / protocol.PREREGISTRATION_PATH


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture
def manifest() -> dict[str, Any]:
    return protocol.load_manifest()


def test_manifest_schema_and_parent_delta_are_deterministic(
    manifest: dict[str, Any],
) -> None:
    assert manifest == protocol.generate_manifest()
    schema = _load_json(SCHEMA_PATH)
    assert schema == protocol.generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)
    delta = protocol.validate_allowed_delta(manifest)
    assert delta["status"] == "passed"
    assert delta["parent_manifest_sha256"] == (protocol.PARENT_MANIFEST_CANONICAL_SHA256)
    assert delta["arm_count"] == 36
    assert delta["historical_outcomes_imported"] is False
    assert delta["formal_collection_execution_authorized"] is False


def test_release_parent_science_ids_and_evidence_are_exact(
    manifest: dict[str, Any],
) -> None:
    parent = protocol._parent_manifest(REPO_ROOT)
    assert protocol.candidate.candidate.file_sha256(REPO_ROOT / protocol.candidate.MANIFEST_PATH) == protocol.PARENT_MANIFEST_FILE_SHA256
    assert manifest["schedule"] == parent["schedule"]
    assert manifest["candidate_evidence"] == parent["candidate_evidence"]
    assert manifest["independent_identity"] == parent["independent_identity"]
    assert manifest["formal_execution_tasks"] == parent["formal_execution_tasks"]
    assert manifest["development_revision"]["scientific_contract_release_revision"] == protocol.SCIENTIFIC_CONTRACT_RELEASE_REVISION
    assert manifest["parent_candidate"]["read_only"] is True


def test_all_execution_authorizations_are_false(
    manifest: dict[str, Any],
) -> None:
    authorization = manifest["authorization"]
    assert authorization["identity_implementation_authorized"] is True
    assert all(value is False for key, value in authorization.items() if key != "identity_implementation_authorized")
    availability = manifest["availability_execution"]
    for field in (
        "credential_read_authorized",
        "execution_authorized",
        "marker_write_authorized",
        "model_creation_authorized",
        "model_tokens_authorized",
        "provider_calls_authorized",
    ):
        assert availability[field] is False
    for command in runner.BLOCKED_COMMANDS:
        with pytest.raises(runner.AuthorizedRunnerError, match="execution authorization"):
            runner._reject_execution(command)


def test_preflight_is_read_only_and_zero_provider(manifest: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".compile-sessions").mkdir(parents=True)
    monkeypatch.setattr(
        runner,
        "_require_release",
        lambda _root: {
            "revision": "a" * 40,
            "branch": "main",
            "origin_main": "a" * 40,
        },
    )
    monkeypatch.setattr(
        runner.candidate_runner,
        "_require_docker_identity",
        lambda _manifest, _root: manifest["environment_identity"]["image_id"],
    )
    monkeypatch.setattr(
        runner.candidate_runner.base,
        "_require_zero_managed_resources",
        lambda: None,
    )
    result = runner.collect_preflight(manifest, repo_root=REPO_ROOT, workspace_root=workspace)
    assert result["ready"] is True
    assert result["credential_check"] == "not_authorized_not_performed"
    assert result["old_evidence"]["inventory_sha256"] == (protocol.candidate.FAILED_EVIDENCE_INVENTORY_SHA256)
    assert result["old_evidence"]["imported"] is False
    assert result["new_evidence_directory_absent"] is True
    assert result["provider_calls"] == result["formal_evidence_writes"] == 0


def test_preregistration_and_runner_preserve_execution_boundary() -> None:
    preregistration = PREREGISTRATION_PATH.read_text(encoding="utf-8")
    runner_source = (REPO_ROOT / protocol.RUNNER_PATH).read_text(encoding="utf-8")
    assert protocol.SCIENTIFIC_CONTRACT_RELEASE_REVISION in preregistration
    assert protocol.PARENT_MANIFEST_CANONICAL_SHA256 in preregistration
    assert "仍需对一个新的 execution identity 明确授权" in preregistration
    assert "DEEPSEEK_API_KEY" not in runner_source
    assert "create_chat_model" not in runner_source
    assert "execute_batch(" not in runner_source
