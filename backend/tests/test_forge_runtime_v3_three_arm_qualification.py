from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from deerflow.compile.agent_workflow_runtime import AgentWorkflowEvidenceLedger
from deerflow.compile.agent_workflow_schemas import (
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    SubmitCandidateRequest,
)
from deerflow.compile.candidate_verifier import (
    CandidateVerifier,
    FunctionalCheckEvidence,
)
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.schemas import BuildCommandRecord, CompileSession, utc_now_iso

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_runtime_v3_three_arm_qualification.py"


def _load_adapter():
    spec = importlib.util.spec_from_file_location(
        "forge_runtime_v3_three_arm_qualification_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


qualification = _load_adapter()


class FakeManager:
    def __init__(self, session: CompileSession):
        self.session = session

    def load_session(self, session_id: str, thread_id: str | None = None) -> CompileSession:
        assert session_id == self.session.session_id
        assert thread_id == self.session.thread_id
        return self.session


class PassingFunctionalRunner:
    def run(self, *, spec: Any, session: Any, manager: Any) -> FunctionalCheckEvidence:
        del session, manager
        return FunctionalCheckEvidence(
            oracle_ref=spec.oracle_ref,
            passed=True,
            command_id="command-oracle",
            exit_code=0,
            timed_out=False,
            stdout_sha256=hashlib.sha256(b"ok").hexdigest(),
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
        )


def _budget() -> AgentWorkflowBudget:
    return AgentWorkflowBudget(
        max_model_requests=4,
        max_recorded_tokens=20_000,
        max_agent_steps=12,
        max_tool_calls=8,
        max_commands=4,
        node_timeout_seconds=300,
        command_timeout_seconds=120,
        evaluator_timeout_seconds=300,
        replay_timeout_seconds=600,
        cleanup_timeout_seconds=120,
    )


def _session(tmp_path: Path, *, opaque_provenance: bool = False) -> CompileSession:
    session_dir = tmp_path / "thread" / "session"
    artifacts = session_dir / "artifacts"
    artifact = artifacts / "bin" / "forge-fixture"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(Path("/bin/true").read_bytes())
    now = utc_now_iso()
    commands = [
        BuildCommandRecord(
            stage="bash",
            command="sh -c 'cmake -S . -B build && cmake --build build'",
            workdir="/workspace/repo",
            command_id="command-wrapper",
            role="build",
            completed_at=now,
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cp build/forge-fixture /artifacts/bin/forge-fixture",
            workdir="/workspace/repo",
            command_id="command-stage",
            role="artifact_stage",
            completed_at=now,
            exit_code=0,
        ),
    ]
    if not opaque_provenance:
        commands = [
            BuildCommandRecord(
                stage="bash",
                command="cmake -S . -B /workspace/repo/build -G Ninja",
                workdir="/workspace/repo",
                command_id="command-configure",
                role="configure",
                completed_at=now,
                exit_code=0,
            ),
            BuildCommandRecord(
                stage="bash",
                command="cmake --build /workspace/repo/build --target forge-fixture",
                workdir="/workspace/repo",
                command_id="command-build",
                role="build",
                completed_at=now,
                exit_code=0,
            ),
            commands[-1],
        ]
    return CompileSession(
        session_id="qualification-session",
        thread_id="qualification-thread",
        run_id="qualification-run",
        repo_url="https://example.invalid/fixture.git",
        branch="main",
        commit_sha="a" * 40,
        image="autocompiler:gcc13",
        image_id="sha256:" + "b" * 64,
        status="inspected",
        selected_build_system="cmake",
        build_system="cmake",
        leadagent_repo_dir=str(session_dir / "workspace" / "repo"),
        leadagent_artifacts_dir=str(artifacts),
        leadagent_logs_dir=str(session_dir / "logs"),
        leadagent_repro_dir=str(session_dir / "repro"),
        metadata_path=str(session_dir / "session.json"),
        commands=commands,
    )


def _node_input(session: CompileSession) -> AgentBuildNodeInput:
    return AgentBuildNodeInput(
        task_id="qualification-task",
        attempt_id="qualification-attempt",
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=session.commit_sha or "",
        source_snapshot_sha256="c" * 64,
        build_system_candidates=("cmake",),
        target_contract=AgentWorkflowTargetContract(
            target_id="forge-fixture",
            artifact_types=("executable",),
            artifact_path_patterns=("bin/forge-fixture",),
            functional_oracle_ref="oracle-qualification",
        ),
        operation_policy_ref="runtime-v3-qualification",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id or "",
            parallel_jobs=session.parallel_jobs,
            network_policy="compile-network-v1",
        ),
        budget=_budget(),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256="d" * 64,
            protocol_sha256="e" * 64,
            runner_sha256="f" * 64,
        ),
        initial_observation={
            "required_candidate_artifacts": ("bin/forge-fixture",),
            "zero_provider": True,
        },
    )


def _request(*, target_id: str = "forge-fixture", opaque_provenance: bool = False) -> SubmitCandidateRequest:
    supporting_command_id = "command-wrapper" if opaque_provenance else "command-build"
    recipe_command_ids = ("command-wrapper", "command-stage") if opaque_provenance else ("command-configure", "command-build", "command-stage")
    return SubmitCandidateRequest(
        candidate_id="candidate-qualification",
        build_system="cmake",
        supporting_command_ids=(supporting_command_id,),
        artifact_paths=("bin/forge-fixture",),
        target_mapping={target_id: "bin/forge-fixture"},
        recipe_command_ids=recipe_command_ids,
    )


def _verifier() -> CandidateVerifier:
    return CandidateVerifier(
        oracle_spec=FunctionalOracleSpec(
            oracle_ref="oracle-qualification",
            argv=("/artifacts/bin/forge-fixture",),
        ),
        functional_runner=PassingFunctionalRunner(),
    )


def _service(
    tmp_path: Path,
    *,
    provenance_evaluator=None,
):
    session = _session(
        tmp_path,
        opaque_provenance=provenance_evaluator is not None,
    )
    node_input = _node_input(session)
    state, tracker, store = qualification.create_store(node_input.budget)
    tracker.consume(tool_calls=1)
    ledger = AgentWorkflowEvidenceLedger(
        tmp_path / "events.jsonl",
        node_input=node_input,
        run_id=session.run_id or "",
    )
    service = qualification.create_candidate_service(
        verifier=_verifier(),
        provenance_evaluator=provenance_evaluator,
        node_input=node_input,
        session=session,
        manager=FakeManager(session),
        store=store,
        candidate_path=tmp_path / "candidate.json",
        ledger=ledger,
    )
    return service, state, tracker


def _common_state() -> dict[str, Any]:
    return {
        "source": {"repository": "fixture", "commit": "a" * 40},
        "parent_history_sha256": "b" * 64,
        "candidate_request_sha256": "c" * 64,
        "rejection_event_sha256": "d" * 64,
        "message_prefix_sha256": "e" * 64,
        "environment": {
            "image_id": "sha256:" + "f" * 64,
            "workspace_sha256": "1" * 64,
            "artifacts_sha256": "2" * 64,
        },
        "budget": {
            "model_requests": 0,
            "recorded_tokens": 0,
            "agent_steps": 0,
            "tool_calls": 1,
            "commands": 0,
        },
        "tool_policy": qualification.TOOL_POLICY,
        "authorities": qualification.component_hashes(),
    }


def test_runtime_v3_delivery_rejection_exposes_production_finding(
    tmp_path: Path,
) -> None:
    service, state, tracker = _service(tmp_path)

    response = service.submit(_request(target_id="wrong-target"))

    assert response.accepted is False
    assert response.rejection_codes == ("target_mapping_invalid",)
    assert response.rejection_details[0].as_payload() == {
        "code": "target_mapping_invalid",
        "paths": [],
        "total_count": 0,
        "truncated": False,
        "expected": ["forge-fixture"],
        "actual": ["wrong-target"],
    }
    assert state.status.value == "running"
    assert tracker.snapshot().model_requests == 0


def test_p2_adapter_replaces_only_coarse_mismatch_after_candidate_verifier(
    tmp_path: Path,
) -> None:
    calls = 0

    def p2(_request: SubmitCandidateRequest) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "status": "unproven",
            "reason": "opaque_wrapper",
            "paths": ["build/forge-fixture"],
            "expected": ["cmake"],
            "actual": ["opaque_wrapper"],
        }

    service, state, _tracker = _service(
        tmp_path,
        provenance_evaluator=p2,
    )

    response = service.submit(_request(opaque_provenance=True))

    assert response.accepted is False
    assert response.rejection_codes == ("build_system_unproven",)
    assert response.rejection_details == ()
    assert service.last_provenance_finding == {
        "code": "build_system_unproven",
        "paths": ["build/forge-fixture"],
        "expected": ["cmake"],
        "actual": ["opaque_wrapper"],
    }
    assert calls == 1
    assert state.status.value == "running"
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events].count("candidate.prefreeze_verification_completed") == 1
    assert [event["event_type"] for event in events].count("candidate.provenance_verification_completed") == 1


@pytest.mark.parametrize("stratum", qualification.STRATA)
def test_three_arm_projection_has_exact_whitelisted_diff(stratum: str) -> None:
    finding = qualification._synthetic_findings()[stratum]
    projections = qualification.build_projection_set(
        pair_id=f"pair-{stratum}",
        stratum=stratum,
        finding=finding,
    )

    assert set(projections["c0"].payload) == {
        "schema_version",
        "accepted",
        "reason",
    }
    assert set(projections["t1"].payload["feedback"]) == {
        "classification",
        "finding",
    }
    assert set(projections["t2"].payload["feedback"]) == {
        "classification",
        "finding",
        "repair_goal",
    }
    assert projections["t1"].payload["feedback"]["finding"] == projections["t2"].payload["feedback"]["finding"]


def _inject_forbidden_command(projections: dict[str, Any]) -> None:
    command = "cmake --build /workspace/repo/build"
    projections["t1"].payload["feedback"]["finding"]["actual"].append(command)
    projections["t2"].payload["feedback"]["finding"]["actual"].append(command)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["t1"].payload["feedback"].update(command_line="cmake --build build"),
            "feedback fields drifted",
        ),
        (
            lambda value: value.__setitem__(
                "t1",
                replace(value["t1"], pair_id="other-pair"),
            ),
            "cross-pair",
        ),
        (
            lambda value: value["t2"].payload["feedback"].update(repair_goal="Apply this patch"),
            "repair goal drifted",
        ),
        (
            _inject_forbidden_command,
            "forbidden content",
        ),
    ],
)
def test_feedback_drift_and_cross_pair_evidence_fail_closed(
    mutation,
    message: str,
) -> None:
    projections = qualification.build_projection_set(
        pair_id="pair-delivery",
        stratum="delivery_target",
        finding=qualification._synthetic_findings()["delivery_target"],
    )
    mutation(projections)

    with pytest.raises(qualification.QualificationError, match=message):
        qualification.validate_projection_set(
            projections,
            pair_id="pair-delivery",
            stratum="delivery_target",
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("environment", "common state drifted"),
        ("budget", "common state drifted"),
    ],
)
def test_state_and_budget_drift_fail_closed(field: str, message: str) -> None:
    pair_id = "pair-provenance"
    projections = qualification.build_projection_set(
        pair_id=pair_id,
        stratum="provenance",
        finding=qualification._synthetic_findings()["provenance"],
    )
    states = qualification.build_arm_states(
        common_state=_common_state(),
        projections=projections,
    )
    states["t2"]["common_state"][field]["drift"] = True

    with pytest.raises(qualification.QualificationError, match=message):
        qualification.validate_state_matched(
            states,
            pair_id=pair_id,
            stratum="provenance",
        )


def test_evaluator_label_leak_and_orphan_fail_closed() -> None:
    valid = qualification.StrictOutcome(
        candidate=True,
        functional_oracle=True,
        provenance=True,
        external_evaluator=True,
        clean_replay=True,
        cleanup=True,
        evaluator_input={"task_id": "qualification-task"},
    )
    qualification.validate_strict_outcome(valid)

    with pytest.raises(qualification.QualificationError, match="arm label"):
        qualification.validate_strict_outcome(replace(valid, evaluator_input={"condition": "treatment"}))
    with pytest.raises(qualification.QualificationError, match="orphans"):
        qualification.validate_strict_outcome(replace(valid, managed_orphans=("container-123",)))


def test_checkpoint_is_create_once_and_hash_validated(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    manifest = qualification.persist_checkpoint(path, {"capture_id": "capture-1"})

    assert qualification.validate_checkpoint(path) == manifest
    with pytest.raises(qualification.QualificationError, match="already exists"):
        qualification.persist_checkpoint(path, {"capture_id": "capture-1"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["capture_id"] = "drifted"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(qualification.QualificationError, match="hash drifted"):
        qualification.validate_checkpoint(path)


def test_cli_binds_current_components_and_zero_external_counts() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "validate"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["status"] == "contract_valid"
    assert result["arms"] == ["c0", "t1", "t2"]
    assert result["strata"] == ["delivery_target", "provenance"]
    assert result["component_sha256"] == qualification.component_hashes()
    assert result["tool_policy"]["parallel_tool_calls"] is False
    assert (
        result["provider_calls"],
        result["formal_attempts"],
        result["experiment_evidence_writes"],
    ) == (0, 0, 0)
    assert result["synthetic_model_counts"] == {
        "requests": 0,
        "turns": 0,
        "recorded_tokens": 0,
    }


def test_source_has_no_provider_credential_or_formal_evidence_path() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "create_chat_model",
        "deepseek_api_key",
        "openai_api_key",
        "activate_experiment",
        "experimentledger",
        "benchmarks/evidence",
    ):
        assert forbidden not in source
