"""Issue #208 Make runtime-parity 与 R0 observable 的零 provider 测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load(name: str, filename: str):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    path = SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load(
    "forge_opaque_provenance_make_runtime_parity_gate_test",
    "forge_opaque_provenance_make_runtime_parity_gate.py",
)
observable = _load(
    "forge_opaque_provenance_make_rejection_observability_gate_test",
    "forge_opaque_provenance_make_rejection_observability_gate.py",
)


@pytest.mark.parametrize(
    "command",
    [
        "make libhoedown.a -j2",
        "gmake -j2 libhoedown.a",
        "make -C /workspace/repo --jobs=2 libhoedown.a",
    ],
)
def test_direct_make_accepts_only_frozen_effective_identity(command: str) -> None:
    policy = gate.FrozenActionPolicy()
    gate.validate_repair_build(command, workdir=policy.workdir, policy=policy)


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("cmake --build build --target libhoedown.a", "direct make"),
        ("make -C /workspace/repo/other libhoedown.a -j2", "directory drifted"),
        ("make other -j2", "target drifted"),
        ("make libhoedown.a", "jobs drifted"),
        ("make libhoedown.a -j8", "jobs drifted"),
        ("make CFLAGS=-O3 libhoedown.a -j2", "non-preregistered"),
    ],
)
def test_direct_make_rejects_identity_or_argument_drift(
    command: str,
    message: str,
) -> None:
    policy = gate.FrozenActionPolicy()
    with pytest.raises(gate.RuntimeParityGateError, match=message):
        gate.validate_repair_build(command, workdir=policy.workdir, policy=policy)


def test_compound_make_and_stage_is_forbidden() -> None:
    with pytest.raises(gate.RuntimeParityGateError, match="must be separate actions"):
        gate.classify_action(
            "make libhoedown.a -j2 && cp libhoedown.a /artifacts/libhoedown.a",
            workdir=gate.make_lifecycle.WORKDIR,
            command_role="build",
            policy=gate.FrozenActionPolicy(),
        )


def test_observable_adapter_translates_make_rejection() -> None:
    adapter = observable.ObservableRuntimeParityToolAdapter(
        run_tool=lambda **_kwargs: "unused",
        submit_tool=lambda **_kwargs: "unused",
    )
    with pytest.raises(observable.ObservableRuntimeParityGateError) as raised:
        adapter.run(
            "make libhoedown.a -j8",
            workdir="/workspace/repo",
            command_role="build",
        )
    assert raised.value.evidence_rejection_classification == ("repair_build_arguments_invalid")
    assert raised.value.evidence_action_kind == "repair_build"


def test_action_budget_remains_atomic_4_2_2_2() -> None:
    budget = gate.AtomicActionBudget()
    before = budget.snapshot()
    with pytest.raises(gate.RuntimeParityGateError, match="submit budget exhausted"):
        budget.claim("repair_build", "submit", "submit", "submit")
    assert budget.snapshot() == before
    assert before["limits"] == {
        "inspection": 4,
        "repair_build": 2,
        "artifact_stage": 2,
        "submit": 2,
    }


def test_gate_contract_is_zero_provider_and_make_bound() -> None:
    report = gate.validate_gate_contract()
    assert report["build_system"] == "make"
    assert report["effective_directory"] == "/workspace/repo"
    assert report["target"] == "libhoedown.a"
    assert report["jobs"] == "2"
    assert (
        report["provider_calls"],
        report["formal_attempts"],
        report["model_tokens"],
        report["docker_executed"],
    ) == (0, 0, 0, False)
