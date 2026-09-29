"""Issue #353 契约驱动修复 mechanism v1 未授权候选门禁。"""

from __future__ import annotations

import copy
import importlib.util
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_candidate_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_contract_driven_repair_mechanism_v1_candidate_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-candidate.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-contract-driven-repair-mechanism-v1-candidate.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module(
    "forge_contract_driven_repair_mechanism_v1_candidate_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_contract_driven_repair_mechanism_v1_candidate_runner_test",
    RUNNER_PATH,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_and_const_schema_are_deterministic() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)

    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.generate_schema(manifest)
    assert protocol.generate_manifest(REPO_ROOT) == protocol.generate_manifest(REPO_ROOT)
    assert protocol.load_manifest(repo_root=REPO_ROOT) == manifest


def test_result_blind_sample_is_frozen_and_qualified() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)

    assert [task["task_id"] for task in manifest["tasks"]] == list(protocol.EXPECTED_TASK_IDS)
    assert {(task["source"]["build_system_stratum"], task["source"]["size_stratum"]) for task in manifest["tasks"]} == {
        ("cmake", "small"),
        ("cmake", "medium"),
        ("make", "small"),
        ("make", "medium"),
        ("autotools", "small"),
        ("autotools", "medium"),
    }
    assert all(task["qualification"]["passed"] is True for task in manifest["tasks"])
    assert all(task["historical_model_outcomes_imported"] is False for task in manifest["tasks"])
    assert all(task["contract"]["functional_oracle"]["exposed_to_model"] is False for task in manifest["tasks"])


def test_schedule_has_two_strata_all_permutations_and_opaque_identities() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    schedule = manifest["schedule"]
    checkpoints = schedule["checkpoints"]

    assert len(checkpoints) == 12
    assert sum(len(checkpoint["arms"]) for checkpoint in checkpoints) == 36
    assert Counter(project["stratum_order"][0] for project in schedule["projects"]) == Counter({"delivery_target": 3, "provenance": 3})
    expected = Counter(itertools.permutations(protocol.ARMS))
    for stratum in protocol.STRATA:
        assert Counter(tuple(checkpoint["arm_order"]) for checkpoint in checkpoints if checkpoint["stratum"] == stratum) == expected
    clone_ids = [arm["opaque_clone_id"] for item in checkpoints for arm in item["arms"]]
    evaluation_ids = [arm["opaque_evaluation_id"] for item in checkpoints for arm in item["arms"]]
    assert len(set(clone_ids)) == len(set(evaluation_ids)) == 36
    assert all(value.startswith("clone-") for value in clone_ids)
    assert all(value.startswith("evaluation-") for value in evaluation_ids)


def test_provider_budget_analysis_and_stop_rules_match_frozen_decision() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    provider = manifest["provider_candidate"]
    budget = manifest["budget_candidate"]
    analysis = manifest["analysis"]

    assert provider["profile"] == provider["actual_model"] == "deepseek-flash"
    assert budget["per_arm"]["max_model_request_attempts"] == 8
    assert budget["per_arm"]["max_recorded_tokens"] is None
    assert budget["formal_arm_count"] == 36
    assert budget["formal_arms_total_max_model_request_attempts"] == 288
    assert budget["total_provider_request_attempts_including_availability_max"] == 290
    assert budget["total_max_recorded_tokens"] is None
    assert budget["token_accounting"] == {
        "mode": "meter_each_request_without_ceiling",
        "record_input_tokens": True,
        "record_output_tokens": True,
        "record_total_tokens": True,
        "token_total_is_termination_condition": False,
    }
    assert budget["monetary_stop_rule"] is None
    assert analysis["primary"]["comparison"] == "c0_vs_t1"
    assert analysis["primary"]["minimum_meaningful_effect"] == "1/3"
    assert analysis["secondary"]["comparison"] == "t1_vs_t2"
    assert analysis["secondary"]["minimum_meaningful_effect"] == "1/6"
    assert analysis["supportive"]["confirmatory_p_value"] is False
    stopping = manifest["transport_and_stopping"]
    assert stopping["availability_qualification"] == {
        "before_formal_marker": True,
        "logical_request_count": 1,
        "max_request_attempts_including_transport_retry": 2,
        "request": "Reply exactly with FORGE_READY.",
        "expected_response": "FORGE_READY",
        "experiment_content_included": False,
        "transport_retry_policy_applies": True,
        "failure_creates_batch": False,
        "request_attempts_count_toward_formal_arm_budget": False,
    }
    assert stopping["transport_retry_max_per_logical_request"] == 1
    assert stopping["stop_after_endpoint_censored_arm_count"] == 2


def test_authorization_and_release_revision_remain_closed() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    authorization = manifest["authorization"]

    assert authorization["candidate_identity_only"] is True
    assert all(value is False for key, value in authorization.items() if key != "candidate_identity_only")
    assert manifest["development_revision"]["release_revision"] is None
    assert manifest["candidate_evidence"]["formal_directory"] is None
    assert manifest["candidate_evidence"]["writes_authorized"] is False


def test_runtime_bindings_and_feedback_delta_are_frozen() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    frozen = manifest["frozen_components"]

    for path in (
        "scripts/forge_runtime_v3_three_arm_qualification.py",
        "backend/tests/test_forge_runtime_v3_three_arm_qualification_docker.py",
        "benchmarks/preregistrations/cpp-runtime-v3-three-arm-zero-provider-qualification.md",
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
        "backend/packages/harness/deerflow/compile/candidate_verifier.py",
        "scripts/forge_opaque_build_provenance_gate.py",
        "backend/packages/harness/deerflow/compile/external_evaluator_v3.py",
        "backend/packages/harness/deerflow/compile/operations.py",
        "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    ):
        assert len(frozen[path]) == 64
    assert manifest["feedback_contract"]["allowed_cross_arm_delta"] == "feedback projection only"
    assert manifest["checkpoint_contract"]["capture_timing"].endswith("before any continuation model request")


def test_runner_is_read_only_and_evaluator_identity_is_blinded() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    checkpoint = manifest["schedule"]["checkpoints"][0]
    arm_plan = checkpoint["arms"][0]

    assert runner.validate_candidate(manifest)["provider_calls"] == 0
    assert runner.plan(manifest)["arm_count"] == 36
    assert runner.show_checkpoint(manifest, checkpoint["checkpoint_id"])["checkpoint"] == checkpoint
    evaluator = runner.external_evaluator_identity(checkpoint, arm_plan)
    assert set(evaluator) == {"opaque_evaluation_id", "checkpoint_id", "task_id"}
    assert "condition" not in evaluator and "feedback_projection" not in evaluator
    for action in (runner.execute_reachability, runner.run_arm, runner.run_batch):
        with pytest.raises(runner.CandidateRunnerError, match="独立 authorized identity"):
            action()


def test_manifest_tamper_fails_closed() -> None:
    manifest = protocol.load_manifest(repo_root=REPO_ROOT)
    tampered = copy.deepcopy(manifest)
    tampered["authorization"]["provider_calls_authorized"] = True
    with pytest.raises(protocol.CandidateProtocolError, match="确定性生成结果"):
        protocol.validate_manifest(tampered, REPO_ROOT)

    tampered = copy.deepcopy(manifest)
    tampered["schedule"]["checkpoints"][0]["arm_order"].reverse()
    with pytest.raises(protocol.CandidateProtocolError, match="确定性生成结果"):
        protocol.validate_manifest(tampered, REPO_ROOT)
