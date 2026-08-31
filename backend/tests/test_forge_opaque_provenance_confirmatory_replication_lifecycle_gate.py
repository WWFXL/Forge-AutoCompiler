"""Issue #245 independent replication lifecycle 的零 provider 静态门禁。"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
GATE_PATH = SCRIPTS / "forge_opaque_provenance_confirmatory_replication_lifecycle_gate.py"


def _load_gate():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("forge_confirmatory_replication_lifecycle_gate_test", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def test_gate_contract_freezes_replication_identity_without_provider_work() -> None:
    result = gate.validate_gate_contract(REPO_ROOT)

    assert result == {
        "schema_version": "forge-opaque-provenance-confirmatory-replication-lifecycle-gate-1.0.0",
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/245",
        "status": "passed",
        "candidate_manifest_sha256": "7b1817becba4ec57eb9726be0e1faaa5427af309dca7552634e3f6a3a1b5d938",
        "candidate_manifest_file_sha256": "b6eb90bfc5242dec1881627101de3c0c4589c5863700293d92bec80bea2de324",
        "evidence_identity_sha256": "b136cc5669384176853f00b878dae207d89b7bce593cc8e5f1ff9ab06505b9bc",
        "schedule_identity_sha256": "3f35dd8c245cb7e9db6069f63cf133c98fbfdf6813a11e3fa2306a5eb34c2134",
        "case_count": 6,
        "pair_count": 12,
        "build_systems": ["cmake", "make"],
        "capture_before_commit_cleanup_required": True,
        "broad_docker_cleanup_forbidden": True,
        "historical_outcomes_imported": False,
        "provider_calls": 0,
        "credential_read": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "formal_evidence_writes": 0,
        "docker_executed": False,
    }


def test_zero_provider_runtime_is_ephemeral_and_fail_closed(tmp_path: Path) -> None:
    manifest = gate.load_candidate(REPO_ROOT)
    runtime = gate.build_zero_provider_runtime_manifest(manifest, tmp_path / "gate", repo_root=REPO_ROOT)

    provider = runtime["authorized_execution"]["provider"]
    assert provider["status"] == "deterministic_zero_provider_gate"
    assert provider["model"] == "deterministic-zero-provider"
    assert provider["endpoint"] == "https://example.invalid/v1"
    assert provider["credential_env"] == "UNUSED_ZERO_PROVIDER_CREDENTIAL"
    assert provider["request_timeout_seconds"] == 1
    assert provider["max_retries"] == 0
    assert runtime["authorization"] == manifest["authorization"]
    assert runtime["gate_context"]["model_tokens_authorized"] == 0
    assert runtime["authorized_execution"]["evidence"]["directory"] == str(tmp_path / "gate")
    with pytest.raises(gate.ReplicationLifecycleGateError, match="不得写入正式"):
        gate.build_zero_provider_runtime_manifest(
            manifest,
            Path(manifest["replication_candidate"]["evidence_candidate"]["directory"]) / "pairs" / "forbidden",
            repo_root=REPO_ROOT,
        )


def test_formal_evidence_must_remain_empty(tmp_path: Path) -> None:
    manifest = gate.load_candidate(REPO_ROOT)
    formal = tmp_path / "formal"
    assert gate.require_empty_formal_evidence(manifest, directory=formal) == []
    formal.mkdir()
    (formal / "unexpected.json").write_text("{}", encoding="utf-8")

    with pytest.raises(gate.ReplicationLifecycleGateError, match="不是空目录"):
        gate.require_empty_formal_evidence(manifest, directory=formal)


def test_gate_rejects_candidate_authorization_drift() -> None:
    manifest = gate.load_candidate(REPO_ROOT)
    drifted = copy.deepcopy(manifest)
    drifted["authorization"]["provider_calls_authorized"] = True

    with pytest.raises(gate.candidate.ReplicationCandidateError):
        gate.build_zero_provider_runtime_manifest(drifted, Path("/tmp/issue-245"), repo_root=REPO_ROOT)


def test_execute_requires_explicit_fake_model(tmp_path: Path) -> None:
    manifest = gate.load_candidate(REPO_ROOT)
    pair = manifest["schedule"]["pairs"][0]

    with pytest.raises(gate.ReplicationLifecycleGateError, match="显式 deterministic model factory"):
        gate.execute_zero_provider_pair(
            manifest,
            pair,
            tmp_path / "pair",
            object(),
            {"branch": "main", "revision": "a" * 40, "origin_main": "a" * 40},
            model_factory=None,
            formal_evidence_directory=tmp_path / "formal",
            repo_root=REPO_ROOT,
        )
