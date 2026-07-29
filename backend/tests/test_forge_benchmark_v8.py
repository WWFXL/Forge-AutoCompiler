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
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v8.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-benchmark-v8.schema.json"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark_v8.py"
V8_PROTOCOL_COMMIT = "c7977ab7d72f5060d14bfd22754363052a687b0f"

SPEC = importlib.util.spec_from_file_location("forge_benchmark_v8", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
forge_benchmark_v8 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark_v8)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_v8_manifest_freezes_independent_provider_conditions_and_order() -> None:
    manifest = load_manifest()

    assert manifest["schema_version"] == "8.0.0"
    assert manifest["forge"]["commit_sha"] == forge_benchmark_v8.BASELINE_COMMIT
    assert {key: manifest["runtime"][key] for key in forge_benchmark_v8.RUNTIME_BUDGETS} == forge_benchmark_v8.RUNTIME_BUDGETS
    assert manifest["model_profiles"] == forge_benchmark_v8.MODEL_PROFILES
    assert {condition["id"]: condition["model_profile"] for condition in manifest["conditions"]} == forge_benchmark_v8.CONDITION_PROFILES
    assert manifest["collection_plan"] == list(forge_benchmark_v8.COLLECTION_PLAN)
    assert len(manifest["collection_plan"]) == 10
    assert forge_benchmark_v8.validate_manifest(manifest) is manifest


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (
            ("model_profiles", "richlab-gpt-5.5", "roles", "lead"),
            "gpt-5.4",
            "model_profiles",
        ),
        (
            ("model_profiles", "deepseek-v4-flash", "fallback_policy"),
            "allowed",
            "model_profiles",
        ),
        (
            ("conditions", 1, "model_profile"),
            "richlab-gpt-5.5",
            "conditions",
        ),
        (
            ("collection_plan", 0, "condition_id"),
            "deepseek-v4-flash",
            "collection_plan",
        ),
    ],
)
def test_v8_validator_rejects_provider_or_order_drift(
    path: tuple[str | int, ...],
    value: object,
    message: str,
) -> None:
    drifted = copy.deepcopy(load_manifest())
    target = drifted
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value

    with pytest.raises(forge_benchmark_v8.BenchmarkError, match=message):
        forge_benchmark_v8.validate_manifest(drifted)


@pytest.mark.parametrize(
    ("budget_name", "invalid_value"),
    [
        ("model_turn_limit", 35),
        ("graph_recursion_limit", 95),
        ("wall_clock_timeout_seconds", 899),
        ("post_build_reserve_seconds", 119),
    ],
)
def test_v8_validator_rejects_budget_drift(
    budget_name: str,
    invalid_value: int,
) -> None:
    drifted = copy.deepcopy(load_manifest())
    drifted["runtime"][budget_name] = invalid_value

    with pytest.raises(forge_benchmark_v8.BenchmarkError, match=budget_name):
        forge_benchmark_v8.validate_manifest(drifted)


def test_v8_current_tree_gate_rejects_post_collection_runner_drift() -> None:
    manifest = load_manifest()

    with pytest.raises(
        forge_benchmark_v8.BenchmarkError,
        match="does not match the current repository file",
    ):
        forge_benchmark_v8.verify_frozen_components(manifest, REPO_ROOT)


def test_v8_runtime_components_match_the_declared_baseline() -> None:
    manifest = load_manifest()
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


def test_v8_protocol_artifacts_match_the_frozen_protocol_commit() -> None:
    manifest = load_manifest()
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable in the minimal backend image")

    for relative_path, expected_digest in manifest["protocol_artifact_sha256"].items():
        result = subprocess.run(
            [git, "show", f"{V8_PROTOCOL_COMMIT}:{relative_path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        assert hashlib.sha256(result.stdout).hexdigest() == expected_digest


def test_v8_schema_validates_the_frozen_manifest() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
