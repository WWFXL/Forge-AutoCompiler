#!/usr/bin/env python3
"""执行 Workflow + Jev + Agent 混合链路 Provider canary v1。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(SCRIPT_ROOT), str(HARNESS_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_phase5_v2_authorized_runner as agent_provider  # noqa: E402
import forge_jev_end_to_end_canary_v7 as legacy  # noqa: E402
import forge_jev_offline_qualification_candidate as jev_candidate  # noqa: E402
import forge_jev_offline_qualification_v6 as jev_protocol  # noqa: E402

from deerflow.compile.agent_workflow_runtime import run_agent_workflow_node_v1  # noqa: E402
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    AgentWorkflowUsage,
)
from deerflow.compile.evidence import (  # noqa: E402
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
)
from deerflow.compile.hybrid_workflow import (  # noqa: E402
    HybridAgentHandoff,
    HybridStepOutcome,
    HybridWorkflowBudget,
    HybridWorkflowObservation,
    HybridWorkflowSnapshot,
    run_hybrid_workflow,
)
from deerflow.compile.jev_controller import CandidateAction, DecisionState  # noqa: E402
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    get_compile_services,
    prepare_compile_session_impl,
)

IDENTITY = "cpp-jev-hybrid-workflow-canary-v1"
BRANCH = "yiwei/409-jev-hybrid-workflow"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / f"{IDENTITY}.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks" / "preregistrations" / f"{IDENTITY}.md"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.json"
REPORT_MARKDOWN_PATH = REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.md"
EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions" / "benchmark-evidence-jev-hybrid-workflow-canary-v1"
QUALIFICATION_REPORT_PATH = REPO_ROOT / "benchmarks" / "reports" / "cpp-jev-hybrid-workflow-qualification-v3.json"
CREDENTIAL_FILE = REPO_ROOT / "jev-apikey.txt"


class CanaryError(RuntimeError):
    """Canary 身份、预算、evidence 或执行合同无效。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanaryError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CanaryError(f"JSON 根必须为对象: {path}")
    return value


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CanaryError(f"create-once 路径已存在: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _write_once_json(path: Path, value: Any) -> None:
    _write_once(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    path.chmod(0o600)


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={REPO_ROOT}", *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise CanaryError(result.stderr.strip() or "Git identity check failed")
    return result.stdout.strip()


def _manifest() -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    if manifest.get("identity") != IDENTITY or manifest.get("branch") != BRANCH:
        raise CanaryError("canary identity 漂移")
    if manifest.get("authorization") != {
        "backfill": False,
        "credential_reads": True,
        "docker_execution": True,
        "formal_attempts": 3,
        "formal_evidence_write": True,
        "historical_evidence_write": False,
        "provider_calls": True,
        "replacement": False,
    }:
        raise CanaryError("canary 授权边界漂移")
    if len(manifest.get("cases", [])) != 3 or manifest.get("evidence", {}).get("create_once") is not True:
        raise CanaryError("canary case 或 create-once 合同漂移")
    for relative_path, expected_sha256 in manifest["parents"].items():
        if legacy.file_sha256(REPO_ROOT / relative_path) != expected_sha256:
            raise CanaryError(f"父证据漂移: {relative_path}")
    for relative_path, expected_sha256 in manifest["components"].items():
        if legacy.file_sha256(REPO_ROOT / relative_path) != expected_sha256:
            raise CanaryError(f"实现组件漂移: {relative_path}")
    for case in manifest["cases"]:
        task = legacy._task(case["task_id"])
        if legacy._source_contract(task) != case["source"]:
            raise CanaryError(f"{case['task_id']} source contract 漂移")
    qualification = _load_json(QUALIFICATION_REPORT_PATH)
    if qualification.get("passed") is not True or qualification.get("decision") != "proceed_to_provider_canary_identity_freeze":
        raise CanaryError("零 Provider qualification 未通过")
    return manifest


def preflight(*, require_clean: bool = True, require_absent_evidence: bool = True) -> dict[str, Any]:
    manifest = _manifest()
    if _git("branch", "--show-current") != BRANCH:
        raise CanaryError("当前分支与 canary identity 不一致")
    if require_clean and _git("status", "--porcelain", "--untracked-files=normal"):
        raise CanaryError("Provider canary 要求干净工作树")
    head = _git("rev-parse", "HEAD")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", manifest["implementation_revision"], head],
        cwd=REPO_ROOT,
        check=False,
        timeout=30,
    )
    if ancestor.returncode != 0:
        raise CanaryError("HEAD 不是冻结 implementation revision 的后代")
    if f"origin/{BRANCH}" not in {line.strip() for line in _git("branch", "-r", "--contains", head).splitlines()}:
        raise CanaryError("Provider canary revision 尚未推送")
    workspace = legacy._configure_compile_workspace(manifest)
    if legacy._image_id() != manifest["environment"]["image_id"]:
        raise CanaryError("编译镜像漂移")
    if require_absent_evidence and (EVIDENCE_ROOT.exists() or REPORT_JSON_PATH.exists() or REPORT_MARKDOWN_PATH.exists()):
        raise CanaryError("Provider canary create-once 输出已存在")
    agent_provider.require_zero_managed_resources()
    jev_protocol.validate_egress()
    if not CREDENTIAL_FILE.is_file() or CREDENTIAL_FILE.stat().st_mode & 0o777 != 0o600:
        raise CanaryError("Jev credential 缺失或权限漂移")
    agent_credential_env = manifest["agent_provider"]["credential_env"]
    if not os.environ.get(agent_credential_env):
        raise CanaryError("Agent Provider credential 环境变量缺失")
    return {
        "ready": True,
        "identity": IDENTITY,
        "release_revision": head,
        "manifest_sha256": legacy.canonical_sha256(manifest),
        "image_id": manifest["environment"]["image_id"],
        "workspace": workspace,
        "evidence_exists": EVIDENCE_ROOT.exists(),
        "zero_managed_resources": True,
    }


def _experiment_policy(manifest: dict[str, Any], task: dict[str, Any], sequence: int) -> ExperimentPolicy:
    agent = manifest["agent_provider"]
    budget = manifest["budget"]["per_case_agent"]
    return ExperimentPolicy(
        benchmark_id=IDENTITY,
        manifest_sha256=legacy.canonical_sha256(manifest),
        case_id=f"{sequence:02d}-{task['task_id']}",
        condition="hybrid_workflow_canary",
        repetition=1,
        expected_repo_url=task["repository_url"],
        expected_commit_sha=task["commit_sha"],
        expected_build_system=task["selected_build_system"],
        compile_image=manifest["environment"]["compile_image"],
        image_id=manifest["environment"]["image_id"],
        model_name=agent["profile"],
        endpoint=agent["endpoint"],
        credential_env=agent["credential_env"],
        request_timeout_seconds=agent["request_timeout_seconds"],
        model_max_retries=agent["max_retries"],
        compiler_max_turns=budget["max_model_requests"],
        subagent_timeout_seconds=budget["node_timeout_seconds"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=budget["max_model_requests"],
        compiler_graph_recursion_limit=budget["max_agent_steps"],
        compiler_wall_clock_seconds=budget["node_timeout_seconds"],
        compiler_post_build_reserve_seconds=budget["cleanup_timeout_seconds"],
    )


def _node_input(
    manifest: dict[str, Any],
    task: dict[str, Any],
    case: dict[str, Any],
    session: Any,
    attempt_id: str,
    state: dict[str, Any],
    route_observation: dict[str, Any],
) -> AgentBuildNodeInput:
    _target_path, target_type = legacy._compiled_target(task)
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        source_snapshot_sha256=task["source_snapshot_sha256"],
        build_system_candidates=(task["selected_build_system"],),
        target_contract=AgentWorkflowTargetContract(
            target_id=f"{task['task_id']}-target",
            artifact_types=(target_type,),
            artifact_path_patterns=tuple(task["target"]["required_artifacts"]),
            functional_oracle_ref=legacy._oracle_ref(task),
        ),
        operation_policy_ref="compile-operation-policy-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=manifest["environment"]["image_id"],
            parallel_jobs=manifest["environment"]["parallel_jobs"],
            network_policy=manifest["environment"]["network_policy"],
        ),
        budget=AgentWorkflowBudget(**manifest["budget"]["per_case_agent"]),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=legacy.canonical_sha256(manifest),
            protocol_sha256=legacy.file_sha256(PREREGISTRATION_PATH),
            runner_sha256=manifest["components"]["scripts/forge_jev_hybrid_workflow_canary_v1.py"],
        ),
        initial_observation={
            "fault_type": case["fault_type"],
            "semantic_failure_log": state["semantic_failure_log"],
            "candidate_action_families": tuple(row["action_family"] for row in state["candidate_actions"]),
            "required_candidate_artifacts": tuple(task["target"]["required_artifacts"]),
            "functional_oracle": task["oracle"],
            "selected_build_system": task["selected_build_system"],
            "route_observation": route_observation,
        },
    )


def _request_fingerprint(state: dict[str, Any]) -> str:
    prompt = jev_protocol._prompt_contract(2)
    provider_state = jev_candidate.provider_state(state["model_input"])
    questions = jev_protocol._provider_questions(prompt)
    return jev_candidate.request_fingerprint(provider_state, questions)


class HybridCanaryCase:
    def __init__(
        self,
        *,
        manifest: dict[str, Any],
        case: dict[str, Any],
        sequence: int,
        session: Any,
        state: dict[str, Any],
        baseline_records: list[Any],
        detection: dict[str, Any],
    ):
        self.manifest = manifest
        self.case = case
        self.sequence = sequence
        self.session = session
        self.state = state
        self.task = legacy._task(case["task_id"])
        self.baseline_records = baseline_records
        self.detection = detection
        self.services = get_compile_services()
        self.fingerprint = _request_fingerprint(state)
        self.observation_id = 0
        self.jev_requests = 0
        self.jev_response: dict[str, Any] | None = None
        self.jev_error_class: str | None = None
        self.direct_attempted = False
        self.direct_action_succeeded = False
        self.agent_attempted = False
        self.agent_finished = False
        self.node_result: AgentBuildNodeResult | None = None
        self.evaluation = None
        self.route_trigger: str | None = None

    def _current(self) -> Any:
        return self.services.manager.load_session(self.session.session_id, self.session.thread_id)

    def _candidates(self) -> tuple[CandidateAction, ...]:
        candidates = legacy._candidate_actions(self.state)
        if self.case["force_agent_handoff"]:
            return tuple(replace(candidate, preconditions_satisfied=False) if candidate.direct_execution else candidate for candidate in candidates)
        return candidates

    def observer(self, _snapshot: HybridWorkflowSnapshot) -> HybridWorkflowObservation:
        self.observation_id += 1
        terminal_status = "pending"
        terminal_reason = None
        if self.evaluation is not None:
            if self.evaluation.strict_reproducible_build_success:
                terminal_status = "strict_success"
                terminal_reason = "s0_s5_strict_evaluator_passed"
            else:
                terminal_status = "terminal_failure"
                terminal_reason = "s0_s5_strict_evaluator_failed"
        elif self.agent_attempted and self.agent_finished:
            terminal_status = "terminal_failure"
            terminal_reason = "agent_returned_without_strict_evaluation"
        return HybridWorkflowObservation(
            observation_id=self.observation_id,
            decision_state=DecisionState(
                state_id=self.state["state_id"],
                build_system=self.state["build_system"],
                phase_facts=self.state["phase_facts"],
                remaining_actions=0,
                remaining_wall_clock_seconds=0,
                expected_request_fingerprint=self.fingerprint,
            ),
            candidates=self._candidates(),
            verifier_capabilities=legacy.VERIFIER_CAPABILITIES,
            terminal_status=terminal_status,
            terminal_reason=terminal_reason,
        )

    def decision_provider(self, _observation: HybridWorkflowObservation) -> Any:
        self.jev_requests += 1
        try:
            decision, response = legacy.request_jev(self.state)
        except Exception as exc:
            self.jev_error_class = type(exc).__name__
            raise
        self.jev_response = response
        return decision

    def _route_observation(self, *, trigger: str | None = None) -> dict[str, Any]:
        return {
            "controller": "hybrid_workflow_canary",
            "build_system_detection": self.detection,
            "state_id": self.state["state_id"],
            "request_fingerprint": self.fingerprint,
            "force_agent_handoff": self.case["force_agent_handoff"],
            "trigger": trigger,
        }

    def direct_executor(self, candidate: CandidateAction) -> HybridStepOutcome:
        self.direct_attempted = True
        action_succeeded, action_records, _message = legacy._run_bound_commands(
            self.session,
            legacy._commands(self.task, self.case["fault_type"], candidate.action_family),
            candidate.action_family,
            require_success=False,
        )
        build_records = action_records if candidate.action_family == "build" else []
        if action_succeeded and candidate.action_family != "build":
            action_succeeded, build_records, _message = legacy._run_bound_commands(
                self.session,
                list(self.task["build_commands"]),
                "build",
                require_success=False,
            )
        stage_records: list[Any] = []
        if action_succeeded:
            action_succeeded, stage_records, _message = legacy._run_bound_commands(
                self.session,
                list(self.task["artifact_stage_commands"]),
                "artifact_stage",
                require_success=False,
            )
        self.direct_action_succeeded = action_succeeded
        if not action_succeeded or not build_records:
            return HybridStepOutcome(False, "bound_direct_action_failed")

        attempt_id = f"hybrid-canary-{self.sequence:02d}-direct"
        node_input = _node_input(
            self.manifest,
            self.task,
            self.case,
            self.session,
            attempt_id,
            self.state,
            self._route_observation(),
        )
        recipe_records = [*self.baseline_records, *action_records]
        if candidate.action_family != "build":
            recipe_records.extend(build_records)
        recipe_records.extend(stage_records)
        self.node_result, candidate_path = legacy._direct_candidate(
            node_input=node_input,
            session=self.session,
            manager=self.services.manager,
            sequence=self.sequence,
            arm="hybrid",
            recipe_records=recipe_records,
            supporting_record=build_records[-1],
        )
        self.evaluation = legacy._evaluate(
            node_input=node_input,
            node_result=self.node_result,
            session=self.session,
            candidate_path=candidate_path,
            evaluation_id=f"hybrid-canary-eval-{self.sequence:02d}-direct",
        )
        strict = self.evaluation.strict_reproducible_build_success
        return HybridStepOutcome(strict, "strict_direct_evaluation_passed" if strict else "strict_direct_evaluation_failed", reported_terminal_success=strict)

    async def agent_runner(self, handoff: HybridAgentHandoff) -> HybridStepOutcome:
        self.agent_attempted = True
        self.route_trigger = handoff.trigger
        attempt_id = f"hybrid-canary-{self.sequence:02d}-agent"
        node_input = _node_input(
            self.manifest,
            self.task,
            self.case,
            self.session,
            attempt_id,
            self.state,
            self._route_observation(trigger=handoff.trigger),
        )
        try:
            model = legacy._agent_model(self.session.thread_id)
            self.node_result = await run_agent_workflow_node_v1(
                node_input=node_input,
                session=self.session,
                manager=self.services.manager,
                model=model,
            )
            if self.node_result.candidate_submitted:
                candidate_path = Path(self.session.metadata_path).parent / "agent-workflow" / attempt_id / "candidate.json"
                self.evaluation = legacy._evaluate(
                    node_input=node_input,
                    node_result=self.node_result,
                    session=self.session,
                    candidate_path=candidate_path,
                    evaluation_id=f"hybrid-canary-eval-{self.sequence:02d}-agent",
                )
        finally:
            self.agent_finished = True
        strict = bool(self.evaluation is not None and self.evaluation.strict_reproducible_build_success)
        return HybridStepOutcome(strict, "strict_agent_evaluation_passed" if strict else "agent_returned_without_strict_success", reported_terminal_success=strict)


def _usage(node_result: AgentBuildNodeResult | None) -> AgentWorkflowUsage:
    return node_result.usage if node_result is not None else AgentWorkflowUsage(0, 0, 0, 0, 0)


async def execute_case(manifest: dict[str, Any], case: dict[str, Any], sequence: int, release_revision: str) -> dict[str, Any]:
    task = legacy._task(case["task_id"])
    digest = legacy.canonical_sha256(manifest)
    case_dir = EVIDENCE_ROOT / "cases" / f"{sequence:02d}-{task['task_id']}"
    marker_path = case_dir / "attempt.json"
    result_path = case_dir / "result.json"
    _write_once_json(
        marker_path,
        {
            "identity": IDENTITY,
            "manifest_sha256": digest,
            "release_revision": release_revision,
            "sequence": sequence,
            "task_id": task["task_id"],
            "status": "started",
            "updated_at": _now(),
        },
    )
    ledger = ExperimentLedger.create(
        case_dir / "experiment.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={"identity": IDENTITY, "manifest_sha256": digest, "sequence": sequence, "task_id": task["task_id"]},
    )
    thread_id = f"jev-hybrid-canary-{sequence:02d}-{task['task_id']}-{digest[:10]}"
    session = None
    harness: HybridCanaryCase | None = None
    hybrid_result = None
    cleanup_succeeded = False
    finalized = None
    cleanup = None
    error_class: str | None = None
    active = False
    started = time.perf_counter()
    try:
        activate_experiment(
            thread_id=thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_experiment_policy(manifest, task, sequence),
        )
        active = True
        session = prepare_compile_session_impl(
            thread_id=thread_id,
            repo_url=task["repository_url"],
            run_id=f"jev-hybrid-canary-{uuid.uuid4().hex}",
            task_description=f"Jev hybrid workflow Provider canary: {task['task_id']}",
        )
        clone, _message = clone_repository_impl(
            session=session,
            repo_url=task["repository_url"],
            commit_sha=task["commit_sha"],
            depth=1,
            max_retries=1,
        )
        if clone.exit_code != 0 or session.commit_sha != task["commit_sha"]:
            raise CanaryError(f"{task['task_id']} exact commit checkout 失败")
        primary, detected, selected = legacy._select_experiment_build_system(session, task)
        detection = {"primary": primary, "detected": detected, "selected": selected}
        _configured, baseline_records, _message = legacy._run_bound_commands(
            session,
            list(task["configure_commands"]),
            "configure",
            require_success=True,
        )
        state, failure_record = legacy._inject_fault(session, task, case["fault_type"], ledger)
        detection["failure_command_id"] = failure_record.command_id
        harness = HybridCanaryCase(
            manifest=manifest,
            case=case,
            sequence=sequence,
            session=session,
            state=state,
            baseline_records=baseline_records,
            detection=detection,
        )
        hybrid_result = await run_hybrid_workflow(
            budget=HybridWorkflowBudget(**manifest["budget"]["hybrid_workflow"]),
            calibration=legacy.CALIBRATION,
            observer=harness.observer,
            decision_provider=harness.decision_provider,
            direct_executor=harness.direct_executor,
            agent_runner=harness.agent_runner,
        )
        finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
        agent_provider.require_zero_managed_resources()
        cleanup_succeeded = cleanup.succeeded and finalized.finalized_at is not None
    except BaseException as exc:
        error_class = type(exc).__name__
        if session is not None and not cleanup_succeeded:
            try:
                finalized, cleanup = cleanup_and_finalize_compile_session_impl(
                    session=session,
                    interrupted_status="failed",
                    error="Hybrid Provider canary failed.",
                )
                agent_provider.require_zero_managed_resources()
                cleanup_succeeded = cleanup.succeeded and finalized.finalized_at is not None
            except Exception as cleanup_exc:
                error_class = f"{error_class}+{type(cleanup_exc).__name__}"
    finally:
        if active:
            deactivate_experiment(thread_id)

    usage = _usage(harness.node_result if harness is not None else None)
    jev_response = harness.jev_response if harness is not None else None
    normalized_response = jev_response["response"] if jev_response is not None else None
    strict_success = bool(hybrid_result is not None and hybrid_result.status == "strict_success")
    result = {
        "schema_version": "forge-jev-hybrid-workflow-canary-case-1.0.0",
        "identity": IDENTITY,
        "manifest_sha256": digest,
        "release_revision": release_revision,
        "sequence": sequence,
        "task_id": task["task_id"],
        "build_system": task["selected_build_system"],
        "fault_type": case["fault_type"],
        "force_agent_handoff": case["force_agent_handoff"],
        "hybrid_result": asdict(hybrid_result) if hybrid_result is not None else None,
        "route_trigger": harness.route_trigger if harness is not None else None,
        "direct_attempted": harness.direct_attempted if harness is not None else False,
        "direct_action_succeeded": harness.direct_action_succeeded if harness is not None else False,
        "agent_handoff_observed": bool(hybrid_result is not None and hybrid_result.agent_handoffs > 0),
        "agent_usage": asdict(usage),
        "jev_usage": {
            "model_requests": harness.jev_requests if harness is not None else 0,
            "input_tokens": normalized_response["usage"]["input_tokens"] if normalized_response is not None else None,
            "output_tokens": normalized_response["usage"]["output_tokens"] if normalized_response is not None else None,
            "cost_usd": normalized_response["cost_usd"] if normalized_response is not None else None,
            "error_class": harness.jev_error_class if harness is not None else None,
            "response_observed": normalized_response is not None,
        },
        "jev_response": normalized_response,
        "node_status": harness.node_result.node_status if harness is not None and harness.node_result is not None else None,
        "candidate_submitted": harness.node_result.candidate_submitted if harness is not None and harness.node_result is not None else False,
        "s0_s5": [asdict(layer) for layer in harness.evaluation.layers] if harness is not None and harness.evaluation is not None else [],
        "strict_reproducible_build_success": strict_success,
        "session_status": finalized.status if finalized is not None else getattr(session, "status", None),
        "cleanup_succeeded": cleanup_succeeded,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "error_class": error_class,
        "terminal_classification": "arm_error" if error_class is not None else "strict_success" if strict_success else "strict_failure" if hybrid_result is not None else "no_result",
    }
    _write_once_json(result_path, result)
    marker = _load_json(marker_path)
    marker.update({"status": "completed", "error_class": error_class, "updated_at": _now(), "result_sha256": legacy.file_sha256(result_path)})
    _atomic_json(marker_path, marker)
    return result


def _totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "agent_requests": sum(row["agent_usage"]["model_requests"] for row in rows),
        "agent_recorded_tokens": sum(row["agent_usage"]["recorded_tokens"] for row in rows),
        "jev_requests": sum(row["jev_usage"]["model_requests"] for row in rows),
        "jev_input_tokens": sum(row["jev_usage"]["input_tokens"] or 0 for row in rows),
        "jev_cost_usd": sum(row["jev_usage"]["cost_usd"] or 0 for row in rows),
    }


def _within_budget(manifest: dict[str, Any], totals: dict[str, Any]) -> bool:
    budget = manifest["budget"]
    return (
        totals["agent_requests"] <= budget["total_agent_request_ceiling"]
        and totals["agent_recorded_tokens"] <= budget["total_agent_token_ceiling"]
        and totals["jev_requests"] <= budget["total_jev_request_ceiling"]
        and totals["jev_input_tokens"] <= budget["total_jev_input_token_ceiling"]
        and totals["jev_cost_usd"] <= budget["total_jev_cost_ceiling_usd"] + 1e-12
    )


async def execute_batch() -> dict[str, Any]:
    ready = preflight()
    manifest = _manifest()
    batch_path = EVIDENCE_ROOT / "batch.json"
    _write_once_json(
        batch_path,
        {
            "identity": IDENTITY,
            "manifest_sha256": ready["manifest_sha256"],
            "release_revision": ready["release_revision"],
            "status": "running",
            "completed_cases": 0,
            "updated_at": _now(),
        },
    )
    rows: list[dict[str, Any]] = []
    try:
        for sequence, case in enumerate(manifest["cases"], start=1):
            rows.append(await execute_case(manifest, case, sequence, ready["release_revision"]))
            totals = _totals(rows)
            if not _within_budget(manifest, totals):
                raise CanaryError("Provider canary 总预算越界")
            batch = _load_json(batch_path)
            batch.update({"completed_cases": len(rows), "totals": totals, "updated_at": _now()})
            _atomic_json(batch_path, batch)
        batch = _load_json(batch_path)
        batch.update({"status": "completed", "updated_at": _now()})
        _atomic_json(batch_path, batch)
        return batch
    except BaseException as exc:
        batch = _load_json(batch_path)
        batch.update(
            {
                "status": "failed",
                "completed_cases": len(rows),
                "totals": _totals(rows),
                "error_class": type(exc).__name__,
                "updated_at": _now(),
            }
        )
        _atomic_json(batch_path, batch)
        raise


def _inventory() -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(EVIDENCE_ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": legacy.file_sha256(path),
        }
        for path in sorted(EVIDENCE_ROOT.rglob("*"))
        if path.is_file()
    ]


def generate_report() -> dict[str, Any]:
    manifest = _manifest()
    batch = _load_json(EVIDENCE_ROOT / "batch.json")
    rows = []
    for sequence, case in enumerate(manifest["cases"], start=1):
        result_path = EVIDENCE_ROOT / "cases" / f"{sequence:02d}-{case['task_id']}" / "result.json"
        if result_path.is_file():
            rows.append(_load_json(result_path))
    totals = _totals(rows)
    agent_provider.require_zero_managed_resources()
    gates = {
        "batch_completed": batch.get("status") == "completed",
        "three_cases_classified": len(rows) == 3 and all(row["terminal_classification"] for row in rows),
        "three_jev_responses": len(rows) == 3 and all(row["jev_usage"]["response_observed"] is True for row in rows),
        "agent_handoff_observed": any(row["agent_handoff_observed"] for row in rows),
        "agent_control_return_observed": any(row["agent_handoff_observed"] and row["hybrid_result"] is not None and row["hybrid_result"]["observations"] >= 2 for row in rows),
        "all_strict_success": len(rows) == 3 and all(row["strict_reproducible_build_success"] for row in rows),
        "all_cleanup_succeeded": len(rows) == 3 and all(row["cleanup_succeeded"] for row in rows),
        "within_frozen_budget": _within_budget(manifest, totals),
        "zero_managed_resources": True,
        "parent_evidence_unchanged": True,
    }
    passed = all(gates.values())
    report = {
        "schema_version": "forge-jev-hybrid-workflow-canary-report-1.0.0",
        "identity": IDENTITY,
        "manifest_sha256": legacy.canonical_sha256(manifest),
        "release_revision": batch.get("release_revision"),
        "created_at": _now(),
        "rows": rows,
        "totals": totals,
        "routing": {
            "direct_attempts": sum(row["direct_attempted"] for row in rows),
            "agent_handoffs": sum(row["agent_handoff_observed"] for row in rows),
        },
        "gates": gates,
        "passed": passed,
        "decision": "proceed_to_natural_failure_evaluation_design" if passed else "stop_and_repair_hybrid_workflow",
        "interpretation": manifest["interpretation"],
        "evidence_inventory": _inventory(),
    }
    _write_once_json(REPORT_JSON_PATH, report)
    _write_once(
        REPORT_MARKDOWN_PATH,
        "# Workflow + Jev + Agent 混合链路 Provider canary v1\n\n"
        f"- 决定：`{report['decision']}`\n"
        f"- 严格成功：`{sum(row['strict_reproducible_build_success'] for row in rows)}/3`\n"
        f"- Jev 请求 / input tokens / 费用：`{totals['jev_requests']} / {totals['jev_input_tokens']} / ${totals['jev_cost_usd']:.8f}`\n"
        f"- Agent handoff / 请求 / tokens：`{report['routing']['agent_handoffs']} / {totals['agent_requests']} / {totals['agent_recorded_tokens']}`\n"
        f"- cleanup 后受管资源：`0`\n\n"
        "该 canary 只验证真实 Provider 接线、控制权交还、预算、严格终点和 cleanup。"
        "三个项目均来自既往资格数据，且 Make case 人为禁用直接执行以保证 Agent handoff；"
        "因此不能据此主张自然失败成功率、成本收益、模型排名、未见项目泛化或动态预算优势。\n",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "execute", "report"))
    arguments = parser.parse_args()
    try:
        if arguments.command == "preflight":
            result = preflight(require_clean=False, require_absent_evidence=False)
        elif arguments.command == "execute":
            result = asyncio.run(execute_batch())
        else:
            result = generate_report()
    except CanaryError as exc:
        print(f"canary error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
