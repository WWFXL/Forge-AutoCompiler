"""Issue #216 R3 Make 单配对 candidate 的零 provider 门禁。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS_DIR / "forge_opaque_provenance_r3_make_candidate_protocol.py"
RUNNER_PATH = SCRIPTS_DIR / "forge_opaque_provenance_r3_make_candidate_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r3-make-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-r3-make-candidate.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_opaque_provenance_r3_make_candidate_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_opaque_provenance_r3_make_candidate_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_and_frozen_parent_components_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    protocol.verify_frozen_components(REPO_ROOT)
    assert manifest["parent"]["canonical_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256


def test_candidate_authorization_and_action_surface_are_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert all(value is False for key, value in manifest["authorization"].items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert manifest["authorization"]["model_tokens_authorized"] == 0
    assert manifest["checkpoint"]["status"] == "not_created"
    assert manifest["evidence"]["status"] == "not_created"
    assert manifest["schedule"][0]["arm_order"] == ["baseline", "treatment"]
    assert manifest["schedule"][0]["treatment_exposure_only"] == "repair_packet"
    assert manifest["runtime_parity"]["action_surface"]["jobs"] == {
        "omitted_allowed": True,
        "minimum": 1,
        "maximum": 2,
    }


def test_runtime_wiring_accepts_bounded_jobs_and_preserves_r0_classifications() -> None:
    result = runner.validate_runtime_gate_contract()
    assert set(result["accepted"].values()) == {"repair_build"}
    assert result["rejected"] == {
        "make -j libhoedown.a": "repair_build_jobs_unbounded",
        "make -j0 libhoedown.a": "repair_build_jobs_out_of_bounds",
        "make -j3 libhoedown.a": "repair_build_jobs_out_of_bounds",
    }
    assert result["r0_companion_event"] == "agent.tool_rejection_observed"
    assert (
        result["provider_calls"],
        result["credential_read"],
        result["docker_executed"],
        result["checkpoint_created"],
        result["formal_attempts"],
        result["model_tokens"],
        result["evidence_writes"],
    ) == (0, False, False, False, 0, 0, 0)

    adapter = runner.ObservableRuntimeParityToolAdapter(run_tool=lambda **kwargs: kwargs, submit_tool=lambda **kwargs: kwargs)
    with pytest.raises(runner.make_observability.ObservableRuntimeParityGateError) as captured:
        adapter.run("make -j libhoedown.a", command_role="build")
    assert captured.value.evidence_rejection_classification == "repair_build_jobs_unbounded"
    assert captured.value.evidence_action_kind == "repair_build"


def test_plan_and_preflight_are_read_only_and_execute_paths_fail_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    plan = runner.build_plan(manifest)
    assert plan["execution_authorized"] is False
    assert plan["treatment_exposure_only"] == "repair_packet"

    values = {
        ("git", "branch", "--show-current"): "main",
        ("git", "rev-parse", "HEAD"): protocol.AUTHORIZATION_BASELINE_COMMIT,
        ("git", "rev-parse", "origin/main"): protocol.AUTHORIZATION_BASELINE_COMMIT,
        ("git", "status", "--porcelain"): "",
        ("git", "merge-base", "--is-ancestor", protocol.AUTHORIZATION_BASELINE_COMMIT, "HEAD"): "",
    }
    candidate = REPO_ROOT / ".compile-sessions" / Path(manifest["evidence"]["directory"]).name
    snapshot = runner.collect_preflight_snapshot(
        manifest,
        repo_root=REPO_ROOT,
        host_candidate_evidence_directory=candidate,
        command_runner=lambda command, _cwd: values[tuple(command)],
    )
    assert snapshot["provider_calls"] == 0
    assert snapshot["credential_read"] is False
    assert snapshot["docker_executed"] is False
    assert snapshot["evidence_writes"] == 0
    assert not candidate.exists()

    for execute in (runner.execute_checkpoint, runner.execute_reachability, runner.execute_pair):
        with pytest.raises(runner.RuntimeGateError, match="not authorized"):
            execute(manifest)


def test_schema_and_protocol_reject_authorization_jobs_or_schedule_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    mutations = (
        ("authorization", "provider_calls_authorized", True),
        ("authorization", "model_tokens_authorized", 1),
        ("runtime_parity", "parallel_tool_calls", True),
        ("schedule", 0, []),
    )
    for section, field, value in mutations:
        drifted = copy.deepcopy(manifest)
        drifted[section][field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
            protocol.validate_manifest(drifted, REPO_ROOT)


def test_new_sources_do_not_embed_credentials_or_provider_execution() -> None:
    combined = PROTOCOL_PATH.read_text(encoding="utf-8") + RUNNER_PATH.read_text(encoding="utf-8")
    for forbidden in ("sk-", "api_key=", "OPENAI_AK", "os.environ["):
        assert forbidden not in combined
    assert "execute_reachability" in combined
    assert "not authorized by Issue #216" in combined
