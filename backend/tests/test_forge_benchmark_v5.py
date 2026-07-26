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
V5_MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v5.json"
V5_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-benchmark-v5.schema.json"
V5_VALIDATOR_PATH = REPO_ROOT / "scripts" / "forge_benchmark_v5.py"
V5_PROTOCOL_COMMIT = "83e807d8a441811920ceb8c9ac6ee6afe6584720"

HISTORICAL_PROTOCOL_COMMIT = "2cfbf79552ba437c67602b6c23bdd1d8d9d231a9"
V4_ORIGINAL_PROTOCOL_COMMIT = "01460235668dcd187809059030ff5d3ec0851b17"
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
    "benchmarks/manifests/cpp-pilot-v4.json": "b82440857acba0235d408c65513e12a61bea856c397929f0d7752eea7ed36f79",
    "benchmarks/schemas/forge-cpp-benchmark-v4.schema.json": "0e5200eeeb12599529ee30828e5387800bbd0cdec6b332be7850bcf0ca26eb3f",
    "scripts/forge_benchmark_v4.py": "a1cabe78ec0cabb0455ecea44e5fabf5eab41862aa614f130350d4a21792fc97",
}

SPEC = importlib.util.spec_from_file_location("forge_benchmark_v5", V5_VALIDATOR_PATH)
assert SPEC is not None
assert SPEC.loader is not None
forge_benchmark_v5 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark_v5)


def load_v5_manifest() -> dict:
    return json.loads(V5_MANIFEST_PATH.read_text(encoding="utf-8"))


def git_blob(revision: str, relative_path: str) -> bytes:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable in the minimal backend image")
    result = subprocess.run(
        [git, "show", f"{revision}:{relative_path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return result.stdout


@pytest.mark.parametrize(
    ("relative_path", "expected_sha256"),
    FROZEN_HISTORICAL_PROTOCOL_FILES.items(),
)
def test_v1_v2_v3_v4_protocol_files_remain_byte_for_byte_immutable(
    relative_path: str,
    expected_sha256: str,
) -> None:
    revision = V4_ORIGINAL_PROTOCOL_COMMIT if relative_path.endswith(("cpp-pilot-v4.json", "forge-cpp-benchmark-v4.schema.json", "forge_benchmark_v4.py")) else HISTORICAL_PROTOCOL_COMMIT
    assert hashlib.sha256(git_blob(revision, relative_path)).hexdigest() == expected_sha256


def test_v5_manifest_unblocks_only_the_new_compose_dood_protocol() -> None:
    manifest = load_v5_manifest()

    assert manifest["scope"]["instrumentation_blocker"] is False
    assert manifest["runtime"]["control_plane_topology"] == "compose-dood"
    assert manifest["forge"]["commit_sha"] == forge_benchmark_v5.BASELINE_COMMIT
    assert manifest["forge"]["revision_policy"] == forge_benchmark_v5.REVISION_POLICY
    assert forge_benchmark_v5.validate_manifest(manifest) is manifest


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda manifest: manifest["scope"].update(instrumentation_blocker=True), "runnable v5 pilot"),
        (lambda manifest: manifest["runtime"].update(control_plane_topology="wsl-native"), "compose-dood"),
        (lambda manifest: manifest["forge"].update(commit_sha="f" * 40), "Issue #32/#33/#34"),
        (lambda manifest: manifest["model"]["roles"].update(compiler="gpt-5.4"), "gpt-5.6-sol"),
    ],
)
def test_v5_manifest_rejects_protocol_drift(mutation, message: str) -> None:
    manifest = copy.deepcopy(load_v5_manifest())
    mutation(manifest)

    with pytest.raises(forge_benchmark_v5.BenchmarkError, match=message):
        forge_benchmark_v5.validate_manifest(manifest)


def test_v5_manifest_digest_is_canonical() -> None:
    manifest = load_v5_manifest()
    digest = forge_benchmark_v5.manifest_sha256(manifest)
    reparsed = json.loads(json.dumps(manifest, ensure_ascii=False, indent=4))

    assert forge_benchmark_v5.manifest_sha256(reparsed) == digest


def test_v5_runtime_components_match_the_declared_baseline() -> None:
    manifest = load_v5_manifest()
    baseline = manifest["forge"]["commit_sha"]
    for relative_path, expected_digest in manifest["forge"]["component_sha256"].items():
        assert hashlib.sha256(git_blob(baseline, relative_path)).hexdigest() == expected_digest


def test_v5_protocol_artifacts_match_the_frozen_protocol_commit() -> None:
    manifest = load_v5_manifest()

    for relative_path, expected_digest in manifest["protocol_artifact_sha256"].items():
        assert hashlib.sha256(git_blob(V5_PROTOCOL_COMMIT, relative_path)).hexdigest() == expected_digest


def test_v5_schema_tracks_the_validator_topology_and_identity_contract() -> None:
    schema = json.loads(V5_SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest_schema = schema["$defs"]["manifest"]
    forge_schema = manifest_schema["properties"]["forge"]
    runtime_schema = manifest_schema["properties"]["runtime"]

    run_record_schema = schema["$defs"]["run_record"]
    source_schema = run_record_schema["properties"]["source"]

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(load_v5_manifest())
    assert manifest_schema["properties"]["schema_version"]["const"] == "5.0.0"
    assert manifest_schema["properties"]["scope"]["properties"]["instrumentation_blocker"]["const"] is False
    assert forge_schema["properties"]["commit_sha"]["const"] == forge_benchmark_v5.BASELINE_COMMIT
    assert forge_schema["properties"]["revision_policy"]["const"] == forge_benchmark_v5.REVISION_POLICY
    assert set(forge_schema["properties"]["component_sha256"]["required"]) == forge_benchmark_v5.COMPONENT_PATHS
    assert runtime_schema["properties"]["control_plane_topology"]["const"] == "compose-dood"
    assert run_record_schema["properties"]["schema_version"]["const"] == "5.0.0"
    assert {"build_system_capabilities", "selected_build_system", "executed_build_system"}.issubset(source_schema["required"])


def test_v5_run_record_persists_explicit_build_identity_without_manifest_backfill() -> None:
    manifest = load_v5_manifest()
    case = manifest["cases"][0]
    session = {
        "session_id": "abcdef123456",
        "run_id": None,
        "repo_url": case["repository_url"],
        "commit_sha": case["commit_sha"],
        "image": manifest["runtime"]["compile_image"],
        "image_id": manifest["runtime"]["image_id"],
        "status": "inspected",
        "created_at": "2026-07-19T00:00:00+00:00",
        "completed_at": None,
        "finalized_at": None,
        "commands": [],
        "artifacts": [],
        "verification": None,
        "replay_attempts": [],
        "build_system_capabilities": ["cmake"],
        "selected_build_system": "cmake",
        "executed_build_system": None,
    }

    record = forge_benchmark_v5.build_run_record(
        manifest=manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        session=session,
        workflow_events=[],
    )

    assert record["source"]["build_system_capabilities"] == ["cmake"]
    assert record["source"]["selected_build_system"] == "cmake"
    assert record["source"]["executed_build_system"] is None
    assert record["source"]["build_system"] is None
    assert forge_benchmark_v5.validate_run_record(record) is record
    Draft202012Validator(json.loads(V5_SCHEMA_PATH.read_text(encoding="utf-8"))).validate(record)


def test_v5_run_record_preserves_selected_executed_identity_drift_before_acceptance() -> None:
    manifest = load_v5_manifest()
    case = manifest["cases"][0]
    session = {
        "session_id": "abcdef123456",
        "run_id": None,
        "repo_url": case["repository_url"],
        "commit_sha": case["commit_sha"],
        "image": manifest["runtime"]["compile_image"],
        "image_id": manifest["runtime"]["image_id"],
        "status": "inspected",
        "created_at": "2026-07-19T00:00:00+00:00",
        "commands": [],
        "artifacts": [],
        "replay_attempts": [],
        "build_system_capabilities": ["cmake", "make"],
        "selected_build_system": "cmake",
        "executed_build_system": "make",
    }

    record = forge_benchmark_v5.build_run_record(
        manifest=manifest,
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        session=session,
        workflow_events=[],
    )

    assert record["source"]["selected_build_system"] == "cmake"
    assert record["source"]["executed_build_system"] == "make"
    assert record["source"]["build_system"] == "make"
