"""Issue #194 runtime-parity rejection observability gate 测试。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from deerflow.compile.evidence import EvidenceError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "forge_opaque_provenance_rejection_observability_gate.py"


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("forge_opaque_provenance_rejection_observability_gate_test", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


gate = _load_module()


@pytest.mark.parametrize(
    ("command", "command_role", "classification", "action_kind"),
    [
        ("ls -la && pwd", "other", "compound_shell_forbidden", "inspection"),
        ("ls -la", "evidence", "invalid_command_role", "command"),
        (
            "cmake --build /workspace/repo/other --target accumulate_examples",
            "build",
            "repair_build_directory_drift",
            "repair_build",
        ),
        (
            "cp build/accumulate_examples /artifacts/other",
            "artifact_stage",
            "artifact_stage_identity_drift",
            "artifact_stage",
        ),
    ],
)
def test_versioned_adapter_exposes_bounded_rejection_metadata(
    command: str,
    command_role: str,
    classification: str,
    action_kind: str,
) -> None:
    adapter = gate.ObservableRuntimeParityToolAdapter(
        run_tool=lambda **_kwargs: "unused",
        submit_tool=lambda **_kwargs: "unused",
    )
    with pytest.raises((gate.ObservableRuntimeParityGateError, EvidenceError)) as captured:
        adapter.run(command, command_role=command_role)

    assert getattr(captured.value, "evidence_rejection_classification") == classification
    assert getattr(captured.value, "evidence_action_kind") == action_kind


def test_versioned_adapter_classifies_budget_exhaustion() -> None:
    adapter = gate.ObservableRuntimeParityToolAdapter(
        run_tool=lambda **_kwargs: "unused",
        submit_tool=lambda **_kwargs: "unused",
    )
    for _ in range(gate.parity.ACTION_LIMITS["inspection"]):
        adapter.run("pwd", command_role="other")
    with pytest.raises(gate.ObservableRuntimeParityGateError) as captured:
        adapter.run("pwd", command_role="other")

    assert captured.value.evidence_rejection_classification == "inspection_budget_exhausted"
    assert captured.value.evidence_action_kind == "inspection"


def test_gate_distinguishes_preregistered_rejection_classes() -> None:
    report = gate.validate_gate()
    assert report["schema_version"] == "forge-opaque-provenance-rejection-observability-gate-1.0.0"
    assert [(item["rejection_classification"], item["action_kind"]) for item in report["classifications"]] == [
        ("compound_shell_forbidden", "inspection"),
        ("invalid_command_role", "command"),
        ("repair_build_directory_drift", "repair_build"),
        ("artifact_stage_identity_drift", "artifact_stage"),
        ("inspection_budget_exhausted", "inspection"),
    ]
    assert [item["tool_ordinal"] for item in report["classifications"]] == [1, 2, 3, 4, 5]
    assert report["raw_command_persisted"] is False


def test_cli_is_zero_provider_and_ephemeral() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "validate"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    assert report["atomic_observability_fields"] == [
        "rejection_classification",
        "action_kind",
        "model_request_id",
        "tool_ordinal",
        "command_sha256",
    ]
    assert (
        report["provider_calls"],
        report["formal_attempts"],
        report["model_tokens"],
        report["docker_executed"],
        report["credential_read"],
        report["frozen_evidence_modified"],
    ) == (0, 0, 0, False, False, False)


def test_source_has_no_provider_or_frozen_evidence_entrypoint() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "create_chat_model",
        "openai_ak",
        "deepseek_api_key",
        "os.getenv",
        "execute_reachability",
        "execute_pair",
        "docker.from_env",
        "benchmark-evidence-opaque-provenance-runtime-parity-amendment-v1",
    ):
        assert forbidden not in source
