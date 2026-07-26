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
V3_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v3.json"
V3_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-benchmark-v3.schema.json"
V3_VALIDATOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark_v3.py"
HISTORY_AUDITOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark_history.py"

SPEC = importlib.util.spec_from_file_location("forge_benchmark_v3", V3_VALIDATOR_PATH)
assert SPEC is not None
assert SPEC.loader is not None
forge_benchmark_v3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark_v3)

HISTORY_SPEC = importlib.util.spec_from_file_location("forge_benchmark_history_v3", HISTORY_AUDITOR_PATH)
assert HISTORY_SPEC is not None
assert HISTORY_SPEC.loader is not None
forge_benchmark_history = importlib.util.module_from_spec(HISTORY_SPEC)
sys.modules[HISTORY_SPEC.name] = forge_benchmark_history
HISTORY_SPEC.loader.exec_module(forge_benchmark_history)


def load_v3_manifest() -> dict:
    return json.loads(V3_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_v1_protocol_files_remain_byte_for_byte_immutable() -> None:
    assert hashlib.sha256(V1_MANIFEST_PATH.read_bytes()).hexdigest() == "6d73afaa476eef172fc810a63daf7ad22f0f84434bdb6300de7eb4c34269bbee"
    assert hashlib.sha256(V1_SCHEMA_PATH.read_bytes()).hexdigest() == "ad4d39978cc06ee5c4d5641f4630908a53dc8c8898be49e98632c52f80b28adb"
    assert hashlib.sha256(V1_VALIDATOR_PATH.read_bytes()).hexdigest() == "d4c18b5e558a7b29812624ea9661aab47cba610b9bc12d0050c0528bbfaa0278"


def test_v3_manifest_unblocks_only_the_new_compose_dood_protocol() -> None:
    v1_manifest = json.loads(V1_MANIFEST_PATH.read_text(encoding="utf-8"))
    v3_manifest = load_v3_manifest()

    assert v1_manifest["scope"]["instrumentation_blocker"] is True
    assert v3_manifest["scope"]["instrumentation_blocker"] is False
    assert v3_manifest["runtime"]["control_plane_topology"] == "compose-dood"
    assert v3_manifest["forge"]["commit_sha"] == forge_benchmark_v3.BASELINE_COMMIT
    assert v3_manifest["forge"]["revision_policy"] == forge_benchmark_v3.REVISION_POLICY
    assert forge_benchmark_v3.validate_manifest(v3_manifest) is v3_manifest


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda manifest: manifest["scope"].update(instrumentation_blocker=True), "runnable v3 pilot"),
        (lambda manifest: manifest["runtime"].update(control_plane_topology="wsl-native"), "compose-dood"),
        (lambda manifest: manifest["forge"].update(commit_sha="f" * 40), "Issue #16/#17/#18"),
        (lambda manifest: manifest["model"]["roles"].update(compiler="gpt-5.4"), "gpt-5.6-sol"),
    ],
)
def test_v3_manifest_rejects_protocol_drift(mutation, message: str) -> None:
    manifest = copy.deepcopy(load_v3_manifest())
    mutation(manifest)

    with pytest.raises(forge_benchmark_v3.BenchmarkError, match=message):
        forge_benchmark_v3.validate_manifest(manifest)


def test_v3_manifest_digest_is_canonical_and_current_runtime_drift_is_rejected() -> None:
    manifest = load_v3_manifest()
    digest = forge_benchmark_v3.manifest_sha256(manifest)
    reparsed = json.loads(json.dumps(manifest, ensure_ascii=False, indent=4))
    runtime_drifted_paths = {relative_path for relative_path, expected_digest in manifest["forge"]["component_sha256"].items() if hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest() != expected_digest}
    protocol_drifted_paths = {relative_path for relative_path, expected_digest in manifest["protocol_artifact_sha256"].items() if hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest() != expected_digest}

    assert forge_benchmark_v3.manifest_sha256(reparsed) == digest
    assert digest == "d67ab40eb75db7edd01dbf760ec3b01ca495c08a3bdb05f4f33f07ce90e1b92f"
    assert "backend/packages/harness/deerflow/client.py" in runtime_drifted_paths
    assert "scripts/forge_benchmark_runner.py" in protocol_drifted_paths
    with pytest.raises(
        forge_benchmark_v3.BenchmarkError,
        match=r"manifest\.forge\.component_sha256\..*: does not match the current repository file",
    ):
        forge_benchmark_v3.verify_frozen_components(manifest, REPO_ROOT)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is unavailable")
def test_v3_history_accepts_the_frozen_protocol_commit() -> None:
    result = forge_benchmark_history.audit_v3_history(
        load_v3_manifest(),
        REPO_ROOT,
        head_revision=forge_benchmark_history.V3_LINEAGE.protocol_commit,
    )

    assert result["lineage_mode"] == "audited_reviewed_successor"
    assert result["baseline_commit"] == "371f678e07acc6ae87f80d7544f573332d74fa88"
    assert result["baseline_tree_sha"] == "a7ab45a93ea763adadcad15cbce31f4c4c36849e"
    assert result["successor_commit"] == "17e09f5896ca8bf5739cec413c16402cb441209d"
    assert result["protocol_commit"] == "c4b817f315515d8afcc26d572151276aef7bece4"
    assert result["protocol_tree_sha"] == "06066746757c0a2ebda30a251a359b71eae7de70"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is unavailable")
def test_v3_history_rejects_the_unreviewed_old_fork() -> None:
    with pytest.raises(
        forge_benchmark_history.HistoryAuditError,
        match="does not descend from the v3 audited protocol successor",
    ):
        forge_benchmark_history.audit_v3_history(
            load_v3_manifest(),
            REPO_ROOT,
            head_revision="8828329896d92e8550eb1d0b3cf59bed58441987",
        )


def test_v3_runtime_components_match_the_declared_baseline() -> None:
    manifest = load_v3_manifest()
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


def test_v3_schema_tracks_the_validator_topology_and_identity_contract() -> None:
    schema = json.loads(V3_SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest_schema = schema["$defs"]["manifest"]
    forge_schema = manifest_schema["properties"]["forge"]
    runtime_schema = manifest_schema["properties"]["runtime"]

    assert manifest_schema["properties"]["schema_version"]["const"] == "3.0.0"
    assert manifest_schema["properties"]["scope"]["properties"]["instrumentation_blocker"]["const"] is False
    assert forge_schema["properties"]["commit_sha"]["const"] == forge_benchmark_v3.BASELINE_COMMIT
    assert forge_schema["properties"]["revision_policy"]["const"] == forge_benchmark_v3.REVISION_POLICY
    assert set(forge_schema["properties"]["component_sha256"]["required"]) == forge_benchmark_v3.COMPONENT_PATHS
    assert runtime_schema["properties"]["control_plane_topology"]["const"] == "compose-dood"
