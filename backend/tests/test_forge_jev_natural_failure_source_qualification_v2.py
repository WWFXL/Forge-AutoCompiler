from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_natural_failure_source_qualification_v2 as protocol  # noqa: E402


def test_protocol_is_valid_and_candidate_only() -> None:
    result = protocol.validate_protocol()

    assert result["valid"] is True
    assert result["authorization"] == "candidate_only"
    assert result["task_count"] == 24
    assert result["counts"] == {"cmake": 8, "make": 8, "autotools": 8}


@pytest.mark.parametrize(
    ("system", "marker"),
    [("cmake", "CMakeLists.txt"), ("make", "GNUmakefile"), ("autotools", "configure.ac")],
)
def test_source_contract_rechecks_root_entry(tmp_path: Path, system: str, marker: str) -> None:
    assert protocol.source_contract_reason(tmp_path, system) is not None

    (tmp_path / marker).write_text("fixture\n", encoding="utf-8")

    assert protocol.source_contract_reason(tmp_path, system) is None


def test_source_contract_rejects_catalog_submodule_drift(tmp_path: Path) -> None:
    (tmp_path / "CMakeLists.txt").write_text("fixture\n", encoding="utf-8")
    (tmp_path / ".gitmodules").write_text("fixture\n", encoding="utf-8")

    assert protocol.source_contract_reason(tmp_path, "cmake") == "submodule_contract_drift"


def test_autotools_bootstrap_precedence_is_deterministic(tmp_path: Path) -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    (tmp_path / "configure.ac").write_text("AC_INIT\n", encoding="utf-8")
    (tmp_path / "bootstrap").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "autogen.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    commands = protocol.initial_commands(tmp_path, manifest, "autotools")

    assert commands[0] == {"phase": "configure", "command": "./autogen.sh"}
    assert commands[-1] == {"phase": "build", "command": "make -j4"}


@pytest.mark.parametrize(
    ("stderr", "outcome", "category"),
    [
        ("Could not resolve host: github.com\nerror: clone failed", "network_dependency_failure", "network_dependency"),
        ("This project is only supported on macOS", "platform_incompatible", "platform_incompatible"),
        ("fatal error: zlib.h: No such file or directory", "bounded_failure", "missing_dependency"),
        ("ninja: command not found", "bounded_failure", "missing_tool"),
        ("undefined reference to `forge'", "bounded_failure", "compile_error"),
        ("unclassified failure", "bounded_failure", "unknown_build_failure"),
    ],
)
def test_failure_normalization_prioritizes_exclusions(stderr: str, outcome: str, category: str) -> None:
    assert protocol.normalize_failure("", stderr) == (outcome, category)


def test_matching_bounded_failures_form_stable_natural_failure() -> None:
    replicates = [
        {"outcome": "bounded_failure", "failure_phase": "configure", "error_category": "missing_dependency"},
        {"outcome": "bounded_failure", "failure_phase": "configure", "error_category": "missing_dependency"},
    ]

    assert protocol.classify_task(replicates) == ("stable_natural_failure", "two_clean_replays_agree")


def test_repeatable_network_failure_is_excluded() -> None:
    replicates = [
        {"outcome": "network_dependency_failure", "failure_phase": "configure", "error_category": "network_dependency"},
        {"outcome": "network_dependency_failure", "failure_phase": "configure", "error_category": "network_dependency"},
    ]

    assert protocol.classify_task(replicates) == ("network_dependency_excluded", "runtime_network_dependency")


def test_source_stage_timeout_is_structured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd=["git", "fetch"], timeout=1, output="partial", stderr="late")

    monkeypatch.setattr(protocol, "_run", timeout)

    result = protocol._run_source_stage(["git", "fetch"], cwd=tmp_path, timeout=1, env={}, stage="fetch")

    assert result["timed_out"] is True
    assert result["stage"] == "fetch"
    assert result["stdout"] == "partial"


def test_docker_timeout_is_structured_and_cleanup_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    removed: list[str] = []

    def timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=1, output="partial", stderr="late")

    monkeypatch.setattr(protocol, "_run", timeout)
    monkeypatch.setattr(protocol, "_remove_container", lambda name: removed.append(name) or True)

    result = protocol._run_build_command(
        workspace=tmp_path,
        command="make -j4",
        phase="build",
        task_id="make-example-project",
        replicate=1,
        manifest=manifest,
        remaining_session_seconds=10,
    )

    assert result["timed_out"] is True
    assert removed and removed[0].startswith("forge-413-")


def test_project_exception_does_not_stop_following_task() -> None:
    tasks = [
        {"project_family": "example/first", "selected_build_system": "cmake", "role": "design"},
        {"project_family": "example/second", "selected_build_system": "make", "role": "design"},
    ]
    observed: list[str] = []

    def process_one(task: dict[str, object]) -> dict[str, object]:
        if task["project_family"] == "example/first":
            raise TimeoutError("injected")
        return {
            "task_id": "make-example-second",
            "project_family": "example/second",
            "selected_build_system": "make",
            "role": "design",
            "classification": "initial_success",
        }

    results = protocol.process_tasks(tasks, process_one, lambda row: observed.append(str(row["project_family"])))

    assert [row["classification"] for row in results] == ["infrastructure_failure", "initial_success"]
    assert observed == ["example/first", "example/second"]


def test_batch_budget_exception_stops_batch() -> None:
    tasks = [{"project_family": "example/first", "selected_build_system": "cmake", "role": "design"}]

    with pytest.raises(protocol.BatchBudgetExceeded):
        protocol.process_tasks(tasks, lambda task: (_ for _ in ()).throw(protocol.BatchBudgetExceeded("budget")))


def test_qualification_requires_every_system_and_role() -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    results: list[dict[str, object]] = []
    for system in protocol.SYSTEMS:
        results.extend(
            [
                {"task_id": f"{system}-d", "classification": "stable_natural_failure", "selected_build_system": system, "role": "design", "cleanup_ok": True},
                {"task_id": f"{system}-c", "classification": "stable_natural_failure", "selected_build_system": system, "role": "calibration", "cleanup_ok": True},
                {"task_id": f"{system}-e1", "classification": "stable_natural_failure", "selected_build_system": system, "role": "evaluation", "cleanup_ok": True},
                {"task_id": f"{system}-e2", "classification": "stable_natural_failure", "selected_build_system": system, "role": "evaluation", "cleanup_ok": True},
            ]
        )

    passed = protocol._decision(results, manifest)
    failed = protocol._decision(results[:-1], manifest)

    assert passed["passed"] is True
    assert passed["decision"] == "proceed_to_reference_recipe_qualification_v2"
    assert failed["passed"] is False
    assert "autotools:evaluation:1<2" in failed["failed_requirements"]
