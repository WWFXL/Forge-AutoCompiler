"""Issue #220 R3 Make 失败审计与安全门禁的零 provider 测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.compile.evidence import ExperimentLedger

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_r3_make_execution_failure_gate.py"


def _load_module():
    scripts = str(SCRIPT_PATH.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(
        "forge_opaque_provenance_r3_make_execution_failure_gate_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_module()


def test_runtime_bindings_combine_r3_adapter_with_r0_registry() -> None:
    parity, observability = gate.build_runtime_bindings()
    assert parity.FrozenActionPolicy is gate.r3_candidate.R3ActionPolicy
    assert parity.SerialToolCallMiddleware is gate.make_parity.SerialToolCallMiddleware
    assert observability.ObservableRuntimeParityToolAdapter is gate.r3_candidate.ObservableRuntimeParityToolAdapter
    assert observability.RejectionObservationRegistry is gate.make_observability.RejectionObservationRegistry
    assert observability.OBSERVATION_EVENT == "agent.tool_rejection_observed"


def test_zero_request_error_is_mechanism_invalid_not_no_submit(
    tmp_path: Path,
) -> None:
    ledger = ExperimentLedger.create(
        tmp_path / "arm.jsonl",
        experiment_id="experiment_11111111111111111111111111111111",
        physical_attempt_id="mechanism_attempt_11111111111111111111111111111111",
        context={"arm": "baseline"},
    )
    result = gate.classify_pre_model_failure(
        arm="baseline",
        ledger=ledger,
        error=AttributeError("missing runtime binding"),
    )
    assert result is not None
    assert result["status"] == "invalid"
    assert result["valid_behavioral_observation"] is False
    assert result["model_behavior"] == {
        "status": "not_observed",
        "terminal_error_class": "AttributeError",
    }
    assert result["model_requests"] == result["recorded_tokens"] == 0
    terminal = ledger.read()[-1]
    assert terminal["payload"] == {
        "status": "invalid_mechanism_attempt",
        "classification": "pre_model_execution_error",
        "terminal_error_class": "AttributeError",
    }


def test_request_evidence_defers_to_existing_behavioral_classifier(
    tmp_path: Path,
) -> None:
    ledger = ExperimentLedger.create(
        tmp_path / "arm.jsonl",
        experiment_id="experiment_22222222222222222222222222222222",
        physical_attempt_id="mechanism_attempt_22222222222222222222222222222222",
        context={"arm": "treatment"},
    )
    ledger.append("model.request_started", {"request": 1})
    before = ledger.read()
    assert (
        gate.classify_pre_model_failure(
            arm="treatment",
            ledger=ledger,
            error=TimeoutError(),
        )
        is None
    )
    assert ledger.read() == before


def test_cleanup_deactivates_all_contexts_before_gate_cleanup() -> None:
    calls: list[tuple[str, str | None]] = []

    class FakeGate:
        def cleanup(self, capture_id: str, *, parent_session):
            calls.append(("cleanup", parent_session.session_id))
            return SimpleNamespace(phase="cleaned")

    result = gate.cleanup_after_deactivation(
        FakeGate(),
        "capture-1",
        parent_session=SimpleNamespace(session_id="parent-1"),
        experiment_thread_ids=["parent", "baseline", "treatment", "baseline"],
        deactivate=lambda thread_id: calls.append(("deactivate", thread_id)),
    )
    assert result.phase == "cleaned"
    assert calls == [
        ("deactivate", "parent"),
        ("deactivate", "baseline"),
        ("deactivate", "treatment"),
        ("cleanup", "parent-1"),
    ]
    with pytest.raises(gate.FailureGateError, match="explicit experiment"):
        gate.cleanup_after_deactivation(
            FakeGate(),
            "capture-1",
            parent_session=SimpleNamespace(session_id="parent-1"),
            experiment_thread_ids=[],
        )


def test_sidecar_is_create_once(tmp_path: Path) -> None:
    path = tmp_path / "reports/failure-audit-v1.json"
    gate.write_sidecar_once(path, {"status": "audited"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "audited"}
    with pytest.raises(gate.FailureGateError, match="already exists"):
        gate.write_sidecar_once(path, {"status": "drifted"})


def test_source_has_no_provider_credential_or_docker_execution() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "ExperimentLedger.open" in source
    assert 'path.open("x"' in source
    for forbidden in (
        "create_chat_model",
        "DEEPSEEK_API_KEY",
        "os.environ",
        "docker.from_env",
        "subprocess.run",
        "requests.",
        "httpx.",
    ):
        assert forbidden not in source
