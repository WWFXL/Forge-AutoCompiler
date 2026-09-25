from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS / "forge_agent_workflow_stage_b_phase5_v2_result_audit.py"
JSON_REPORT = REPO_ROOT / "benchmarks/reports/cpp-agent-workflow-stage-b-phase5-v2-audit.json"
MARKDOWN_REPORT = REPO_ROOT / "benchmarks/reports/cpp-agent-workflow-stage-b-phase5-v2-audit.md"


def _load_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("forge_agent_workflow_stage_b_phase5_v2_result_audit_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module()


def _load_report() -> dict:
    value = json.loads(JSON_REPORT.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_committed_audit_separates_execution_from_strict_success() -> None:
    report = _load_report()

    assert report["raw_result"] == {
        "batch_marker_status": "passed",
        "batch_recorded_tokens": 918121,
        "bitwise_reproducible": 2,
        "candidate_generated": 6,
        "candidate_submitted": 5,
        "execution_completed": True,
        "reachability_recorded_tokens": 58,
        "strict_success": 1,
        "total_recorded_tokens": 918179,
    }
    assert report["audit_result"]["reliable_success"] == 1
    assert report["audit_result"]["workflow_failure"] == 2
    assert report["audit_result"]["invalid_due_to_evaluator_defect"] == 3
    assert report["stage_c"]["authorized"] is False
    assert report["stage_c"]["current_batch_rerun_allowed"] is False
    assert report["historical_evidence_mutated"] is False


def test_committed_audit_names_each_classification_and_renders_deterministically() -> None:
    report = _load_report()
    classifications = {item["task_id"]: item["audit_classification"] for item in report["tasks"]}

    assert classifications == {
        "yyjson": "workflow_failure",
        "cppitertools": "reliable_success",
        "openh264": "invalid_due_to_evaluator_defect",
        "uwebsockets": "workflow_failure",
        "c-ares": "invalid_due_to_evaluator_defect",
        "libass": "invalid_due_to_evaluator_defect",
    }
    assert audit.render_markdown(report) == MARKDOWN_REPORT.read_text(encoding="utf-8")


def test_cli_summary_is_bounded_and_omits_full_outcomes() -> None:
    summary = audit.compact_summary(_load_report())

    assert summary == {
        "status": "audited",
        "execution_completed": True,
        "raw_strict_success": 1,
        "reliable_success": 1,
        "workflow_failure": 2,
        "evaluator_invalid": 3,
        "stage_c_authorized": False,
        "current_batch_rerun_allowed": False,
    }
    assert len(json.dumps(summary, ensure_ascii=False)) < 512
    assert "tasks" not in summary
    assert "outcomes" not in summary


def test_frozen_v2_files_keep_the_recorded_identity() -> None:
    frozen = {
        REPO_ROOT / "backend/packages/harness/deerflow/compile/external_evaluator_v2.py": audit.FROZEN_EVALUATOR_V2_SHA256,
        REPO_ROOT / "scripts/forge_agent_workflow_stage_b_phase5_v2_authorized_runner.py": audit.FROZEN_AUTHORIZED_RUNNER_SHA256,
    }

    for path, expected in frozen.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
