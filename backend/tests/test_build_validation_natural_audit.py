"""回顾审计不得省略失败或未观察槽位，也不得默许模型执行。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_validation_natural_audit import EXPECTED, validate_protocol  # noqa: E402


def protocol():
    return {"identity": "cpp-build-validation-natural-audit-v1", "provider_calls": 0, "docker_runs": 0, "results_previously_observed": True, "cohorts": [{"identity": key, "rows": [{}] * n} for key, n in EXPECTED.items()]}


def test_complete_fixed_denominator_is_accepted():
    validate_protocol(protocol())


@pytest.mark.parametrize("fault", ["omit_failed_slot", "duplicate_cohort", "provider", "docker", "prospective"])
def test_changed_denominator_or_execution_boundary_rejected(fault):
    p = protocol()
    if fault == "omit_failed_slot":
        p["cohorts"][0]["rows"].pop()
    elif fault == "duplicate_cohort":
        p["cohorts"].append(p["cohorts"][0])
    elif fault == "provider":
        p["provider_calls"] = 1
    elif fault == "docker":
        p["docker_runs"] = 1
    else:
        p["results_previously_observed"] = False
    with pytest.raises(ValueError):
        validate_protocol(p)
