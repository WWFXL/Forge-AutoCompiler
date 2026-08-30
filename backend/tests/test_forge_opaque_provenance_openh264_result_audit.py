"""Issue #228 OpenH264 result audit 的零 provider 测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_openh264_result_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "forge_opaque_provenance_openh264_result_audit_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module()


def _event(
    name: str,
    payload: dict,
    *,
    event_sha256: str = "f" * 64,
    previous_event_sha256: str | None = None,
) -> dict:
    return {
        "event": name,
        "payload": payload,
        "event_sha256": event_sha256,
        "previous_event_sha256": previous_event_sha256,
    }


def _arm_events(arm: str) -> list[dict]:
    events: list[dict] = []
    expected_requests = audit.EXPECTED_REQUESTS[arm]
    for index in range(expected_requests["model_requests"]):
        request_id = f"{arm}-request-{index}"
        events.extend(
            [
                _event("model.request_started", {"model_request_id": request_id}),
                _event(
                    "model.request_completed",
                    {
                        "model_request_id": request_id,
                        "token_usage": {
                            "total_tokens": expected_requests["recorded_tokens"] if index == 0 else 0,
                        },
                    },
                ),
            ]
        )

    command_roles = ["other"] * 4
    if arm == "treatment":
        command_roles.append("build")
    for index, role in enumerate(command_roles):
        command_id = f"{arm}-command-{index}"
        failed_inspection = arm == "treatment" and index == 2
        events.extend(
            [
                _event(
                    "command.role_resolved",
                    {"command_id": command_id, "effective_role": role},
                ),
                _event(
                    "command.completed",
                    {
                        "command_id": command_id,
                        "stage": "bash",
                        "timed_out": False,
                        "termination": "failed" if failed_inspection else "completed",
                    },
                ),
            ]
        )

    classifications = audit.EXPECTED_R0_CLASSIFICATIONS
    for index in range(audit.EXPECTED_R0_COUNTS[arm]):
        failure_id = f"{arm}-failure-{index}"
        events.extend(
            [
                _event(
                    "agent.tool_failed",
                    {
                        "failure_id": failure_id,
                        "exception_class": "ObservableRuntimeParityGateError",
                    },
                ),
                _event(
                    "agent.tool_rejection_observed",
                    {
                        "failure_id": failure_id,
                        "rejection_classification": classifications[index % len(classifications)],
                    },
                ),
            ]
        )

    if arm == "treatment":
        events.extend(
            [
                _event("submit.started", {"submit_attempt_id": "submit-1"}),
                _event("submit.completed", {"submit_attempt_id": "submit-1"}),
                _event(
                    "attempt.budget_completed",
                    {},
                    event_sha256=audit.EXPECTED_REPORT_TIME_HEADS[arm],
                ),
            ]
        )
    events.append(
        _event(
            "experiment.completed",
            {"status": "passed"},
            event_sha256=audit.EXPECTED_TERMINAL_HEADS[arm],
            previous_event_sha256=(audit.EXPECTED_REPORT_TIME_HEADS[arm] if arm == "treatment" else "e" * 64),
        )
    )
    return events


def _report() -> dict:
    return {
        "manifest_sha256": audit.EXPECTED_MANIFEST_SHA256,
        "evidence_identity_sha256": audit.EXPECTED_EVIDENCE_IDENTITY_SHA256,
        "release_revision": audit.EXPECTED_RELEASE_REVISION,
        "complete_pair": True,
        "cleanup_succeeded": True,
        "recorded_tokens": 57_872,
        "reachability_recorded_tokens": 17,
        "historical_pairs_pooled": False,
        "treatment_effect_estimated": False,
        "p_value_computed": False,
        "model_ranking_performed": False,
        "r0_rejection_observability": {
            "baseline": None,
            "treatment": {"classified_rejections": 3},
        },
        "runtime_parity_action_budgets": {
            "baseline": None,
            "treatment": {"consumed": audit.EXPECTED_ACTION_CONSUMED["treatment"]},
        },
        "arms": [
            {
                "arm": "baseline",
                "ledger_head_sha256": audit.EXPECTED_REPORT_TIME_HEADS["baseline"],
                "infrastructure": {"status": "valid"},
                "model_behavior": {
                    "status": "graph_step_limit",
                    "terminal_error_class": "GraphRecursionError",
                },
                "model_requests": 8,
                "recorded_tokens": 37_271,
                "metrics": {
                    "model_requests": 8,
                    "recorded_tokens": 37_271,
                    "submit_attempts": 0,
                },
                "verification_outcome": {
                    "clean_replay_attempts": 0,
                    "status": "not_attempted",
                    "submit_attempts": 0,
                },
                "p2": {"status": "unproven", "reason": "opaque_wrapper"},
                "post_checkpoint_provenance_conversion": False,
            },
            {
                "arm": "treatment",
                "ledger_head_sha256": audit.EXPECTED_REPORT_TIME_HEADS["treatment"],
                "infrastructure": {"status": "valid"},
                "model_behavior": {"status": "completed", "terminal_error_class": None},
                "model_requests": 6,
                "recorded_tokens": 20_584,
                "metrics": {
                    "model_requests": 6,
                    "recorded_tokens": 20_584,
                    "submit_attempts": 1,
                },
                "verification_outcome": {
                    "clean_replay_attempts": 1,
                    "status": "passed",
                    "submit_attempts": 1,
                },
                "p2": {"status": "proven", "proof_mode": "direct_make"},
                "post_checkpoint_provenance_conversion": True,
            },
        ],
    }


def _attempt_document() -> dict:
    return {
        "status": "passed",
        "error_class": None,
        "manifest_sha256": audit.EXPECTED_MANIFEST_SHA256,
        "release_revision": audit.EXPECTED_RELEASE_REVISION,
    }


def test_frozen_source_manifest_covers_exactly_twelve_files() -> None:
    assert len(audit.EXPECTED_INPUT_SHA256) == 12
    assert set(audit.EXPECTED_INPUT_SHA256) == {
        "checkpoint/coordinator.sqlite",
        "checkpoint/messages.sqlite",
        audit.PARENT_LEDGER_PATH,
        "markers/dependency-fixture.json",
        "markers/pair.json",
        "markers/reachability.json",
        audit.ARM_LEDGER_PATHS["baseline"],
        audit.ARM_LEDGER_PATHS["treatment"],
        "reports/canary.json",
        "reports/dependency-fixture-cleanup.json",
        "reports/dependency-fixture.json",
        "reports/reachability.json",
    }


def test_source_verifier_allows_only_the_create_once_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for relative_path in audit.EXPECTED_INPUT_SHA256:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(
        audit,
        "file_sha256",
        lambda path: audit.EXPECTED_INPUT_SHA256[path.relative_to(tmp_path).as_posix()],
    )
    assert audit.verify_source_inputs(tmp_path) == audit.EXPECTED_INPUT_SHA256
    sidecar = tmp_path / audit.DEFAULT_SIDECAR
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.touch()
    assert audit.verify_source_inputs(tmp_path) == audit.EXPECTED_INPUT_SHA256
    unexpected = tmp_path / "reports/unexpected.json"
    unexpected.touch()
    with pytest.raises(audit.ResultAuditError, match="unexpected evidence file"):
        audit.verify_source_inputs(tmp_path)


def test_r0_and_action_summaries_are_recovered_for_both_arms() -> None:
    baseline_events = _arm_events("baseline")
    treatment_events = _arm_events("treatment")
    baseline_r0 = audit.summarize_r0("baseline", baseline_events)
    treatment_r0 = audit.summarize_r0("treatment", treatment_events)
    assert baseline_r0["classified_rejections"] == 7
    assert treatment_r0["classified_rejections"] == 3
    assert baseline_r0["rejection_classifications"] == audit.EXPECTED_R0_CLASSIFICATIONS
    assert audit.reconstruct_action_budget("baseline", baseline_events)["consumed"] == {
        "inspection": 4,
        "repair_build": 0,
        "artifact_stage": 0,
        "submit": 0,
    }
    assert audit.reconstruct_action_budget("treatment", treatment_events)["consumed"] == {
        "inspection": 4,
        "repair_build": 1,
        "artifact_stage": 0,
        "submit": 1,
    }
    missing_companion = treatment_events.copy()
    first_companion = next(index for index, event in enumerate(missing_companion) if event["event"] == "agent.tool_rejection_observed")
    del missing_companion[first_companion]
    with pytest.raises(audit.ResultAuditError, match="linkage is incomplete"):
        audit.summarize_r0("treatment", missing_companion)


def test_model_request_lifecycle_and_tokens_are_closed() -> None:
    baseline = audit.summarize_model_requests("baseline", _arm_events("baseline"))
    treatment = audit.summarize_model_requests("treatment", _arm_events("treatment"))
    assert (baseline["model_requests"], baseline["recorded_tokens"]) == (8, 37_271)
    assert (treatment["model_requests"], treatment["recorded_tokens"]) == (6, 20_584)
    incomplete = _arm_events("baseline")
    incomplete = [event for event in incomplete if not (event["event"] == "model.request_completed" and event["payload"].get("model_request_id") == "baseline-request-0")]
    with pytest.raises(audit.ResultAuditError, match="lifecycle is incomplete"):
        audit.summarize_model_requests("baseline", incomplete)


def test_report_time_and_terminal_heads_remain_distinct() -> None:
    baseline = audit.summarize_ledger_head(
        "baseline",
        _arm_events("baseline"),
        report_time_head=audit.EXPECTED_REPORT_TIME_HEADS["baseline"],
    )
    treatment = audit.summarize_ledger_head(
        "treatment",
        _arm_events("treatment"),
        report_time_head=audit.EXPECTED_REPORT_TIME_HEADS["treatment"],
    )
    assert baseline["report_time_head_semantics"] == "terminal_head"
    assert treatment["report_time_head_semantics"] == "pre_terminal_head"
    assert treatment["report_time_ledger_head_sha256"] != treatment["terminal_ledger_head_sha256"]


def test_audit_document_recovers_gap_without_changing_primary_outcome() -> None:
    manifest = json.loads((REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-openh264-execution.json").read_text(encoding="utf-8"))
    result = audit.build_audit_document(
        manifest=manifest,
        report=_report(),
        pair_marker=_attempt_document(),
        reachability_marker=_attempt_document(),
        reachability_report={
            "passed": True,
            "request_count": 1,
            "recorded_tokens": 17,
            "request_timeout_seconds": 300,
            "max_retries": 0,
            "fallback_used": False,
            "manifest_sha256": audit.EXPECTED_MANIFEST_SHA256,
            "release_revision": audit.EXPECTED_RELEASE_REVISION,
            "actual_model": "deepseek-v4-flash",
            "duration_ms": 1369,
        },
        fixture_marker=_attempt_document(),
        fixture_report={
            "manifest_sha256": audit.EXPECTED_MANIFEST_SHA256,
            "release_revision": audit.EXPECTED_RELEASE_REVISION,
            "apt_index_downloaded": False,
            "preparation_container_removed": True,
        },
        fixture_cleanup_report={
            "manifest_sha256": audit.EXPECTED_MANIFEST_SHA256,
            "cleanup_succeeded": True,
            "container_absent": True,
            "tag_absent": True,
            "image_id_absent": True,
        },
        parent_events=[
            _event(
                "experiment.completed",
                {"status": "passed"},
                event_sha256=audit.EXPECTED_TERMINAL_HEADS["parent"],
            )
        ],
        events_by_arm={
            "baseline": _arm_events("baseline"),
            "treatment": _arm_events("treatment"),
        },
        source_sha256=dict(audit.EXPECTED_INPUT_SHA256),
    )
    assert result["source_evidence_file_count"] == 12
    assert result["evidence_file_count_after_sidecar"] == 13
    assert result["arms"]["baseline"]["r0_rejection_observability"]["classified_rejections"] == 7
    assert result["arms"]["treatment"]["runtime_parity_action_budget"]["consumed"]["submit"] == 1
    assert result["paired_descriptive_outcome"] == {
        "complete_pair": True,
        "baseline_p2_status": "unproven",
        "baseline_p2_reason": "opaque_wrapper",
        "treatment_p2_status": "proven",
        "treatment_p2_proof_mode": "direct_make",
        "treatment_submit_attempts": 1,
        "treatment_clean_replay_attempts": 1,
        "cleanup_succeeded": True,
    }
    assert (
        result["provider_calls"],
        result["credential_read"],
        result["docker_executed"],
        result["formal_attempts"],
        result["model_tokens"],
    ) == (0, False, False, 0, 0)


def test_sidecar_is_create_once_and_leaves_source_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"status":"frozen"}\n', encoding="utf-8")
    before = audit.file_sha256(source)
    path = tmp_path / audit.DEFAULT_SIDECAR
    audit.write_sidecar_once(path, {"status": "audited"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "audited"}
    assert audit.file_sha256(source) == before
    with pytest.raises(audit.ResultAuditError, match="already exists"):
        audit.write_sidecar_once(path, {"status": "drifted"})


def test_source_has_no_provider_docker_or_original_evidence_write_path() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "ExperimentLedger.open" in source
    assert 'path.open("x"' in source
    for forbidden in (
        "create_chat_model",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "os.environ",
        "docker.from_env",
        "subprocess",
        "write_text(",
        "reports/canary.json).write",
    ):
        assert forbidden not in source
