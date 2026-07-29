from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v7.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-benchmark-v7.schema.json"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark_v7.py"

SPEC = importlib.util.spec_from_file_location("forge_benchmark_v7", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
forge_benchmark_v7 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark_v7)


def test_v7_manifest_freezes_post_v6_diagnostics_and_separate_budgets() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "7.0.0"
    assert manifest["forge"]["commit_sha"] == forge_benchmark_v7.BASELINE_COMMIT
    assert {key: manifest["runtime"][key] for key in forge_benchmark_v7.RUNTIME_BUDGETS} == forge_benchmark_v7.RUNTIME_BUDGETS
    assert "compiler_max_turns" not in manifest["runtime"]
    assert "subagent_timeout_seconds" not in manifest["runtime"]
    assert manifest["model"]["request_timeout_seconds"] == 120
    assert manifest["model"]["max_retries"] == 0
    assert forge_benchmark_v7.validate_manifest(manifest) is manifest


@pytest.mark.parametrize(
    ("budget_name", "invalid_value"),
    [
        ("model_turn_limit", 35),
        ("graph_recursion_limit", 95),
        ("wall_clock_timeout_seconds", 899),
        ("post_build_reserve_seconds", 119),
    ],
)
def test_v7_validator_rejects_budget_drift(
    budget_name: str,
    invalid_value: int,
) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    drifted = copy.deepcopy(manifest)
    drifted["runtime"][budget_name] = invalid_value

    with pytest.raises(forge_benchmark_v7.BenchmarkError, match=budget_name):
        forge_benchmark_v7.validate_manifest(drifted)


def test_v7_current_tree_gate_rejects_post_collection_runner_drift() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    with pytest.raises(
        forge_benchmark_v7.BenchmarkError,
        match="does not match the current repository file",
    ):
        forge_benchmark_v7.verify_frozen_components(manifest, REPO_ROOT)


def test_v7_runtime_components_match_the_declared_baseline() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable in the minimal backend image")

    for relative_path, expected_digest in manifest["forge"]["component_sha256"].items():
        result = subprocess.run(
            [git, "show", f"{manifest['forge']['commit_sha']}:{relative_path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        assert hashlib.sha256(result.stdout).hexdigest() == expected_digest


def test_v7_schema_validates_the_frozen_manifest() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
