"""Issue #210 R2 Make result audit 的零 provider 测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_r2_make_result_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "forge_opaque_provenance_r2_make_result_audit_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module()


def _event(name: str, payload: dict) -> dict:
    return {"event": name, "payload": payload}


def _treatment_events() -> list[dict]:
    events: list[dict] = []
    for index in range(4):
        command_id = f"command-{index}"
        events.extend(
            [
                _event(
                    "command.role_resolved",
                    {
                        "command_id": command_id,
                        "effective_role": "other",
                    },
                ),
                _event(
                    "command.completed",
                    {
                        "command_id": command_id,
                        "stage": "bash",
                        "exit_code": 0,
                        "termination": "completed",
                        "timed_out": False,
                    },
                ),
            ]
        )
    for index, classification in enumerate(
        [
            "compound_shell_forbidden",
            "inspection_budget_exhausted",
            "repair_build_arguments_invalid",
            "repair_build_arguments_invalid",
            "repair_build_arguments_invalid",
        ]
    ):
        failure_id = f"failure-{index}"
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
                        "rejection_classification": classification,
                    },
                ),
            ]
        )
    return events


def _report() -> dict:
    return {
        "manifest_sha256": audit.EXPECTED_MANIFEST_SHA256,
        "evidence_identity_sha256": audit.EXPECTED_EVIDENCE_IDENTITY_SHA256,
        "complete_pair": True,
        "cleanup_succeeded": True,
        "runtime_parity_action_budgets": {
            "baseline": None,
            "treatment": None,
        },
        "r0_rejection_observability": {
            "baseline": None,
            "treatment": None,
        },
        "arms": [
            {
                "arm": "baseline",
                "infrastructure": {"status": "endpoint_censored"},
                "model_behavior": {"status": "not_observed"},
                "model_requests": 1,
                "recorded_tokens": 0,
                "metrics": {
                    "submit_attempts": 0,
                    "clean_replay_attempts": 0,
                },
                "p2": {"status": "unproven", "reason": "opaque_wrapper"},
                "post_checkpoint_provenance_conversion": False,
            },
            {
                "arm": "treatment",
                "infrastructure": {"status": "valid"},
                "model_behavior": {"status": "graph_step_limit"},
                "model_requests": 8,
                "recorded_tokens": 38_780,
                "metrics": {
                    "submit_attempts": 0,
                    "clean_replay_attempts": 0,
                },
                "p2": {"status": "unproven", "reason": "opaque_wrapper"},
                "post_checkpoint_provenance_conversion": False,
            },
        ],
    }


def test_r0_summary_requires_one_to_one_companions() -> None:
    summary = audit.summarize_r0(_treatment_events())
    assert summary == {
        "classified_rejections": 5,
        "companion_events": 5,
        "companion_complete": True,
        "rejection_classifications": [
            "compound_shell_forbidden",
            "inspection_budget_exhausted",
            "repair_build_arguments_invalid",
        ],
        "raw_command_persisted": False,
    }
    missing = _treatment_events()[:-1]
    with pytest.raises(audit.ResultAuditError, match="linkage is incomplete"):
        audit.summarize_r0(missing)


def test_action_budget_reconstruction_is_result_specific_and_closed() -> None:
    baseline = audit.reconstruct_action_budget(
        "baseline",
        [],
        submit_attempts=0,
    )
    treatment = audit.reconstruct_action_budget(
        "treatment",
        _treatment_events(),
        submit_attempts=0,
    )
    assert baseline["consumed"] == audit.EXPECTED_ACTION_CONSUMED["baseline"]
    assert treatment["consumed"] == audit.EXPECTED_ACTION_CONSUMED["treatment"]
    assert treatment["remaining"] == {
        "inspection": 0,
        "repair_build": 2,
        "artifact_stage": 2,
        "submit": 2,
    }
    with pytest.raises(audit.ResultAuditError, match="drifted"):
        audit.reconstruct_action_budget(
            "treatment",
            _treatment_events()[:-12],
            submit_attempts=0,
        )


def test_audit_document_restores_summary_but_censors_paired_estimand() -> None:
    manifest = json.loads((REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r2-make-execution.json").read_text(encoding="utf-8"))
    result = audit.build_audit_document(
        manifest=manifest,
        report=_report(),
        pair_marker={"status": "passed"},
        events_by_arm={
            "baseline": [],
            "treatment": _treatment_events(),
        },
        source_sha256=dict(audit.EXPECTED_INPUT_SHA256),
    )
    assert result["paired_primary_estimand"] == {
        "status": "not_estimable",
        "reason": "baseline_endpoint_censored",
    }
    assert result["treatment_descriptive_outcome"] == {
        "status": "observed_no_conversion",
        "submit_attempts": 0,
        "p2_status": "unproven",
    }
    assert result["arms"]["treatment"]["r0_rejection_observability"]["companion_complete"] is True
    assert result["source_evidence_modified"] is False
    assert (
        result["provider_calls"],
        result["docker_executed"],
        result["formal_attempts"],
        result["model_tokens"],
    ) == (0, False, 0, 0)


def test_sidecar_is_create_once_and_does_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "reports/audit-v1.json"
    audit.write_sidecar_once(path, {"status": "audited"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "audited"}
    with pytest.raises(audit.ResultAuditError, match="already exists"):
        audit.write_sidecar_once(path, {"status": "drifted"})


def test_source_has_no_provider_docker_or_original_evidence_write_path() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "ExperimentLedger.open" in source
    assert 'path.open("x"' in source
    for forbidden in (
        "create_chat_model",
        "DEEPSEEK_API_KEY",
        "os.environ",
        "docker.from_env",
        "write_text(",
        "reports/canary.json).write",
    ):
        assert forbidden not in source
