from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_offline_qualification_v5 as jev  # noqa: E402


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class _Context:
    def __enter__(self) -> _Context:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_evaluation_fixture_is_deterministic_and_label_free() -> None:
    fixture = jev.validate_evaluation_states()

    assert fixture == jev.generate_evaluation_states()
    assert fixture["contains_labels"] is False
    assert len(fixture["states"]) == 18
    payload = json.dumps(fixture, sort_keys=True)
    for forbidden in ("optimal_action", "successful_actions", "fault_type", "project_family"):
        assert forbidden not in payload


def test_execution_manifest_is_provider_only_and_freezes_route() -> None:
    manifest = jev.generate_execution_manifest(
        implementation_revision="a" * 40,
        runner_sha256="b" * 64,
    )

    assert manifest["identity"] == jev.IDENTITY
    assert manifest["implementation"]["git_revision"] == "a" * 40
    assert manifest["authorization"] == {
        "credential_read_authorized": True,
        "provider_calls_authorized": True,
        "model_calls_authorized": True,
        "maximum_model_requests": 72,
        "maximum_input_tokens": 1_000_000,
        "maximum_model_cost_usd": 0.042,
        "docker_outcome_collection_authorized": False,
        "new_identity_evidence_write_authorized": True,
        "controller_implementation_authorized": False,
        "historical_evidence_write_authorized": False,
    }
    assert manifest["data_contract"]["parent_outcomes_file_sha256"] == jev.PARENT_OUTCOMES_SHA256
    assert manifest["provider_route"]["proxy_url"] == jev.EGRESS_PROXY_URL
    assert manifest["provider_route"]["trust_environment"] is False
    assert manifest["model_resolution"] == {
        "catalog_observation_report": "benchmarks/reports/cpp-jev-offline-qualification-v4.json",
        "catalog_aliases": ["jev-latest", "jev-preview"],
        "catalog_exact_version_required": False,
        "request_model": jev.candidate.MODEL_ID,
        "response_model_must_equal_request_model": True,
        "first_design_request_establishes_callable_version": True,
        "alias_fallback_allowed": False,
        "extra_probe_request_allowed": False,
    }


def test_cli_exposes_only_provider_identity_commands() -> None:
    parser = jev._parser()
    choices = parser._subparsers._group_actions[0].choices

    assert set(choices) == {
        "bind-execution",
        "generate-evaluation-states",
        "validate",
        "preflight",
        "run-provider",
        "freeze-prompt",
        "calibrate",
        "report",
    }
    assert "collect-outcomes" not in choices
    assert "materialize-source-cache" not in choices


def test_parent_outcomes_are_frozen_qualified_and_balanced() -> None:
    outcomes = jev.load_outcomes()

    assert outcomes["identity"] == jev.PARENT_OUTCOME_IDENTITY
    assert len(outcomes["states"]) == 36
    assert len(outcomes["outcomes"]) == 288
    assert len(outcomes["reference_closures"]) == 24
    assert outcomes["analysis"]["replay"]["replay_consistency"] == 1.0
    for split in jev.candidate.QUALIFICATION_SPLITS:
        assert outcomes["analysis"]["split_metrics"][split]["optimal_actions"] == {
            "build": 6,
            "configure": 6,
            "dependency": 6,
        }


def test_parent_outcomes_reject_hash_and_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    copied = tmp_path / "outcomes.json"
    copied.write_bytes(jev.PARENT_OUTCOMES.read_bytes())
    monkeypatch.setattr(jev, "PARENT_OUTCOMES", copied)
    monkeypatch.setattr(jev, "PARENT_OUTCOMES_SHA256", "0" * 64)
    with pytest.raises(jev.ExecutionError, match="文件漂移"):
        jev.load_outcomes()

    value = json.loads(copied.read_text(encoding="utf-8"))
    value["identity"] = "wrong"
    _write_json(copied, value)
    monkeypatch.setattr(jev, "PARENT_OUTCOMES_SHA256", jev.v1.file_sha256(copied))
    with pytest.raises(jev.ExecutionError, match="资格合同未通过"):
        jev.load_outcomes()


def test_parent_catalog_records_aliases_without_model_inference() -> None:
    catalog = jev.validate_parent_catalog()

    assert catalog["identity"] == "cpp-jev-offline-qualification-v4"
    assert [row["name"] for row in catalog["observed_models"]] == [
        "jev-latest",
        "jev-preview",
    ]
    assert catalog["model_inference_performed"] is False


def test_parent_catalog_rejects_report_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report = tmp_path / "v4.json"
    report.write_bytes(jev.PARENT_CATALOG_REPORT.read_bytes())
    monkeypatch.setattr(jev, "PARENT_CATALOG_REPORT", report)
    monkeypatch.setattr(jev, "PARENT_CATALOG_REPORT_SHA256", "0" * 64)

    with pytest.raises(jev.ExecutionError, match="模型目录报告漂移"):
        jev.validate_parent_catalog()


def _docker_inspect(image: str, *, read_only: bool = True) -> dict[str, object]:
    return {
        "State": {"Running": True},
        "Image": image,
        "HostConfig": {
            "PortBindings": {jev.EGRESS_CONTAINER_PORT: [{"HostIp": "127.0.0.1", "HostPort": jev.EGRESS_HOST_PORT}]},
            "ReadonlyRootfs": read_only,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "Privileged": False,
        },
    }


def test_egress_validation_freezes_hash_runtime_and_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = tmp_path / "typesafe-config.yaml"
    config.write_text("frozen", encoding="utf-8")
    config.chmod(0o600)
    monkeypatch.setattr(jev, "EGRESS_CONFIG", config)
    monkeypatch.setattr(jev, "EGRESS_CONFIG_SHA256", jev.v1.file_sha256(config))

    def inspect(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps([_docker_inspect(jev.EGRESS_IMAGE_ID)]),
            stderr="",
        )

    monkeypatch.setattr(jev.subprocess, "run", inspect)
    assert jev.validate_egress()["passed"] is True

    def drifted(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps([_docker_inspect(jev.EGRESS_IMAGE_ID, read_only=False)]),
            stderr="",
        )

    monkeypatch.setattr(jev.subprocess, "run", drifted)
    with pytest.raises(jev.ExecutionError, match="runtime 合同漂移"):
        jev.validate_egress()


def test_preflight_never_reads_credential(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    credential = tmp_path / "jev-apikey.txt"
    credential.write_text("must-not-be-read\n", encoding="utf-8")
    credential.chmod(0o600)
    monkeypatch.setattr(jev, "CREDENTIAL_FILE", credential)
    monkeypatch.setattr(jev, "validate_execution_manifest", lambda: {"identity": jev.IDENTITY})
    monkeypatch.setattr(jev, "_assert_revision", lambda manifest, require_clean: None)
    monkeypatch.setattr(jev, "validate_egress", lambda: {"passed": True})
    monkeypatch.setattr(jev, "_git", lambda *args: "a" * 40)
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path == credential:
            raise AssertionError("preflight 读取了 credential")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    result = jev.preflight()

    assert result["credential_reads"] == 0
    assert result["provider_calls"] == 0


def test_provider_http_client_disables_environment_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(jev.httpx2, "Client", client)
    jev._provider_http_client()

    assert captured == {
        "proxy": jev.EGRESS_PROXY_URL,
        "trust_env": False,
        "timeout": 30.0,
    }


def test_provider_validates_parent_catalog_before_reading_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jev, "validate_execution_manifest", lambda: {})
    monkeypatch.setattr(jev, "_assert_revision", lambda manifest, require_clean: None)
    monkeypatch.setattr(jev, "load_outcomes", lambda: {})
    monkeypatch.setattr(
        jev,
        "validate_parent_catalog",
        lambda: (_ for _ in ()).throw(jev.ExecutionError("模型目录报告漂移")),
    )
    monkeypatch.setattr(
        jev,
        "_read_credential",
        lambda: pytest.fail("父报告门禁前读取了 credential"),
    )

    with pytest.raises(jev.ExecutionError, match="模型目录报告漂移"):
        jev.run_provider("design", 1)


def test_budget_counts_started_physical_attempt_without_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(jev, "EVIDENCE_ROOT", tmp_path)
    _write_json(tmp_path / "provider/design-round-1/attempts/01-state.json", {"state_id": "state"})

    assert jev._budget_usage() == {
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

    assert jev._select_zero_error_threshold(candidates) == {
        "threshold": 0.8,
        "coverage": 2,
        "errors": 0,
    }


def test_prompt_amendment_binds_design_analysis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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


def test_evaluation_seals_all_responses_before_label_analysis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
    monkeypatch.setattr(jev, "validate_parent_catalog", lambda: {"identity": "v4"})
    monkeypatch.setattr(jev, "validate_egress", lambda: {"passed": True})
    monkeypatch.setattr(jev, "_split_states", lambda split: states)
    monkeypatch.setattr(
        jev,
        "_split_labels",
        lambda split: pytest.fail("响应封存前读取了 evaluation 标签"),
    )
    monkeypatch.setattr(jev, "_read_credential", lambda: "secret")
    monkeypatch.setattr(jev, "_provider_http_client", _Context)
    monkeypatch.setattr(jev, "_git", lambda *args: "c" * 40)

    class FakeClient(_Context):
        calls = 0

        def __init__(self, **kwargs: object) -> None:
            assert kwargs["api_key"] == "secret"

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

    assert jev.run_provider("evaluation", 1) == {"split": "evaluation", "state_count": 18}
    assert jev._budget_usage()["model_requests"] == 18


def test_prediction_metrics_report_calibration_latency_and_build_systems() -> None:
    rows = []
    for index, build_system in enumerate(("cmake", "make", "autotools"), start=1):
        rows.append(
            {
                "choice": "dependency",
                "optimal_action": "dependency",
                "probabilities": {
                    "dependency": 0.7,
                    "configure": 0.1,
                    "build": 0.1,
                    "escalate_agent": 0.1,
                },
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
    assert metrics["multiclass_brier_score"] == pytest.approx(0.12)
    assert metrics["latency_ms"]["median"] == 2.0
    assert metrics["usage"]["input_tokens"] == 30
    assert set(metrics["by_build_system"]) == {"cmake", "make", "autotools"}
