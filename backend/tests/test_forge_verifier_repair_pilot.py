from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_runtime.py"
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_pilot_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_pilot_runner.py"
ANALYZER_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_pilot_analyzer.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-repair-pilot-runtime-candidate.json"
MANIFEST_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-verifier-repair-pilot-runtime-v1.schema.json"
PACKET_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-verifier-repair-packet-v1.schema.json"

SHARED_COMPONENT_BLOBS = {
    "backend/packages/harness/deerflow/compile/operations.py": "d48cd0fe8108023fa4128ae2a6e048498b881259",
    "backend/packages/harness/deerflow/compile/evidence.py": "d6c22034889e6c62a35289ca0901c2a550da9984",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py": "a99c062dddf450088477ab813713bd5d250fa636",
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load_module("forge_verifier_repair_runtime_test", RUNTIME_PATH)
protocol = _load_module("forge_verifier_repair_pilot_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_verifier_repair_pilot_runner_test", RUNNER_PATH)
analyzer = _load_module("forge_verifier_repair_pilot_analyzer_test", ANALYZER_PATH)


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _candidate_failure_events() -> list[dict]:
    return [
        {
            "event": "build.system_checked",
            "payload": {
                "expected_build_system": "cmake",
                "observed_build_system": "cmake",
                "selected_build_system": "cmake",
                "matches": True,
            },
        },
        {
            "event": "submit.completed",
            "payload": {
                "status": "failed",
                "candidate_status": "failed",
                "submit_attempt_id": "submit_1",
                "supporting_command_id": "command_1",
                "checks": [{"name": "benchmark_constraints", "passed": False, "exit_code": 1}],
                "artifacts": [{"path": "artifact.a", "artifact_type": "static_library"}],
                "replay": None,
            },
        },
    ]


def _result(status: str = "failed") -> str:
    return json.dumps(
        {
            "exit_code": 1 if status == "failed" else 0,
            "status": status,
            "candidate_status": "failed" if status == "failed" else "passed",
            "replay_status": "not_run" if status == "failed" else "passed",
            "replay_attempt_id": None,
            "submit_attempt_id": "submit_1",
            "supporting_command_id": "command_1",
            "artifacts": [],
            "message": "Error: candidate rejected" if status == "failed" else "accepted",
        },
        ensure_ascii=False,
        indent=2,
    )


def _context(tmp_path: Path, *, treatment: str, events: list[dict]):
    ledger = runtime.RepairEvidenceLedger.create(
        tmp_path / f"{treatment}.jsonl",
        {
            "manifest_sha256": "0" * 64,
            "thread_id": "thread_1",
            "physical_attempt_id": "physical_attempt_1",
            "order": 1,
            "pair_id": "pair_1",
            "case_id": "case_1",
            "provider_condition": "provider_1",
            "treatment": treatment,
            "repetition": 1,
        },
    )
    return runtime.RepairFeedbackContext(
        thread_id="thread_1",
        pair_id="pair_1",
        case_id="case_1",
        provider_condition="provider_1",
        treatment=treatment,
        repetition=1,
        expected_build_system="cmake",
        expected_artifacts=(("artifact.a", "static_library"),),
        event_reader=lambda: events,
        evidence=ledger,
    )


def test_baseline_submit_response_is_byte_identical(tmp_path: Path) -> None:
    original = _result()
    fake_tools = SimpleNamespace(_submit_with_post_build_phase=lambda _session, supporting_command_id=None: original)
    context = _context(tmp_path, treatment=runtime.BASELINE_ARM, events=_candidate_failure_events())

    with runtime.submit_feedback_scope(context, fake_tools):
        returned = fake_tools._submit_with_post_build_phase(SimpleNamespace(thread_id="thread_1"))

    assert returned == original
    records = context.evidence.read()
    assert records[-1]["payload"]["packet_attached"] is False
    assert runtime.evaluate_treatment_fidelity(records) == {
        "status": "passed",
        "evidence_complete": True,
        "exposures": 1,
        "actionable_exposures": 1,
        "failures": [],
    }


def test_treatment_attaches_deterministic_valid_packet(tmp_path: Path) -> None:
    original = _result()
    fake_tools = SimpleNamespace(_submit_with_post_build_phase=lambda _session, supporting_command_id=None: original)
    context = _context(tmp_path, treatment=runtime.TREATMENT_ARM, events=_candidate_failure_events())

    with runtime.submit_feedback_scope(context, fake_tools):
        returned = fake_tools._submit_with_post_build_phase(SimpleNamespace(thread_id="thread_1"))

    payload = json.loads(returned)
    packet = payload["repair_packet"]
    assert packet["primary_classification"] == "build_system_unproven"
    assert packet["failed_checks"] == [{"name": "benchmark_constraints", "exit_code": 1}]
    assert packet["artifact_identity_diff"] == {
        "expected_only": [],
        "observed_only": [],
        "mismatches": [],
        "truncated": False,
    }
    jsonschema.validate(packet, json.loads(PACKET_SCHEMA_PATH.read_text(encoding="utf-8")))
    assert runtime.evaluate_treatment_fidelity(context.evidence.read())["status"] == "passed"


def test_successful_or_non_actionable_submit_does_not_attach_packet(tmp_path: Path) -> None:
    original = _result(status="passed")
    fake_tools = SimpleNamespace(_submit_with_post_build_phase=lambda _session, supporting_command_id=None: original)
    context = _context(tmp_path, treatment=runtime.TREATMENT_ARM, events=[])

    with runtime.submit_feedback_scope(context, fake_tools):
        returned = fake_tools._submit_with_post_build_phase(SimpleNamespace(thread_id="thread_1"))

    assert returned == original
    assert runtime.evaluate_treatment_fidelity(context.evidence.read())["status"] == "not_exposed"


def test_failed_submit_without_persisted_evidence_fails_fidelity(tmp_path: Path) -> None:
    original = _result()
    fake_tools = SimpleNamespace(_submit_with_post_build_phase=lambda _session, supporting_command_id=None: original)
    context = _context(tmp_path, treatment=runtime.TREATMENT_ARM, events=[])

    with runtime.submit_feedback_scope(context, fake_tools):
        returned = fake_tools._submit_with_post_build_phase(SimpleNamespace(thread_id="thread_1"))

    assert returned == original
    assert runtime.evaluate_treatment_fidelity(context.evidence.read()) == {
        "status": "failed",
        "evidence_complete": False,
        "exposures": 1,
        "actionable_exposures": 0,
        "failures": ["evidence_missing"],
    }


def test_baseline_digest_drift_fails_fidelity(tmp_path: Path) -> None:
    context = _context(tmp_path, treatment=runtime.BASELINE_ARM, events=_candidate_failure_events())
    context.evidence.append(
        "repair.feedback_observed",
        {
            "treatment": runtime.BASELINE_ARM,
            "status": "failed",
            "actionable": True,
            "evidence_complete": True,
            "primary_classification": "build_system_unproven",
            "packet_attached": False,
            "packet": None,
            "original_sha256": "1" * 64,
            "returned_sha256": "2" * 64,
            "submit_attempt_id": "submit_1",
        },
    )

    fidelity = runtime.evaluate_treatment_fidelity(context.evidence.read())

    assert fidelity["status"] == "failed"
    assert fidelity["failures"] == ["baseline_response_modified"]


def test_replay_mismatch_is_normalized_without_raw_output() -> None:
    payload = json.loads(_result())
    payload.update(candidate_status="passed", replay_status="failed", replay_attempt_id="replay_1")
    events = [
        {
            "event": "submit.completed",
            "payload": {
                "status": "failed",
                "candidate_status": "passed",
                "submit_attempt_id": "submit_1",
                "supporting_command_id": "command_1",
                "checks": [{"name": "clean_replay", "passed": False, "exit_code": 1}],
                "artifacts": [{"path": "artifact.a", "artifact_type": "static_library"}],
                "replay": {"status": "failed", "replay_attempt_id": "replay_1"},
            },
        },
        {
            "event": "replay.completed",
            "payload": {
                "submit_attempt_id": "submit_1",
                "replay_attempt_id": "replay_1",
                "status": "failed",
                "primary_failure_classification": "sha256_mismatch",
                "artifacts": [{"path": "artifact.a", "mismatches": ["sha256"]}],
            },
        },
    ]

    packet = runtime.build_repair_packet(payload, events, expected_artifacts=(("artifact.a", "static_library"),))

    assert packet is not None
    assert packet["primary_classification"] == "sha256_mismatch"
    assert packet["artifact_identity_diff"]["mismatches"] == [{"path": "artifact.a", "kinds": ["sha256"]}]
    serialized = json.dumps(packet).lower()
    assert "stdout" not in serialized
    assert "stderr" not in serialized
    assert "prompt" not in serialized


def test_packet_allows_safe_artifact_name_containing_forbidden_word() -> None:
    events = _candidate_failure_events()
    events[-1]["payload"]["artifacts"] = [{"path": "prompt-output.a", "artifact_type": "static_library"}]

    packet = runtime.build_repair_packet(
        json.loads(_result()),
        events,
        expected_artifacts=(("prompt-output.a", "static_library"),),
    )

    assert packet is not None
    assert packet["artifact_identity_diff"]["expected_only"] == []


def test_unsafe_dynamic_failed_check_name_is_omitted() -> None:
    events = _candidate_failure_events()
    events[-1]["payload"]["checks"].append({"name": "unsafe/check", "passed": False, "exit_code": 1})

    packet = runtime.build_repair_packet(json.loads(_result()), events, expected_artifacts=(("artifact.a", "static_library"),))

    assert packet is not None
    assert packet["failed_checks"] == [{"name": "benchmark_constraints", "exit_code": 1}]


def test_sidecar_hash_chain_detects_tampering(tmp_path: Path) -> None:
    context = _context(tmp_path, treatment=runtime.BASELINE_ARM, events=[])
    context.evidence.append("repair.context_completed", {"status": "failed"})
    lines = context.evidence.path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("pair_1", "pair_2")
    context.evidence.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(runtime.RepairRuntimeError, match="hash chain"):
        context.evidence.read()


def test_sidecar_rejects_non_whitelisted_payload_fields(tmp_path: Path) -> None:
    context = _context(tmp_path, treatment=runtime.BASELINE_ARM, events=[])

    with pytest.raises(runtime.RepairRuntimeError, match="completion fields"):
        context.evidence.append("repair.context_completed", {"status": "failed", "detail": "not allowed"})


def test_protocol_is_deterministic_strict_and_unauthed() -> None:
    manifest = _manifest()

    assert protocol.generate_manifest() == manifest
    assert protocol.validate_manifest(manifest) == manifest
    assert manifest["protocolization"]["runtime_implementation_authorized"] is True
    assert manifest["protocolization"]["collection_authorized"] is False
    assert len(manifest["pilot_schedule"]) == 12
    assert len({slot["pair_id"] for slot in manifest["pilot_schedule"]}) == 6
    first_arms = []
    for pair_id in sorted({slot["pair_id"] for slot in manifest["pilot_schedule"]}):
        first_arms.append(min((slot for slot in manifest["pilot_schedule"] if slot["pair_id"] == pair_id), key=lambda slot: slot["order"])["treatment"])
    assert first_arms.count(runtime.BASELINE_ARM) == 3
    assert first_arms.count(runtime.TREATMENT_ARM) == 3

    manifest_schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    packet_schema = json.loads(PACKET_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(manifest_schema)
    jsonschema.Draft202012Validator.check_schema(packet_schema)
    jsonschema.validate(manifest, manifest_schema)

    changed = copy.deepcopy(manifest)
    changed["protocolization"]["collection_authorized"] = True
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_manifest(changed)


def test_shared_frozen_compile_components_remain_byte_identical() -> None:
    for relative_path, expected_blob in SHARED_COMPONENT_BLOBS.items():
        payload = (REPO_ROOT / relative_path).read_bytes()
        header = f"blob {len(payload)}\0".encode()
        assert hashlib.sha1(header + payload).hexdigest() == expected_blob


@pytest.mark.parametrize("entrypoint", [runner.provider_canary, runner.run_attempt, runner.run_batch])
def test_unauthed_runner_rejects_before_evidence_or_model_work(entrypoint, tmp_path: Path) -> None:
    with pytest.raises(runner.RunnerError, match="not authorized"):
        entrypoint(_manifest(), output_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def _attempts(manifest: dict) -> list[dict]:
    attempts = []
    for slot in manifest["pilot_schedule"]:
        treatment = slot["treatment"] == runtime.TREATMENT_ARM
        converted = treatment and slot["pair_id"] == "liblouis-richlab-r1"
        attempts.append(
            {
                **{field: slot[field] for field in ("order", "pair_id", "case_id", "provider_condition", "treatment", "repetition")},
                "oracle_passed": treatment and slot["pair_id"] == "liblouis-richlab-r1",
                "terminal_passed": False,
                "fidelity_status": "passed" if treatment else "not_exposed",
                "recorded_tokens": 100 + int(treatment),
                "model_requests": 10,
                "wall_clock_seconds": 20.0 + int(treatment),
                "actionable_verifier_failures": int(treatment),
                "repair_conversions": int(converted),
                "submit_attempts": 1 + int(treatment),
                "clean_replay_attempts": int(treatment),
                "failure_transitions": ([{"from": "candidate_verification_failed", "to": "oracle_passed"}] if converted else []),
            }
        )
    return attempts


def test_analyzer_reports_only_complete_descriptive_pairs() -> None:
    manifest = _manifest()
    report = analyzer.build_report(manifest, _attempts(manifest))

    assert report["scope"] == {
        "descriptive_only": True,
        "p_value_computed": False,
        "model_ranking_performed": False,
        "paired_primary_eligible": True,
    }
    assert report["collection"] == {
        "planned_slots": 12,
        "observed_slots": 12,
        "complete_pairs": 6,
        "incomplete_pairs": [],
    }
    assert report["oracle_discordance"]["treatment_only_passed"] == 1
    assert all(pair["recorded_tokens_delta"] == 1 for pair in report["pairs"])
    assert report["secondary_outcomes"] == {
        "repair_conversion": {
            "baseline": {"actionable_failures": 0, "conversions": 0, "rate": None},
            "treatment": {"actionable_failures": 6, "conversions": 1, "rate": 0.166667},
        },
        "false_acceptance_count": {"baseline": 0, "treatment": 0},
        "submit_attempts": {"baseline": 6, "treatment": 12},
        "clean_replay_attempts": {"baseline": 0, "treatment": 6},
        "failure_transitions": {
            "baseline": {},
            "treatment": {"candidate_verification_failed->oracle_passed": 1},
        },
    }
    converted_pair = next(pair for pair in report["pairs"] if pair["pair_id"] == "liblouis-richlab-r1")
    assert converted_pair["repair_conversions"] == {"baseline": 0, "treatment": 1, "delta": 1}


def test_analyzer_keeps_incomplete_pair_out_of_pair_results() -> None:
    manifest = _manifest()
    attempts = _attempts(manifest)[:-1]

    report = analyzer.build_report(manifest, attempts)

    assert report["collection"]["observed_slots"] == 11
    assert report["collection"]["complete_pairs"] == 5
    assert report["collection"]["incomplete_pairs"] == ["mupdf-deepseek-r1"]
    assert report["scope"]["paired_primary_eligible"] is False
