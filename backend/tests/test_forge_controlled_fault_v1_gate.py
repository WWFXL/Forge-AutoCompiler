"""Issue #147 controlled fault v1 的非 Docker 门禁。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from deerflow.compile.evidence import ExperimentLedger, new_evidence_id

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
MODULE_PATH = SCRIPTS_DIR / "forge_controlled_fault_v1_gate.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-candidate.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_controlled_fault_v1_gate", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate_module = _load_module()


class Session:
    def __init__(self, root: Path) -> None:
        self.session_id = "session-controlled-fault"
        self.leadagent_repo_dir = str(root / "workspace/repo")
        self.leadagent_artifacts_dir = str(root / "artifacts")
        self.replay_attempts = []


def _fixture(tmp_path: Path) -> tuple[Session, ExperimentLedger]:
    session = Session(tmp_path)
    output = Path(session.leadagent_repo_dir) / "build/example.a"
    staged = Path(session.leadagent_artifacts_dir) / "example.a"
    output.parent.mkdir(parents=True)
    staged.parent.mkdir(parents=True)
    output.write_bytes(b"deterministic-static-library")
    staged.write_bytes(output.read_bytes())
    ledger = ExperimentLedger.create(
        tmp_path / "controlled-fault.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"scope": "issue-147-non-provider-gate"},
    )
    return session, ledger


def _fault() -> object:
    return gate_module.ControlledFaultV1(
        gate_module.ControlledFaultSpec(
            case_id="fixture",
            build_output_relative_path="build/example.a",
            staged_relative_path="example.a",
            artifact_type="static_library",
        ),
        classifier=lambda _path: "static_library",
    )


def test_injects_only_staging_fault_and_records_safe_deterministic_state(tmp_path: Path) -> None:
    session, ledger = _fixture(tmp_path)
    manifest = _fault().inject(session=session, ledger=ledger, fault_id="fault_fixture")

    assert (Path(session.leadagent_repo_dir) / "build/example.a").is_file()
    assert list(Path(session.leadagent_artifacts_dir).iterdir()) == []
    assert manifest["state"]["workspace_artifact_present"] is True
    assert manifest["state"]["staged_artifact_present"] is False
    assert manifest["fault_state_sha256"] == gate_module.sha256_bytes(gate_module.canonical_bytes(manifest["state"]))
    event = ledger.read()[-1]
    assert event["event"] == "controlled.fault_injected"
    assert event["payload"]["fault_state_sha256"] == manifest["fault_state_sha256"]
    encoded = json.dumps(event, ensure_ascii=False).lower()
    for forbidden in ("stdout", "stderr", "authorization", "api_key", "secret", str(tmp_path).lower()):
        assert forbidden not in encoded


def test_rejects_mismatched_or_extra_staged_artifacts(tmp_path: Path) -> None:
    session, ledger = _fixture(tmp_path)
    staged = Path(session.leadagent_artifacts_dir) / "example.a"
    staged.write_bytes(b"different")
    with pytest.raises(gate_module.ControlledFaultGateError, match="differ"):
        _fault().inject(session=session, ledger=ledger, fault_id="fault_mismatch")

    staged.write_bytes((Path(session.leadagent_repo_dir) / "build/example.a").read_bytes())
    (staged.parent / "extra.a").write_bytes(b"extra")
    with pytest.raises(gate_module.ControlledFaultGateError, match="exactly"):
        _fault().inject(session=session, ledger=ledger, fault_id="fault_extra")


def test_actionable_failure_validation_requires_one_pre_replay_failure(tmp_path: Path) -> None:
    session, ledger = _fixture(tmp_path)
    submit_id = new_evidence_id("submit")
    ledger.append(
        "submit.completed",
        {
            "submit_attempt_id": submit_id,
            "supporting_command_id": None,
            "session_id": session.session_id,
            "status": "failed",
            "candidate_status": "failed",
            "command_cutoff": 0,
            "command_ids": [],
            "artifacts": [],
            "checks": [],
            "recipe_sha256": None,
            "replay": None,
            "gates": {"exit_code": False, "candidate_only": False, "replay_ready": False, "clean_replay": False, "delivered": None},
        },
    )
    failure_id = new_evidence_id("failure")
    ledger.append(
        "failure.recorded",
        {
            "failure_id": failure_id,
            "submit_attempt_id": submit_id,
            "replay_attempt_id": None,
            "session_id": session.session_id,
            "domain": "verification",
            "classification": "candidate_verification_failed",
            "primary": True,
            "secondary_classifications": [],
        },
    )

    evidence = gate_module.validate_actionable_failure(ledger=ledger, session=session)
    assert evidence["submit_attempt_id"] == submit_id
    assert evidence["failure_id"] == failure_id
    assert evidence["classification"] == "candidate_verification_failed"


def test_canary_candidate_is_strictly_unauthorized_and_hash_bound() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    gate_module.validate_canary_candidate(manifest)
    for artifact in manifest["protocol_artifacts"]:
        assert gate_module.sha256_file(REPO_ROOT / artifact["path"]) == artifact["sha256"]


def test_source_does_not_import_provider_or_formal_runner() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "create_chat_model" not in source
    assert "formal_collection_runner" not in source
    assert "DEEPSEEK_API_KEY" not in source
