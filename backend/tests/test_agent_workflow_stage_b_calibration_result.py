"""Phase 5 停止结果只读审计测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
RESULT_PATH = SCRIPTS / "forge_agent_workflow_stage_b_calibration_result.py"
REPORT_PATH = REPO_ROOT / "benchmarks/reports/cpp-agent-workflow-stage-b-calibration-failed.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


result_audit = _load_module("forge_agent_workflow_stage_b_calibration_result_test", RESULT_PATH)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _marker(digest: str, revision: str, status: str, *, task_id: str | None = None) -> dict:
    return {
        "manifest_sha256": digest,
        "release_revision": revision,
        "task_id": task_id,
        "status": status,
        "error_class": "Phase5AuthorizedRunnerError" if status == "failed" else None,
        "updated_at": "2026-09-25T05:22:46+00:00",
    }


def _result(digest: str, revision: str, task_id: str, *, strict: bool, tokens: int) -> dict:
    layers = [{"layer": name, "status": "passed" if strict or name in ("S0", "S1") else "failed", "reason_codes": ["fixture"]} for name in ("S0", "S1", "S2", "S3", "S4", "S5")]
    return {
        "manifest_sha256": digest,
        "release_revision": revision,
        "task_id": task_id,
        "candidate_generated_observed": True,
        "candidate_submitted": True,
        "strict_reproducible_build_success": strict,
        "bitwise_reproducible": True if strict else None,
        "recorded_tokens": tokens,
        "duration_ms": 1000,
        "session_status": "completed" if strict else "failed",
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
        "s0_s5": layers,
    }


def _fixture(tmp_path: Path) -> tuple[dict, Path, Path]:
    manifest = result_audit.protocol.load_manifest()
    digest = result_audit.protocol.candidate.canonical_sha256(manifest)
    revision = "a" * 40
    evidence = tmp_path / "evidence"
    sessions = tmp_path / "sessions"
    reachability = manifest["authorized_execution"]["reachability"]
    _write_json(evidence / reachability["marker"], _marker(digest, revision, "passed"))
    _write_json(
        evidence / reachability["report"],
        {
            "manifest_sha256": digest,
            "release_revision": revision,
            "passed": True,
            "request_count": 1,
            "recorded_tokens": 61,
            "actual_model": "deepseek-flash",
        },
    )
    _write_json(evidence / manifest["authorized_execution"]["batch_marker"], _marker(digest, revision, "failed"))
    completed = manifest["schedule"]["order"][:4]
    for index, task_id in enumerate(completed):
        _write_json(evidence / "tasks" / task_id / "attempt.json", _marker(digest, revision, "passed", task_id=task_id))
        _write_json(evidence / "tasks" / task_id / "result.json", _result(digest, revision, task_id, strict=index == 2, tokens=100 + index))
    stopped = manifest["schedule"]["order"][4]
    _write_json(evidence / "tasks" / stopped / "attempt.json", _marker(digest, revision, "failed", task_id=stopped))
    task = next(item for item in manifest["tasks"] if item["task_id"] == stopped)
    _write_json(
        sessions / f"phase5-{stopped}-{digest[:12]}" / "session-1" / "session.json",
        {
            "repo_url": task["repository_url"],
            "commit_sha": task["commit_sha"],
            "status": "failed",
            "finalized_at": "2026-09-25T05:22:45+00:00",
            "build_system": "cmake",
        },
    )
    return manifest, evidence, sessions


def test_build_report_freezes_stopped_prefix_and_stage_c_block(tmp_path: Path) -> None:
    manifest, evidence, sessions = _fixture(tmp_path)

    report = result_audit.build_report(
        manifest,
        evidence,
        sessions,
        resource_probe=lambda: {
            "managed_containers": [],
            "managed_images": [],
            "paused_parents": [],
            "zero_managed_resources": True,
        },
    )

    assert report["status"] == "stopped_on_pre_model_identity_drift"
    assert report["batch"]["completed_task_count"] == 4
    assert report["batch"]["attempted_task_count"] == 5
    assert report["batch"]["stopped_task_id"] == "c-ares"
    assert report["batch"]["unattempted_tasks"] == ["libass"]
    assert report["summary"]["strict_success"] == 1
    assert report["summary"]["bitwise_reproducible"] == 1
    assert report["summary"]["total_recorded_tokens"] == 467
    assert report["stop_audit"]["frozen_build_system"] == "autotools"
    assert report["stop_audit"]["observed_build_system"] == "cmake"
    assert report["stop_audit"]["model_invocation_reached"] is False
    assert report["stage_c"]["authorized"] is False
    assert report["interpretation"]["replacement_or_backfill_allowed"] is False
    assert "Stage C 保持阻断" in result_audit.render_markdown(report)


def test_build_report_rejects_evidence_after_stop(tmp_path: Path) -> None:
    manifest, evidence, sessions = _fixture(tmp_path)
    digest = result_audit.protocol.candidate.canonical_sha256(manifest)
    revision = "a" * 40
    _write_json(evidence / "tasks/libass/attempt.json", _marker(digest, revision, "failed", task_id="libass"))

    with pytest.raises(result_audit.Phase5ResultAuditError, match="多个失败 attempt"):
        result_audit.build_report(
            manifest,
            evidence,
            sessions,
            resource_probe=lambda: {"zero_managed_resources": True},
        )


def test_committed_report_records_observed_phase5_stop() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    assert report["manifest_sha256"] == "9818ea136c90620f2e38925cb936c1c21e3cf523b43ea8039c8c2283ea6f1dcf"
    assert report["release_revision"] == "1a60cf2e496ca32081450b9163eeecd47eb61182"
    assert report["batch"]["stopped_task_id"] == "c-ares"
    assert report["batch"]["unattempted_tasks"] == ["libass"]
    assert report["summary"]["total_recorded_tokens"] == 545_545
    assert report["stage_c"]["authorized"] is False
