from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_contract_repair_design_sensitivity.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "forge_contract_repair_design_sensitivity_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sensitivity = _load_module()


def test_exact_two_sided_binomial_probability() -> None:
    assert sensitivity.exact_two_sided_binomial_p(6, 6) == pytest.approx(0.03125)
    assert sensitivity.exact_two_sided_binomial_p(5, 6) == pytest.approx(0.21875)
    assert sensitivity.exact_two_sided_binomial_p(0, 0) == 1.0


def test_candidate_sensitivity_and_sample_size_are_stable() -> None:
    report = sensitivity.build_report()
    effect = next(item for item in report["sensitivity"] if item["absolute_effect"] == 1 / 3)

    powers = [scenario["power"] for scenario in effect["scenarios"]]
    assert min(powers) == pytest.approx(0.164052, abs=1e-6)
    assert max(powers) == pytest.approx(0.196004, abs=1e-6)
    assert [item["minimum_checkpoints"] for item in report["sample_size_sensitivity"]] == [23, 36, 56]
    assert [item["three_arm_count"] for item in report["sample_size_sensitivity"]] == [69, 108, 168]


def test_cli_validate_emits_non_authorizing_report() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "validate"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)

    assert report["status"] == "design_sensitivity_only"
    assert report["candidate_checkpoint_count"] == 12
    assert report["candidate_arm_count"] == 36
    assert "not a formal outcome or authorization" in report["interpretation_boundary"]
