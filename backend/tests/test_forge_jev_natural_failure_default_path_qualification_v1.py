from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_jev_natural_failure_default_path_qualification_v1.py"
SPEC = importlib.util.spec_from_file_location("forge_jev_natural_failure_default_path_qualification_v1", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)


def _result(
    *,
    system: str,
    rank: int,
    classification: str = "stable_failure_candidate",
    full_name: str | None = None,
) -> dict[str, Any]:
    return {
        "case_id": f"{system}-{rank:02d}",
        "build_system": system,
        "system_rank": rank,
        "role": qualification._role_for_rank(rank),
        "full_name": full_name or f"example/{system}-{rank}",
        "observations": [{}, {}],
        "default_path": {"classification": classification},
        "project_qualification": {"eligible_as_natural_failure": False},
    }


def test_load_cases_freezes_parent_population_and_roles() -> None:
    cases = qualification.load_cases()

    assert len(cases) == 36
    assert len({row["project_family"] for row in cases}) == 36
    for system in qualification.SYSTEMS:
        system_cases = [row for row in cases if row["build_system"] == system]
        assert [row["system_rank"] for row in system_cases] == list(range(1, 13))
        assert [row["role"] for row in system_cases].count("design") == 3
        assert [row["role"] for row in system_cases].count("calibration") == 3
        assert [row["role"] for row in system_cases].count("evaluation") == 6


def test_evaluate_qualification_passes_only_with_all_role_quotas(monkeypatch) -> None:
    monkeypatch.setattr(qualification, "managed_containers", lambda: [])
    results = [_result(system=system, rank=rank) for system in qualification.SYSTEMS for rank in range(1, 13)]

    value = qualification.evaluate_qualification(results)

    assert value["passed"] is True
    assert value["decision"] == "proceed_to_formal_reference_closure_qualification_v1"


def test_evaluate_qualification_stops_when_fixed_role_quota_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(qualification, "managed_containers", lambda: [])
    results = [
        _result(
            system=system,
            rank=rank,
            classification=("stable_host_userland_closure" if system == "cmake" and rank in {4, 5, 6} else "stable_failure_candidate"),
        )
        for system in qualification.SYSTEMS
        for rank in range(1, 13)
    ]

    value = qualification.evaluate_qualification(results)

    assert value["passed"] is False
    assert value["decision"] == "stop_natural_failure_build_reference_qualification_v1"
    assert "stable_candidate_quota:cmake:calibration:0<1" in value["failed_requirements"]


def test_known_non_host_project_cannot_count_as_failure_candidate(monkeypatch) -> None:
    monkeypatch.setattr(qualification, "managed_containers", lambda: [])
    results = [_result(system=system, rank=rank) for system in qualification.SYSTEMS for rank in range(1, 13)]
    results[0]["full_name"] = "seL4/seL4"

    value = qualification.evaluate_qualification(results)

    assert value["passed"] is False
    assert any(item.startswith("known_non_host_not_excluded:seL4/seL4") for item in value["failed_requirements"])


def test_protocol_is_valid() -> None:
    value = qualification.validate_protocol()

    assert value["valid"] is True, value["errors"]
    assert value["candidate_count"] == 36
