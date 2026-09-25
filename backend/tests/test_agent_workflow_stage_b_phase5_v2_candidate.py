"""Issue #291 Phase 5 v2 未授权候选 identity 与 runner 门禁测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_agent_workflow_stage_b_phase5_v2_candidate_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_agent_workflow_stage_b_phase5_v2_candidate_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-agent-workflow-stage-b-phase5-v2-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v2-candidate.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_agent_workflow_stage_b_phase5_v2_candidate_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_agent_workflow_stage_b_phase5_v2_candidate_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_candidate_manifest_schema_and_qualification_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.load_qualification_result(repo_root=REPO_ROOT)["status"] == "passed"
    assert manifest["qualification"]["result_sha256"] == protocol.QUALIFICATION_RESULT_SHA256
    assert manifest["qualification"]["provider_request_count"] == 0
    assert manifest["qualification"]["formal_attempt_created"] is False
    assert manifest["parent_phase5"]["outcomes_imported"] is False
    assert manifest["evidence_candidate"]["historical_evidence_reused"] is False
    assert "historical_baseline" not in manifest


def test_candidate_freezes_capabilities_selection_and_v2_runtime() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    tasks = {task["task_id"]: task for task in manifest["tasks"]}

    assert tasks["c-ares"]["historical_build_system_label"] == "autotools"
    assert tasks["c-ares"]["build_system_capabilities"] == ["cmake", "autotools"]
    assert tasks["c-ares"]["selected_build_system"] == "cmake"
    assert manifest["runtime_candidate"]["external_evaluator"] == "external-evaluator-v2"
    assert manifest["evidence_candidate"]["directory"].endswith("stage-b-phase5-v2")
    boolean_authorizations = {key: value for key, value in manifest["authorization"].items() if key != "model_tokens_authorized"}
    assert all(value is False for value in boolean_authorizations.values())
    assert manifest["authorization"]["model_tokens_authorized"] == 0


def test_qualification_result_tamper_fails_closed(tmp_path: Path) -> None:
    result = protocol.load_qualification_result(repo_root=REPO_ROOT)
    result["tasks"][0]["selected_build_system"] = "make"
    path = tmp_path / "qualification.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(protocol.Phase5V2CandidateProtocolError, match="字节 identity"):
        protocol.load_qualification_result(path, REPO_ROOT)


def test_runner_preflight_is_zero_execution_and_real_commands_are_blocked() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)

    preflight = runner.collect_preflight(manifest, repo_root=REPO_ROOT)

    assert preflight["status"] == "candidate_valid_not_authorized"
    assert preflight["qualification_result_sha256"] == protocol.QUALIFICATION_RESULT_SHA256
    for field in ("provider_calls", "credential_reads", "docker_executions", "formal_attempts", "model_tokens", "evidence_writes"):
        assert preflight[field] == 0
    with pytest.raises(runner.Phase5V2CandidateRunnerError, match="未授权"):
        runner.execute_reachability(manifest)
    with pytest.raises(runner.Phase5V2CandidateRunnerError, match="未授权"):
        runner.run_batch(manifest)


def test_runtime_probe_and_node_input_use_qualified_build_systems() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    task = next(task for task in manifest["tasks"] if task["task_id"] == "c-ares")
    session = SimpleNamespace(
        session_id="phase5-v2-session",
        commit_sha=task["commit_sha"],
        image_id=manifest["environment_candidate"]["image_id"],
        build_system_capabilities=["cmake", "autotools"],
        selected_build_system=None,
    )

    assert runner.validate_runtime_probe(manifest, task, session, "cmake") == "cmake"
    value = runner.node_input(manifest, task, session, "phase5-v2-c-ares-attempt-1")

    assert value.build_system_candidates == ("cmake", "autotools")
    assert value.initial_observation["selected_build_system"] == "cmake"
    assert value.initial_observation["qualification_result_sha256"] == protocol.QUALIFICATION_RESULT_SHA256

    drifted = copy.deepcopy(task)
    drifted["selected_build_system"] = "autotools"
    with pytest.raises(runner.Phase5V2CandidateRunnerError, match="qualification"):
        runner.validate_runtime_probe(manifest, drifted, session, "cmake")
