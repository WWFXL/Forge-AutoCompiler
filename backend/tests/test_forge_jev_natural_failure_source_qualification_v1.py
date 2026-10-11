from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_natural_failure_source_qualification_v1 as protocol  # noqa: E402


def test_protocol_is_valid_and_result_blind() -> None:
    result = protocol.validate_protocol()

    assert result["valid"] is True
    assert result["task_count"] == 22
    assert result["authorization"] == "candidate_only"


@pytest.mark.parametrize(
    ("build_system", "marker"),
    [
        ("cmake", "CMakeLists.txt"),
        ("make", "GNUmakefile"),
        ("autotools", "configure.ac"),
    ],
)
def test_source_contract_requires_root_entrypoint(tmp_path: Path, build_system: str, marker: str) -> None:
    assert protocol.source_contract_reason(tmp_path, build_system) is not None

    (tmp_path / marker).write_text("fixture\n", encoding="utf-8")

    assert protocol.source_contract_reason(tmp_path, build_system) is None


def test_autotools_bootstrap_precedence_is_deterministic(tmp_path: Path) -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    (tmp_path / "configure.ac").write_text("AC_INIT\n", encoding="utf-8")
    (tmp_path / "bootstrap").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "autogen.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    commands = protocol.initial_commands(tmp_path, manifest, "autotools")

    assert commands[0] == {"phase": "configure", "command": "./autogen.sh"}
    assert commands[-1] == {"phase": "build", "command": "make -j4"}


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("No targets specified and no makefile found", "configure_required"),
        ("fatal error: zlib.h: No such file or directory", "missing_dependency"),
        ("ninja: command not found", "missing_tool"),
        ("undefined reference to `forge'", "compile_error"),
        ("unclassified build failure", "unknown_build_failure"),
    ],
)
def test_error_category_is_bounded(stderr: str, expected: str) -> None:
    assert protocol.normalize_error_category("", stderr) == expected


def test_two_matching_bounded_failures_form_stable_natural_failure() -> None:
    replicates = [
        {
            "outcome": "bounded_failure",
            "failure_phase": "configure",
            "error_category": "missing_dependency",
        },
        {
            "outcome": "bounded_failure",
            "failure_phase": "configure",
            "error_category": "missing_dependency",
        },
    ]

    assert protocol._classify_task(replicates) == (
        "stable_natural_failure",
        "two_clean_replays_agree",
    )


def test_phase_or_category_drift_is_not_stable() -> None:
    replicates = [
        {
            "outcome": "bounded_failure",
            "failure_phase": "configure",
            "error_category": "missing_dependency",
        },
        {
            "outcome": "bounded_failure",
            "failure_phase": "build",
            "error_category": "compile_error",
        },
    ]

    assert protocol._classify_task(replicates)[0] == "inconsistent_failure"


def test_qualification_requires_every_system_and_role() -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    results: list[dict[str, object]] = []
    for system in protocol.SYSTEMS:
        results.extend(
            [
                {
                    "classification": "stable_natural_failure",
                    "selected_build_system": system,
                    "role": "design",
                },
                {
                    "classification": "stable_natural_failure",
                    "selected_build_system": system,
                    "role": "calibration",
                },
                {
                    "classification": "stable_natural_failure",
                    "selected_build_system": system,
                    "role": "evaluation",
                },
                {
                    "classification": "stable_natural_failure",
                    "selected_build_system": system,
                    "role": "evaluation",
                },
            ]
        )

    passed = protocol._decision(results, manifest)
    failed = protocol._decision(results[:-1], manifest)

    assert passed["passed"] is True
    assert passed["decision"] == "proceed_to_reference_recipe_qualification"
    assert failed["passed"] is False
    assert "autotools:evaluation:1<2" in failed["failed_requirements"]
