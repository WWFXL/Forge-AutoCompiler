from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
IDENTITY_PATH = REPO_ROOT / "benchmarks" / "runtime-identities" / "compile-runtime-v3.json"
V2_IDENTITY_PATH = REPO_ROOT / "benchmarks" / "runtime-identities" / "compile-runtime-v2.json"
V2_DOCUMENT_PATH = REPO_ROOT / "docs" / "compile_runtime_v2.md"


def _identity() -> dict:
    return json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))


def test_compile_runtime_v3_identity_is_explicitly_non_experimental() -> None:
    identity = _identity()

    assert set(identity) == {
        "schema_version",
        "identity",
        "status",
        "issued_on",
        "issue_url",
        "predecessor",
        "authorization",
        "contracts",
        "component_sha256",
    }
    assert identity["schema_version"] == "forge-compile-runtime-identity-v1"
    assert identity["identity"] == "forge-compile-runtime-v3"
    assert identity["status"] == "engineering_validation"
    assert identity["authorization"] == {
        "interactive_product_validation": True,
        "provider_experiment_execution": False,
        "formal_collection": False,
    }
    assert identity["predecessor"]["historical_manifests_immutable"] is True
    assert identity["predecessor"]["historical_evidence_immutable"] is True


def test_compile_runtime_v3_component_hashes_match_current_product_code() -> None:
    identity = _identity()

    for relative_path, expected_sha256 in identity["component_sha256"].items():
        payload = (REPO_ROOT / relative_path).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_sha256


def test_compile_runtime_v3_preserves_the_predecessor_in_git_history() -> None:
    identity = _identity()
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is required to audit the predecessor runtime")
    predecessor = identity["predecessor"]["commit_sha"]

    exists = subprocess.run(
        [git, "cat-file", "-e", f"{predecessor}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    assert exists.returncode == 0
    operations_path = "backend/packages/harness/deerflow/compile/operations.py"
    historical = subprocess.run(
        [git, "show", f"{predecessor}:{operations_path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    assert hashlib.sha256(historical.stdout).hexdigest() != identity["component_sha256"][operations_path]


def test_compile_runtime_v2_identity_and_document_remain_frozen() -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is required to audit the predecessor runtime")
    predecessor = _identity()["predecessor"]["commit_sha"]

    for path in (V2_IDENTITY_PATH, V2_DOCUMENT_PATH):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        historical = subprocess.run(
            [git, "show", f"{predecessor}:{relative_path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        ).stdout
        assert path.read_bytes() == historical
