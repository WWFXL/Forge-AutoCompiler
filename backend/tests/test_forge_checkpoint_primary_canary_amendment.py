from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_checkpoint_primary_canary_amendment.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-amendment-candidate.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_checkpoint_primary_canary_amendment_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


amendment = _load_module()


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_candidate_is_deterministic_unauthorized_and_parent_frozen() -> None:
    manifest = _manifest()

    assert amendment.validate_manifest(manifest) == manifest
    assert amendment.generate_manifest() == manifest
    amendment.verify_frozen_components(manifest)
    assert manifest["scope"]["provider_canary_authorized"] is False
    assert manifest["scope"]["mechanism_canary_authorized"] is False
    assert manifest["scope"]["pilot_collection_authorized"] is False
    assert manifest["amendment"]["budget"]["stage_maximum_tokens"] == 245_000
    assert manifest["amendment"]["reachability_policy"] == "new_request_required_after_separate_authorization"


def test_candidate_rejects_authorization_reuse_or_budget_expansion() -> None:
    manifest = _manifest()
    manifest["scope"]["provider_canary_authorized"] = True
    with pytest.raises(amendment.AmendmentError, match="冻结候选协议"):
        amendment.validate_manifest(manifest)

    manifest = _manifest()
    manifest["amendment"]["reachability_policy"] = "reuse_parent"
    with pytest.raises(amendment.AmendmentError, match="冻结候选协议"):
        amendment.validate_manifest(manifest)

    manifest = _manifest()
    manifest["amendment"]["budget"]["stage_maximum_tokens"] += 1
    with pytest.raises(amendment.AmendmentError, match="冻结候选协议"):
        amendment.validate_manifest(manifest)


def test_new_evidence_and_markers_are_isolated_from_parent() -> None:
    manifest = _manifest()
    parent = manifest["parent"]["terminal_evidence"]
    execution = manifest["amendment"]["execution"]

    assert execution["evidence_directory"] != parent["directory"]
    parent_names = {Path(item["path"]).name for item in parent["files"]}
    assert execution["reachability_marker"] not in parent_names
    assert execution["controlled_pair_marker"] not in parent_names


def test_superseded_evidence_requires_exact_files_hashes_and_semantics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    expected_files = {item["path"]: item["sha256"] for item in manifest["parent"]["terminal_evidence"]["files"]}
    marker_identity = {
        "manifest_sha256": amendment.PARENT_MANIFEST_SHA256,
        "release_revision": amendment.PARENT_RELEASE_REVISION,
    }
    documents = {
        "markers/reachability-attempt.json": {**marker_identity, "status": "passed", "error_class": None},
        "markers/controlled-pair-attempt.json": {**marker_identity, "status": "failed", "error_class": "CanaryError"},
        "reports/reachability.json": {
            **marker_identity,
            "passed": True,
            "actual_model": "deepseek-v4-flash",
            "request_count": 1,
            "recorded_tokens": 17,
        },
        "ledgers/parent.jsonl": {},
    }
    for relative_path, document in documents.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document) + "\n", encoding="utf-8")

    original_file_sha256 = amendment.file_sha256

    def evidence_sha256(path: Path) -> str:
        if path.is_relative_to(tmp_path):
            return expected_files[path.relative_to(tmp_path).as_posix()]
        return original_file_sha256(path)

    monkeypatch.setattr(amendment, "file_sha256", evidence_sha256)
    assert amendment.verify_superseded_evidence(manifest, tmp_path)["file_count"] == 4

    extra = tmp_path / "reports" / "unexpected.json"
    extra.write_text("{}\n", encoding="utf-8")
    with pytest.raises(amendment.AmendmentError, match="文件集合"):
        amendment.verify_superseded_evidence(manifest, tmp_path)
    extra.unlink()

    pair_path = tmp_path / "markers" / "controlled-pair-attempt.json"
    pair = copy.deepcopy(documents["markers/controlled-pair-attempt.json"])
    pair["status"] = "passed"
    pair_path.write_text(json.dumps(pair) + "\n", encoding="utf-8")
    with pytest.raises(amendment.AmendmentError, match="controlled pair marker"):
        amendment.verify_superseded_evidence(manifest, tmp_path)


def test_cli_does_not_expose_provider_execution_commands() -> None:
    parser = amendment._parser()
    choices = parser._subparsers._group_actions[0].choices
    assert set(choices) == {"generate", "validate", "validate-evidence"}
