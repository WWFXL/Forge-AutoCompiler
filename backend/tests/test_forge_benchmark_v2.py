from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
V1_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v1.json"
V1_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-benchmark-v1.schema.json"
V1_VALIDATOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark.py"
V2_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v2.json"
V2_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-benchmark-v2.schema.json"
V2_VALIDATOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark_v2.py"
HISTORY_AUDITOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark_history.py"

SPEC = importlib.util.spec_from_file_location("forge_benchmark_v2", V2_VALIDATOR_PATH)
assert SPEC is not None
assert SPEC.loader is not None
forge_benchmark_v2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark_v2)

HISTORY_SPEC = importlib.util.spec_from_file_location("forge_benchmark_history", HISTORY_AUDITOR_PATH)
assert HISTORY_SPEC is not None
assert HISTORY_SPEC.loader is not None
forge_benchmark_history = importlib.util.module_from_spec(HISTORY_SPEC)
sys.modules[HISTORY_SPEC.name] = forge_benchmark_history
HISTORY_SPEC.loader.exec_module(forge_benchmark_history)


def load_v2_manifest() -> dict:
    return json.loads(V2_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_v1_protocol_files_remain_byte_for_byte_immutable() -> None:
    assert hashlib.sha256(V1_MANIFEST_PATH.read_bytes()).hexdigest() == "6d73afaa476eef172fc810a63daf7ad22f0f84434bdb6300de7eb4c34269bbee"
    assert hashlib.sha256(V1_SCHEMA_PATH.read_bytes()).hexdigest() == "ad4d39978cc06ee5c4d5641f4630908a53dc8c8898be49e98632c52f80b28adb"
    assert hashlib.sha256(V1_VALIDATOR_PATH.read_bytes()).hexdigest() == "d4c18b5e558a7b29812624ea9661aab47cba610b9bc12d0050c0528bbfaa0278"


def test_v2_manifest_unblocks_only_the_new_compose_dood_protocol() -> None:
    v1_manifest = json.loads(V1_MANIFEST_PATH.read_text(encoding="utf-8"))
    v2_manifest = load_v2_manifest()

    assert v1_manifest["scope"]["instrumentation_blocker"] is True
    assert v2_manifest["scope"]["instrumentation_blocker"] is False
    assert v2_manifest["runtime"]["control_plane_topology"] == "compose-dood"
    assert v2_manifest["forge"]["commit_sha"] == forge_benchmark_v2.BASELINE_COMMIT
    assert v2_manifest["forge"]["revision_policy"] == forge_benchmark_v2.REVISION_POLICY
    assert forge_benchmark_v2.validate_manifest(v2_manifest) is v2_manifest


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda manifest: manifest["scope"].update(instrumentation_blocker=True), "runnable v2 pilot"),
        (lambda manifest: manifest["runtime"].update(control_plane_topology="wsl-native"), "compose-dood"),
        (lambda manifest: manifest["forge"].update(commit_sha="f" * 40), "Issue #11"),
        (lambda manifest: manifest["model"]["roles"].update(compiler="gpt-5.4"), "gpt-5.6-sol"),
    ],
)
def test_v2_manifest_rejects_protocol_drift(mutation, message: str) -> None:
    manifest = copy.deepcopy(load_v2_manifest())
    mutation(manifest)

    with pytest.raises(forge_benchmark_v2.BenchmarkError, match=message):
        forge_benchmark_v2.validate_manifest(manifest)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is unavailable")
def test_v2_manifest_digest_is_canonical_and_current_runner_drift_is_rejected() -> None:
    manifest = load_v2_manifest()
    digest = forge_benchmark_v2.manifest_sha256(manifest)
    reparsed = json.loads(json.dumps(manifest, ensure_ascii=False, indent=4))

    assert forge_benchmark_v2.manifest_sha256(reparsed) == digest
    assert digest == "6f29c0f06b5c6e72f9cf0d38afb35be3a61d304ad2ed4f2556a29b5cd7a1422b"
    with pytest.raises(
        forge_benchmark_history.HistoryAuditError,
        match=r"frozen protocol artifact mismatch: scripts/forge_benchmark_runner\.py",
    ):
        forge_benchmark_history.audit_v2_history(manifest, REPO_ROOT)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is unavailable")
def test_v2_history_rejects_an_unrelated_head() -> None:
    manifest = load_v2_manifest()

    with pytest.raises(
        forge_benchmark_history.HistoryAuditError,
        match="does not descend",
    ):
        forge_benchmark_history.audit_v2_history(
            manifest,
            REPO_ROOT,
            head_revision="9ef57c50193ace14b6f8b761e09cced21e92f08e",
        )


def test_v2_runtime_components_match_the_declared_baseline() -> None:
    manifest = load_v2_manifest()
    baseline = manifest["forge"]["commit_sha"]
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable in the minimal backend image")
    for relative_path, expected_digest in manifest["forge"]["component_sha256"].items():
        result = subprocess.run(
            [git, "show", f"{baseline}:{relative_path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        assert hashlib.sha256(result.stdout).hexdigest() == expected_digest


def test_v2_schema_tracks_the_validator_topology_and_identity_contract() -> None:
    schema = json.loads(V2_SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest_schema = schema["$defs"]["manifest"]
    forge_schema = manifest_schema["properties"]["forge"]
    runtime_schema = manifest_schema["properties"]["runtime"]

    assert manifest_schema["properties"]["schema_version"]["const"] == "2.0.0"
    assert manifest_schema["properties"]["scope"]["properties"]["instrumentation_blocker"]["const"] is False
    assert forge_schema["properties"]["commit_sha"]["const"] == forge_benchmark_v2.BASELINE_COMMIT
    assert forge_schema["properties"]["revision_policy"]["const"] == forge_benchmark_v2.REVISION_POLICY
    assert set(forge_schema["properties"]["component_sha256"]["required"]) == forge_benchmark_v2.COMPONENT_PATHS
    assert runtime_schema["properties"]["control_plane_topology"]["const"] == "compose-dood"
