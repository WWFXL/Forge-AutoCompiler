from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
V4_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v4.json"
V4_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-benchmark-v4.schema.json"
V4_VALIDATOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark_v4.py"
V4_PROTOCOL_ARTIFACT_COMMITS = {
    "scripts/forge_benchmark.py": "ec30fac8ada1e00b2863c031999ea7acf5c1a676",
    "scripts/forge_benchmark_v4.py": "2cfbf79552ba437c67602b6c23bdd1d8d9d231a9",
    "scripts/forge_benchmark_runner.py": "2cfbf79552ba437c67602b6c23bdd1d8d9d231a9",
    "benchmarks/schemas/forge-cpp-benchmark-v4.schema.json": "2cfbf79552ba437c67602b6c23bdd1d8d9d231a9",
}

FROZEN_HISTORICAL_PROTOCOL_FILES = {
    "benchmarks/manifests/cpp-pilot-v1.json": "6d73afaa476eef172fc810a63daf7ad22f0f84434bdb6300de7eb4c34269bbee",
    "benchmarks/schemas/forge-cpp-benchmark-v1.schema.json": "ad4d39978cc06ee5c4d5641f4630908a53dc8c8898be49e98632c52f80b28adb",
    "scripts/forge_benchmark.py": "d4c18b5e558a7b29812624ea9661aab47cba610b9bc12d0050c0528bbfaa0278",
    "benchmarks/manifests/cpp-pilot-v2.json": "2c7b8f3c5921a3c34238f03df24cdd35e99ff598dd4322bfd2da8062b9587e8e",
    "benchmarks/schemas/forge-cpp-benchmark-v2.schema.json": "3ff392b252f4c97d606b71a8806c4e7d0b866b65bce322afb55b57d2f855f47b",
    "scripts/forge_benchmark_v2.py": "2cce54a84d625be33b21ecc3effe40c15c2a2ac74a94d2b1afc73a79273ce49f",
    "benchmarks/manifests/cpp-pilot-v3.json": "e58f278aa5c8d9d32ebfa2d0fff314319860b44138b4a659af72a75ee4d0f6fb",
    "benchmarks/schemas/forge-cpp-benchmark-v3.schema.json": "33748caa620f8d4c2aedb5b829992a470d5c3c68d5d40e42994d76e8df7087c2",
    "scripts/forge_benchmark_v3.py": "d18dbd22b2ef7df2063c2b6ed656d089e1c8fc1418d4c1196b73ad84a532bec6",
}

SPEC = importlib.util.spec_from_file_location("forge_benchmark_v4", V4_VALIDATOR_PATH)
assert SPEC is not None
assert SPEC.loader is not None
forge_benchmark_v4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark_v4)


def load_v4_manifest() -> dict:
    return json.loads(V4_MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("relative_path", "expected_sha256"),
    FROZEN_HISTORICAL_PROTOCOL_FILES.items(),
)
def test_v1_v2_v3_protocol_files_remain_byte_for_byte_immutable(
    relative_path: str,
    expected_sha256: str,
) -> None:
    assert hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest() == expected_sha256


def test_v4_manifest_unblocks_only_the_new_compose_dood_protocol() -> None:
    manifest = load_v4_manifest()

    assert manifest["scope"]["instrumentation_blocker"] is False
    assert manifest["runtime"]["control_plane_topology"] == "compose-dood"
    assert manifest["forge"]["commit_sha"] == forge_benchmark_v4.BASELINE_COMMIT
    assert manifest["forge"]["revision_policy"] == forge_benchmark_v4.REVISION_POLICY
    assert forge_benchmark_v4.validate_manifest(manifest) is manifest


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda manifest: manifest["scope"].update(instrumentation_blocker=True), "runnable v4 pilot"),
        (lambda manifest: manifest["runtime"].update(control_plane_topology="wsl-native"), "compose-dood"),
        (lambda manifest: manifest["forge"].update(commit_sha="f" * 40), "Issue #24/#25/#26"),
        (lambda manifest: manifest["model"]["roles"].update(compiler="gpt-5.4"), "gpt-5.6-sol"),
    ],
)
def test_v4_manifest_rejects_protocol_drift(mutation, message: str) -> None:
    manifest = copy.deepcopy(load_v4_manifest())
    mutation(manifest)

    with pytest.raises(forge_benchmark_v4.BenchmarkError, match=message):
        forge_benchmark_v4.validate_manifest(manifest)


def test_v4_manifest_digest_is_canonical() -> None:
    manifest = load_v4_manifest()
    digest = forge_benchmark_v4.manifest_sha256(manifest)
    reparsed = json.loads(json.dumps(manifest, ensure_ascii=False, indent=4))

    assert forge_benchmark_v4.manifest_sha256(reparsed) == digest


def test_v4_current_tree_gate_rejects_later_runtime_component_drift() -> None:
    manifest = load_v4_manifest()

    with pytest.raises(forge_benchmark_v4.BenchmarkError, match="does not match the current repository file"):
        forge_benchmark_v4.verify_frozen_components(manifest, REPO_ROOT)


def test_v4_runtime_components_match_the_declared_baseline() -> None:
    manifest = load_v4_manifest()
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


def test_v4_protocol_artifacts_match_the_frozen_protocol_commit() -> None:
    manifest = load_v4_manifest()
    if shutil.which("git") is None:
        pytest.skip("git is unavailable in the minimal backend image")

    for relative_path, expected_digest in manifest["protocol_artifact_sha256"].items():
        result = subprocess.run(
            ["git", "show", f"{V4_PROTOCOL_ARTIFACT_COMMITS[relative_path]}:{relative_path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        assert hashlib.sha256(result.stdout).hexdigest() == expected_digest


def test_v4_schema_tracks_the_validator_topology_and_identity_contract() -> None:
    schema = json.loads(V4_SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest_schema = schema["$defs"]["manifest"]
    forge_schema = manifest_schema["properties"]["forge"]
    runtime_schema = manifest_schema["properties"]["runtime"]

    assert manifest_schema["properties"]["schema_version"]["const"] == "4.0.0"
    assert manifest_schema["properties"]["scope"]["properties"]["instrumentation_blocker"]["const"] is False
    assert forge_schema["properties"]["commit_sha"]["const"] == forge_benchmark_v4.BASELINE_COMMIT
    assert forge_schema["properties"]["revision_policy"]["const"] == forge_benchmark_v4.REVISION_POLICY
    assert set(forge_schema["properties"]["component_sha256"]["required"]) == forge_benchmark_v4.COMPONENT_PATHS
    assert runtime_schema["properties"]["control_plane_topology"]["const"] == "compose-dood"
