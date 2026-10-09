from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_offline_qualification_v1 as jev  # noqa: E402


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_evaluation_fixture_is_deterministic_and_label_free() -> None:
    fixture = jev.validate_evaluation_states()

    assert fixture == jev.generate_evaluation_states()
    assert fixture["contains_labels"] is False
    assert len(fixture["states"]) == 18
    payload = json.dumps(fixture, sort_keys=True)
    for forbidden in ("optimal_action", "successful_actions", "fault_type", "project_family"):
        assert forbidden not in payload


def test_execution_manifest_freezes_authorization_budget_and_runner() -> None:
    manifest = jev.generate_execution_manifest(
        implementation_revision="a" * 40,
        runner_sha256="b" * 64,
    )

    assert manifest["identity"] == jev.IDENTITY
    assert manifest["implementation"]["git_revision"] == "a" * 40
    assert manifest["implementation"]["runner_sha256"] == "b" * 64
    assert manifest["authorization"] == {
        "credential_read_authorized": True,
        "provider_calls_authorized": True,
        "model_calls_authorized": True,
        "maximum_model_requests": 72,
        "maximum_input_tokens": 1_000_000,
        "maximum_model_cost_usd": 0.042,
        "docker_outcome_collection_authorized": True,
        "new_identity_evidence_write_authorized": True,
        "controller_implementation_authorized": False,
        "historical_evidence_write_authorized": False,
    }
    assert manifest["provider_schedule"]["evaluation_single_analysis_only"] is True
    assert manifest["data_contract"]["evaluation_states_contain_labels"] is False
    assert manifest["thresholds"]["maximum_erroneous_direct_actions"] == 0


def test_revision_expression_is_canonicalized_to_full_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        jev,
        "_git",
        lambda *args: "29d61604c9492d2fe176fdd6d093920618ae2368",
    )

    assert jev._canonical_revision("29d61604^{commit}") == "29d61604c9492d2fe176fdd6d093920618ae2368"


def test_formal_faults_use_task_specific_build_state_and_make_directory() -> None:
    stockfish = {
        "selected_build_system": "make",
        "fault_file": "src/position.cpp",
        "build_state_file": "src/Makefile",
        "build_commands": ["make -C src -j4 build ARCH=x86-64"],
    }

    invalid = jev._formal_fault_trigger(stockfish, "invalid_build_state")
    wrong_target = jev._formal_fault_trigger(stockfish, "wrong_build_target")

    assert "src/Makefile" in invalid
    assert "make -C src -j4 build" in invalid
    assert wrong_target == f"make -C src {jev.pilot.OPAQUE_TARGET}"


def test_formal_pilot_context_restores_module_globals() -> None:
    original_identity = jev.pilot.IDENTITY
    original_fault = jev.pilot._fault_trigger_command

    with jev._formal_pilot_context():
        assert jev.pilot.IDENTITY == jev.IDENTITY
        assert jev.pilot._fault_trigger_command is jev._formal_fault_trigger

    assert jev.pilot.IDENTITY == original_identity
    assert jev.pilot._fault_trigger_command is original_fault


def test_outcome_qualification_enforces_counts_balance_and_replay() -> None:
    pool = jev.v1.load_json(jev.SOURCE_POOL)
    records = []
    optimal_actions = ("dependency", "configure", "build")
    for task in pool["tasks"]:
        for replicate in (1, 2):
            states = []
            outcomes = []
            hidden = {}
            for state_index, optimal in enumerate(optimal_actions, start=1):
                state_id = f"{task['task_id']}-state-{state_index}"
                state = {
                    "state_id": state_id,
                    "project_id": task["task_id"],
                    "project_family": task["project_family"],
                    "build_system": task["selected_build_system"],
                    "model_input": {"semantic_failure_log": f"compiler diagnostic class {state_index}"},
                }
                states.append(state)
                hidden[state_id] = jev.candidate.FAULT_TYPES[state_index - 1]
                for action in jev.candidate.ACTION_FAMILIES:
                    success = action == optimal
                    outcomes.append(
                        {
                            "state_id": state_id,
                            "action_family": action,
                            "replicate": replicate,
                            "strict_success": success,
                            "action_timed_out": False,
                            "action_exit_code": 0 if success else 1,
                            "strict_timed_out": False if success else None,
                            "replay_signature": {
                                "action_family": action,
                                "action_exit_class": "success" if success else "failure",
                                "continuation_exit_class": "success" if success else "not_run",
                                "strict_success": success,
                            },
                        }
                    )
            records.append(
                {
                    "states": states,
                    "outcomes": outcomes,
                    "reference_closure": {
                        "reference_passed": True,
                        "strict_checks": {
                            "candidate": True,
                            "functional": True,
                            "provenance": True,
                            "clean_replay": True,
                        },
                    },
                    "hidden_fault_mapping": hidden,
                }
            )

    result = jev._qualify_outcomes(records, pool)

    assert result["analysis"]["passed"] is True
    assert len(result["states"]) == 36
    assert len(result["outcomes"]) == 288
    assert result["analysis"]["replay"]["replay_consistency"] == 1.0
    for split in jev.candidate.QUALIFICATION_SPLITS:
        assert result["analysis"]["split_metrics"][split]["optimal_actions"] == {
            "build": 6,
            "configure": 6,
            "dependency": 6,
        }


def test_preflight_never_reads_credential(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    credential = tmp_path / "jev-apikey.txt"
    credential.write_text("must-not-be-read\n", encoding="utf-8")
    credential.chmod(0o600)
    monkeypatch.setattr(jev, "CREDENTIAL_FILE", credential)
    monkeypatch.setattr(jev, "validate_execution_manifest", lambda: {"identity": jev.IDENTITY})
    monkeypatch.setattr(jev, "_assert_revision", lambda manifest, require_clean: None)
    monkeypatch.setattr(jev, "AMENDMENT", Path(__file__))
    monkeypatch.setattr(jev.v1, "require_zero_managed_resources", lambda: None)
    monkeypatch.setattr(jev.v1, "current_image_id", lambda manifest: "sha256:test")
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path == credential:
            raise AssertionError("preflight 读取了 credential")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    result = jev.preflight()

    assert result["credential_reads"] == 0
    assert result["provider_calls"] == 0


def test_budget_counts_started_physical_attempt_without_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(jev, "EVIDENCE_ROOT", tmp_path)
    _write_json(tmp_path / "provider/design-round-1/attempts/01-state.json", {"state_id": "state"})

    usage = jev._budget_usage()

    assert usage == {
        "model_requests": 1,
        "completed_model_responses": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "model_cost_usd": 0.0,
    }


def test_threshold_selection_maximizes_zero_error_coverage_then_threshold() -> None:
    candidates = [
        {"calibrated_safe_probability": 0.9, "route_acceptable": True},
        {"calibrated_safe_probability": 0.8, "route_acceptable": True},
        {"calibrated_safe_probability": 0.7, "route_acceptable": False},
    ]

    selected = jev._select_zero_error_threshold(candidates)

    assert selected == {"threshold": 0.8, "coverage": 2, "errors": 0}


def test_prompt_amendment_binds_design_analysis(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(jev, "EVIDENCE_ROOT", tmp_path / "evidence")
    monkeypatch.setattr(jev, "PROMPT_AMENDMENT", tmp_path / "amendment.json")
    analysis = {"top1_correct": 14, "order_agreement_count": 15}
    _write_json(jev._stage_directory("design", 1) / "analysis.json", analysis)
    amendment = {
        "schema_version": "forge-jev-prompt-amendment-1.0.0",
        "identity": jev.IDENTITY,
        "based_on_design_round": 1,
        "design_analysis_canonical_sha256": jev.v1.canonical_sha256(analysis),
        "rationale": "Clarify evidence-specific action boundaries.",
        "instructions": "Choose one action from the supplied evidence.",
        "action_descriptions": dict(jev.candidate.ACTION_DESCRIPTIONS),
    }
    _write_json(jev.PROMPT_AMENDMENT, amendment)

    prompt = jev._prompt_contract(2)

    assert prompt["instructions"] == amendment["instructions"]
    assert prompt["action_descriptions"] == amendment["action_descriptions"]


def test_evaluation_seals_all_responses_before_label_analysis(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(jev, "EVIDENCE_ROOT", tmp_path)
    _write_json(tmp_path / "prompt-freeze.json", {"passed": True, "design_round": 1})
    _write_json(tmp_path / "calibration.json", {"passed": True})
    states = jev.validate_evaluation_states()["states"]
    monkeypatch.setattr(
        jev,
        "validate_execution_manifest",
        lambda: {
            "authorization": {
                "maximum_model_requests": 72,
                "maximum_input_tokens": 1_000_000,
                "maximum_model_cost_usd": 0.042,
            }
        },
    )
    monkeypatch.setattr(jev, "_assert_revision", lambda manifest, require_clean: None)
    monkeypatch.setattr(jev, "load_outcomes", lambda: {"analysis": {"passed": True}})
    monkeypatch.setattr(jev, "_split_states", lambda split: states)
    monkeypatch.setattr(jev, "_split_labels", lambda split: pytest.fail("响应封存前读取了 evaluation 标签"))
    monkeypatch.setattr(jev, "_read_credential", lambda: "secret")
    monkeypatch.setattr(jev, "_git", lambda *args: "c" * 40)

    class FakeClient:
        calls = 0

        def __init__(self, **kwargs: object) -> None:
            assert kwargs["api_key"] == "secret"

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def system_one(self, **kwargs: object) -> SimpleNamespace:
            self.calls += 1
            return SimpleNamespace(sequence=self.calls)

    monkeypatch.setattr(jev, "TypeSafeClient", FakeClient)

    def normalize(response: SimpleNamespace, *, latency_ms: float) -> dict[str, object]:
        return {
            "model": jev.candidate.MODEL_ID,
            "request_id": f"request-{response.sequence}",
            "answers": {},
            "usage": {"input_tokens": 10, "output_tokens": 1},
            "cost_usd": 0.00000042,
            "latency_ms": latency_ms,
        }

    monkeypatch.setattr(jev.candidate, "normalize_response", normalize)

    def analyse(split: str, responses: list[dict[str, object]]) -> dict[str, object]:
        assert split == "evaluation"
        assert len(responses) == 18
        assert len(list((tmp_path / "provider/evaluation/attempts").glob("*.json"))) == 18
        assert len(list((tmp_path / "provider/evaluation/requests").glob("*.json"))) == 18
        return {"split": split, "state_count": 18}

    monkeypatch.setattr(jev, "_analyse_predictions", analyse)

    result = jev.run_provider("evaluation", 1)

    assert result == {"split": "evaluation", "state_count": 18}
    assert jev._budget_usage()["model_requests"] == 18


def test_prediction_metrics_report_calibration_latency_and_build_systems() -> None:
    rows = []
    for index, build_system in enumerate(("cmake", "make", "autotools"), start=1):
        probabilities = {
            "dependency": 0.7,
            "configure": 0.1,
            "build": 0.1,
            "escalate_agent": 0.1,
        }
        rows.append(
            {
                "choice": "dependency",
                "optimal_action": "dependency",
                "probabilities": probabilities,
                "top1_correct": True,
                "route_acceptable": True,
                "order_agreement": True,
                "build_system": build_system,
                "latency_ms": float(index),
                "usage": {"input_tokens": 10, "output_tokens": 1},
                "cost_usd": 0.00000042,
            }
        )

    metrics = jev._prediction_metrics(rows)

    assert metrics["macro_f1"] == pytest.approx(1.0)
    assert metrics["macro_f1_classes"] == ["dependency"]
    assert metrics["multiclass_brier_score"] == pytest.approx(0.12)
    assert metrics["latency_ms"]["median"] == 2.0
    assert metrics["usage"]["input_tokens"] == 30
    assert set(metrics["by_build_system"]) == {"cmake", "make", "autotools"}


def test_frozen_failure_report_stops_before_provider_and_model_claims() -> None:
    report = jev.v1.load_json(REPO_ROOT / "benchmarks/reports/cpp-jev-offline-qualification-v1.json")

    assert report["identity"] == jev.IDENTITY
    assert report["terminal_stage"] == "outcome_qualification"
    assert report["decision"] == "stop_before_credential_read"
    assert report["controller_decision"] == "stop_jev_controller_and_keep_offline_result"
    assert report["failure"]["task_id"] == "zstd"
    assert report["failure"]["fault_type"] == "missing_compile_input"
    assert report["partial_collection"]["eligible_for_outcome_analysis"] is False
    assert report["provider_usage"] == {
        "credential_reads": 0,
        "provider_calls": 0,
        "model_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "model_cost_usd": 0.0,
        "credential_file_content_observed": False,
    }
    assert report["interpretation"]["jev_model_effect_estimated"] is False
    assert report["interpretation"]["controller_effect_estimated"] is False
