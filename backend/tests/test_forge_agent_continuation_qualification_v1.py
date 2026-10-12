from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_agent_continuation_qualification_v1.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_agent_continuation_qualification_v1", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _qualified_outcomes(manifest: dict) -> list[dict]:
    outcomes = []
    for arm in manifest["formal_schedule"]:
        task = next(task for task in manifest["tasks"] if task["task_id"] == arm["task_id"])
        outcomes.append(
            {
                "task_id": task["task_id"],
                "build_system": task["build_system"],
                "checkpoint_depth": int(task["checkpoint_state_id"].rsplit("-", 1)[-1]),
                "checkpoint_sha256": "a" * 64,
                "terminal_classification": "strict_success",
                "strict_success": True,
                "budget": {"complete": True, "conserved": True},
                "post_action_observation": {"session_status": "completed"},
                "cleanup_succeeded": True,
                "error_class": None,
            }
        )
    return outcomes


def test_manifest_freezes_cross_system_depth_schedule() -> None:
    module = _load_module()
    manifest = module.validate_manifest(module._manifest(), require_components=False)

    assert len(manifest["tasks"]) == 9
    assert len(manifest["canary_checkpoints"]) == 3
    assert len(manifest["formal_schedule"]) == 27
    assert manifest["budget"]["total_provider_requests"] == 720
    assert manifest["budget"]["total_recorded_tokens"] == 9_000_000
    assert all(task["target"]["artifact_type"] in {"executable", "static_library"} for task in manifest["tasks"])


def test_q2_qualification_requires_system_and_depth_coverage() -> None:
    module = _load_module()
    manifest = module._manifest()
    outcomes = _qualified_outcomes(manifest)

    passed = module._formal_qualification(manifest, outcomes)
    assert passed["passed"] is True
    assert passed["decision"] == "proceed_to_matched_outcome_matrix_design"

    for item in outcomes:
        if item["checkpoint_depth"] == 3:
            item["strict_success"] = False
            item["terminal_classification"] = "evaluated_failure"
    failed = module._formal_qualification(manifest, outcomes)
    assert failed["passed"] is False
    assert failed["behavior_gates"]["depth_coverage"] is False
    assert failed["decision"] == "stop_before_dynamic_budget_controller_implementation"


def test_q1_checks_q0_before_credential_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    manifest = module._manifest()
    called = False

    monkeypatch.setattr(
        module,
        "preflight",
        lambda _manifest, phase: {"manifest_sha256": "a" * 64, "release_revision": "b" * 40},
    )

    def reject_q0(*_args, **_kwargs):
        raise module.QualificationError("q0 not passed")

    def credential_preflight(_manifest):
        nonlocal called
        called = True

    monkeypatch.setattr(module, "_require_phase_passed", reject_q0)
    monkeypatch.setattr(module, "_provider_preflight", credential_preflight)

    with pytest.raises(module.QualificationError, match="q0 not passed"):
        module.execute_q1(manifest)
    assert called is False


def test_token_observation_fails_closed_on_failed_request(tmp_path: Path) -> None:
    module = _load_module()
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            (
                '{"event_type":"model.request_started","payload":{"request_sequence":1}}',
                '{"event_type":"model.request_failed","payload":{"request_sequence":1}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )

    observed = module._token_observation(events)
    assert observed["requests_started"] == 1
    assert observed["requests_failed"] == 1
    assert observed["complete"] is False
