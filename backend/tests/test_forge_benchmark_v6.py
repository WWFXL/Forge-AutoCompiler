from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v6.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-benchmark-v6.schema.json"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark_v6.py"

SPEC = importlib.util.spec_from_file_location("forge_benchmark_v6", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
forge_benchmark_v6 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark_v6)


def test_v6_manifest_freezes_post_build_handoff_baseline() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "6.0.0"
    assert manifest["forge"]["commit_sha"] == forge_benchmark_v6.BASELINE_COMMIT
    assert manifest["runtime"]["subagent_timeout_seconds"] == 300
    assert manifest["model"]["request_timeout_seconds"] == 120
    assert manifest["model"]["max_retries"] == 0
    assert forge_benchmark_v6.validate_manifest(manifest) is manifest


def test_v6_current_tree_gate_rejects_later_runtime_component_drift() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    with pytest.raises(
        forge_benchmark_v6.BenchmarkError,
        match="does not match the current repository file",
    ):
        forge_benchmark_v6.verify_frozen_components(manifest, REPO_ROOT)


def test_v6_runtime_components_match_the_declared_baseline() -> None:
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


def test_v6_schema_validates_the_frozen_manifest() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
