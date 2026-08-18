from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_checkpoint_primary_canary_amendment_authorized.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-amendment-authorized.json"
CANDIDATE_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-amendment-candidate.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_checkpoint_primary_canary_amendment_authorized_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


authorized = _load_module()


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_authorized_manifest_is_deterministic_bounded_and_parent_frozen() -> None:
    manifest = _manifest()

    assert authorized.generate_manifest() == manifest
    assert authorized.validate_manifest(manifest) == manifest
    authorized.verify_frozen_artifacts(manifest)
    assert manifest["scope"] == {
        "provider_canary_authorized": True,
        "mechanism_canary_authorized": True,
        "pilot_collection_authorized": False,
        "natural_collection_authorized": False,
        "secondary_provider_authorized": False,
    }
    assert manifest["authorization"]["authorized_reachability_attempts"] == 1
    assert manifest["authorization"]["authorized_controlled_pairs"] == 1
    assert manifest["budget"]["stage_maximum_tokens"] == 245_000
    assert manifest["parent_candidate"]["canonical_sha256"] == authorized.CANDIDATE_CANONICAL_SHA256
    assert "scripts/forge_checkpoint_primary_canary_amendment.py" in {artifact["path"] for artifact in manifest["protocol_artifacts"]}


def test_authorized_manifest_rejects_budget_pilot_and_candidate_drift() -> None:
    manifest = _manifest()
    manifest["budget"]["stage_maximum_tokens"] += 1
    with pytest.raises(authorized.AuthorizedAmendmentError, match="冻结授权协议"):
        authorized.validate_manifest(manifest)

    manifest = _manifest()
    manifest["scope"]["pilot_collection_authorized"] = True
    with pytest.raises(authorized.AuthorizedAmendmentError, match="冻结授权协议"):
        authorized.validate_manifest(manifest)

    manifest = _manifest()
    manifest["parent_candidate"]["canonical_sha256"] = "0" * 64
    with pytest.raises(authorized.AuthorizedAmendmentError, match="冻结授权协议"):
        authorized.validate_manifest(manifest)


def test_candidate_manifest_cannot_pass_authorized_validation() -> None:
    candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    with pytest.raises(authorized.AuthorizedAmendmentError, match="冻结授权协议"):
        authorized.validate_manifest(candidate)


def test_release_identity_requires_authorization_baseline_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    monkeypatch.setattr(
        authorized,
        "_parent_release_identity",
        lambda _manifest, _repo_root: {
            "branch": "main",
            "revision": "a" * 40,
            "origin_main": "a" * 40,
        },
    )
    monkeypatch.setattr(
        authorized.primary_canary,
        "_git",
        lambda _repo_root, *_arguments: authorized.AUTHORIZATION_BASELINE,
    )
    assert authorized.require_release_identity(manifest)["branch"] == "main"

    monkeypatch.setattr(
        authorized.primary_canary,
        "_git",
        lambda _repo_root, *_arguments: "b" * 40,
    )
    with pytest.raises(authorized.AuthorizedAmendmentError, match="不是授权 baseline 的后代"):
        authorized.require_release_identity(manifest)


def test_execution_wrappers_require_old_evidence_and_apply_build_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    calls: list[str] = []

    monkeypatch.setattr(authorized, "verify_superseded_evidence", lambda _manifest: calls.append("evidence"))
    monkeypatch.setattr(
        authorized.primary_canary,
        "run_reachability",
        lambda *_args, **_kwargs: {"passed": True},
    )

    def pair(*_args, **_kwargs):
        calls.append(authorized.primary_canary.BUILD_OUTPUT)
        return {"passed": True}

    monkeypatch.setattr(authorized.primary_canary, "run_controlled_pair", pair)
    assert authorized.run_reachability(manifest)["passed"] is True
    assert authorized.run_controlled_pair(manifest)["passed"] is True
    assert calls == ["evidence", "evidence", ".forge-cmake-build/accumulate_examples"]
    assert authorized.primary_canary.BUILD_OUTPUT == "build/accumulate_examples"


def test_authorized_cli_exposes_only_bounded_execution_commands() -> None:
    parser = authorized._parser()
    action = next(action for action in parser._actions if action.dest == "command")
    assert set(action.choices) == {
        "generate",
        "validate",
        "validate-evidence",
        "reachability",
        "controlled-pair",
    }

    candidate_choices = authorized.candidate_protocol._parser()._subparsers._group_actions[0].choices
    assert set(candidate_choices) == {"generate", "validate", "validate-evidence"}
