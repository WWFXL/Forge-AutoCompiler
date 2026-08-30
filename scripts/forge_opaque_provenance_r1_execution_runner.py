#!/usr/bin/env python3
"""执行 Issue #200 授权的 R1 reachability 与 yyjson 单 pair。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import MethodType
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_provenance_minimal_canary_execution_runner as legacy  # noqa: E402
import forge_opaque_provenance_r1_checkpoint_gate as checkpoint_gate  # noqa: E402
import forge_opaque_provenance_r1_execution_protocol as protocol  # noqa: E402
import forge_opaque_provenance_rejection_observability_gate as observability  # noqa: E402
import forge_opaque_provenance_runtime_parity_gate as parity  # noqa: E402

primary = legacy.primary
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-r1-yyjson-v1")
ARMS = ("baseline", "treatment")


class ExecutionGateError(RuntimeError):
    """R1 execution identity、R0 evidence、预算或 cleanup 无效。"""


def _output_dir(manifest: dict[str, Any], output_dir: Path) -> Path:
    expected = Path(manifest["evidence"]["directory"]).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise ExecutionGateError("evidence 必须写入 #196 冻结的 R1 目录")
    return output_dir


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _output_dir(manifest, output_dir)
    release = legacy._release_identity(manifest, repo_root)
    medium = legacy._network_medium(manifest)
    primary.require_compose_dood()
    try:
        legacy.v3_runner.require_zero_managed_containers()
    except legacy.v3_runner.AuthorizedPilotError as exc:
        raise ExecutionGateError(str(exc)) from exc
    legacy._provider_preflight(manifest)
    entries = sorted(str(path.relative_to(output_dir)).replace("\\", "/") for path in output_dir.rglob("*") if path.is_file()) if output_dir.exists() else []
    if require_empty and entries:
        raise ExecutionGateError("reachability 前要求 R1 evidence 目录为空")
    return {
        "ready": True,
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release["revision"],
        "network_access_medium": medium,
        "evidence_files": entries,
        "zero_managed_containers": True,
        "docker_provider": manifest["preflight"]["docker_provider"],
        "docker_endpoint": manifest["preflight"]["docker_endpoint"],
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def _policy(manifest: dict[str, Any], *, arm: str, image_id: str) -> Any:
    case = manifest["case"]
    provider = manifest["provider"]
    continuation = manifest["continuation"]
    return primary.ExperimentPolicy(
        benchmark_id="forge-opaque-provenance-r1-yyjson",
        manifest_sha256=protocol.canonical_sha256(manifest),
        case_id=case["case_id"],
        condition=arm,
        repetition=1,
        expected_repo_url=case["repository_url"],
        expected_commit_sha=case["commit_sha"],
        expected_build_system=case["build_system"],
        compile_image=case["compile_image"],
        image_id=image_id,
        model_name=provider["model"],
        endpoint=provider["endpoint"],
        credential_env=provider["credential_env"],
        request_timeout_seconds=provider["request_timeout_seconds"],
        model_max_retries=provider["max_retries"],
        compiler_max_turns=continuation["maximum_model_turns_per_arm"],
        subagent_timeout_seconds=continuation["work_wall_clock_seconds_per_arm"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=continuation["maximum_model_turns_per_arm"],
        compiler_graph_recursion_limit=continuation["maximum_graph_steps_per_arm"],
        compiler_wall_clock_seconds=continuation["work_wall_clock_seconds_per_arm"],
        compiler_post_build_reserve_seconds=continuation["cleanup_reserve_seconds_per_arm"],
        source_subdir=case["source_subdir"],
        build_targets=(case["target"],),
        artifact_instructions=(
            (
                case["staged_artifact"],
                case["build_output"],
                case["artifact_type"],
            ),
        ),
    )


def _r0_summary(ledger: Any) -> dict[str, Any]:
    events = ledger.read()
    failures = [event for event in events if event["event"] == "agent.tool_failed" and event["payload"].get("exception_class") == "ObservableRuntimeParityGateError"]
    observations = [event for event in events if event["event"] == observability.OBSERVATION_EVENT]
    failure_ids = {event["payload"]["failure_id"] for event in failures}
    observed_ids = {event["payload"]["failure_id"] for event in observations}
    if failure_ids != observed_ids:
        raise ExecutionGateError("classified runtime-parity rejection 缺少唯一 R0 companion evidence")
    if len(observed_ids) != len(observations):
        raise ExecutionGateError("R0 companion evidence 重复关联同一 failure")
    return {
        "classified_rejections": len(failures),
        "companion_events": len(observations),
        "companion_complete": failure_ids == observed_ids,
        "rejection_classifications": sorted({event["payload"]["rejection_classification"] for event in observations}),
        "raw_command_persisted": False,
    }


def _r0_summary_from_path(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "classified_rejections": 0,
            "companion_events": 0,
            "companion_complete": True,
            "rejection_classifications": [],
            "raw_command_persisted": False,
        }
    return _r0_summary(primary.ExperimentLedger.open(path))


def _install_model_origin_observer(middlewares: list[Any], registry: Any) -> tuple[Any, Any]:
    from deerflow.agents.middlewares.llm_error_handling_middleware import (
        LLMErrorHandlingMiddleware,
    )

    middleware = next(
        (item for item in middlewares if isinstance(item, LLMErrorHandlingMiddleware)),
        None,
    )
    if middleware is None:
        raise ExecutionGateError("continuation 缺少 LLM evidence middleware")
    original = middleware._request_completed

    def observed(
        self: Any,
        thread_id: str | None,
        response: Any,
        *,
        model_call_id: str,
        model_request_id: str,
        attempt: int,
        latency_seconds: float,
    ) -> None:
        original(
            thread_id,
            response,
            model_call_id=model_call_id,
            model_request_id=model_request_id,
            attempt=attempt,
            latency_seconds=latency_seconds,
        )
        registry.register_model_tool_calls(
            thread_id,
            response,
            model_request_id=model_request_id,
        )

    middleware._request_completed = MethodType(observed, middleware)
    return middleware, original


async def run_arm_continuation(
    manifest: dict[str, Any],
    *,
    arm: str,
    lifecycle_arm: Any,
    message_state: dict[str, Any],
    ledger: Any,
    model_factory: Any | None = None,
    budget_sink: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    from langchain.agents import create_agent
    from langchain_core.tools import tool
    from langgraph.checkpoint.memory import InMemorySaver

    from deerflow.agents.middlewares import tool_error_handling_middleware
    from deerflow.agents.middlewares.tool_error_handling_middleware import (
        build_subagent_runtime_middlewares,
    )
    from deerflow.agents.thread_state import ThreadState
    from deerflow.compile.operations import get_compile_services
    from deerflow.subagents.builtins.compiler_agent import COMPILER_AGENT_CONFIG
    from deerflow.tools.bound_compile_tools import get_bound_compile_tools

    if arm not in ARMS:
        raise ExecutionGateError("unknown checkpoint arm")
    session = lifecycle_arm.session
    policy = _policy(manifest, arm=arm, image_id=session.image_id)
    attempt_budget = primary.ExperimentAttemptBudget(
        total_wall_clock_seconds=720,
        cleanup_reserve_seconds=120,
        max_compiler_invocations=1,
        max_model_requests=manifest["continuation"]["maximum_requests_per_arm"],
    )
    primary.activate_experiment(
        thread_id=session.thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
        attempt_budget=attempt_budget,
    )
    adapter: Any | None = None
    original_failure_recorder = tool_error_handling_middleware.record_agent_tool_failure
    observed_middleware: Any | None = None
    original_request_completed: Any | None = None
    registry = observability.RejectionObservationRegistry()
    try:
        model = model_factory(manifest["provider"], session.thread_id) if model_factory is not None else primary._create_provider_model(manifest["provider"], experiment_thread_id=session.thread_id)
        tools = get_bound_compile_tools(session)
        run_tool = next(item for item in tools if item.name == "run_container_bash")
        submit_tool = next(item for item in tools if item.name == "submit_build_result")
        action_policy = parity.FrozenActionPolicy(
            workdir=checkpoint_gate.WORKDIR,
            build_directory=checkpoint_gate.BUILD_DIRECTORY,
            target=checkpoint_gate.TARGET,
            build_output=(f"{checkpoint_gate.WORKDIR}/{checkpoint_gate.BUILD_OUTPUT}"),
            staged_artifact=f"/artifacts/{checkpoint_gate.STAGED_ARTIFACT}",
        )
        adapter = observability.ObservableRuntimeParityToolAdapter(
            run_tool=run_tool,
            submit_tool=submit_tool,
            policy=action_policy,
            staged_artifacts_present=lambda: any(path.is_file() and not path.is_symlink() for path in Path(session.leadagent_artifacts_dir).rglob("*")),
        )

        @tool("run_container_bash", parse_docstring=True)
        def observable_run_container_bash(
            command: str,
            timeout_seconds: int = 300,
            workdir: str | None = None,
            command_role: str = "other",
        ) -> str:
            """在当前 R1 arm 中执行 runtime-parity 白名单动作。

            Args:
                command: 要执行的单一 bash 命令。
                timeout_seconds: 单条命令超时，最多 300 秒。
                workdir: 容器内工作目录。
                command_role: evidence 命令角色。
            """
            return adapter.run(
                command,
                timeout_seconds=timeout_seconds,
                workdir=workdir,
                command_role=command_role,
            )

        @tool("submit_build_result", parse_docstring=True)
        def observable_submit_build_result(
            supporting_command_id: str | None = None,
        ) -> str:
            """提交当前 R1 arm 的 staged artifact。

            Args:
                supporting_command_id: 可选的成功构建命令 ID。
            """
            return adapter.submit(supporting_command_id)

        middlewares = [
            parity.SerialToolCallMiddleware(),
            *build_subagent_runtime_middlewares(lazy_init=True),
        ]
        observed_middleware, original_request_completed = _install_model_origin_observer(middlewares, registry)

        def observed_failure(request: Any, exc: Exception, *, execution_mode: str) -> dict[str, Any] | None:
            failure, _observation = registry.record_tool_failure(
                request,
                exc,
                execution_mode=execution_mode,
            )
            return failure

        tool_error_handling_middleware.record_agent_tool_failure = observed_failure
        agent = create_agent(
            model=model,
            tools=[observable_run_container_bash, observable_submit_build_result],
            middleware=middlewares,
            system_prompt=COMPILER_AGENT_CONFIG.system_prompt,
            state_schema=ThreadState,
            checkpointer=InMemorySaver(),
        )
        state = {
            "messages": message_state["messages"],
            "artifacts": [],
            "viewed_images": {},
        }
        config = {
            "configurable": {"thread_id": session.thread_id},
            "recursion_limit": manifest["continuation"]["maximum_graph_steps_per_arm"],
        }
        await asyncio.wait_for(
            agent.ainvoke(
                state,
                config=config,
                context={"thread_id": session.thread_id, "agent_name": "compiler"},
            ),
            timeout=manifest["continuation"]["work_wall_clock_seconds_per_arm"],
        )
        primary.record_experiment_attempt_budget_completion(session.thread_id)
    finally:
        tool_error_handling_middleware.record_agent_tool_failure = original_failure_recorder
        if observed_middleware is not None and original_request_completed is not None:
            observed_middleware._request_completed = original_request_completed
        if adapter is not None:
            budget_sink[arm] = adapter.budget.snapshot()
        primary.deactivate_experiment(session.thread_id)

    authoritative = get_compile_services().manager.load_session(session.session_id, session.thread_id)
    result = primary.validate_arm_evidence(
        manifest,
        arm=arm,
        ledger=ledger,
        session=authoritative,
    )
    result["runtime_parity_action_budget"] = budget_sink[arm]
    result["r0_rejection_observability"] = _r0_summary(ledger)
    ledger.append("experiment.completed", {"status": "passed"})
    return result


def _with_execution_hooks(manifest: dict[str, Any], output_dir: Path, operation: Any) -> Any:
    from deerflow.compile import operations
    from deerflow.tools import bound_compile_tools

    original_protocol = legacy.protocol
    original_collect = legacy.collect_preflight
    original_opaque = legacy.opaque
    original_policy = legacy._policy
    original_continuation = primary.run_arm_continuation
    original_submit_impl = operations.submit_build_result_impl
    original_write_once = legacy.v3_runner._write_once
    action_budgets: dict[str, dict[str, Any]] = {}
    report_path = output_dir / manifest["evidence"]["canary_report"]

    def parent_submit_through_bound_wrapper(*, session: Any, supporting_command_id: str | None = None) -> str:
        return bound_compile_tools._submit_with_post_build_phase(
            session,
            supporting_command_id=supporting_command_id,
        )

    async def continuation(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return await run_arm_continuation(
            *args,
            **kwargs,
            budget_sink=action_budgets,
        )

    def write_once(path: Path, value: Any) -> None:
        if path.resolve(strict=False) == report_path.resolve(strict=False):
            arm_root = output_dir / manifest["execution"]["arm_ledger_directory"]
            r0_by_arm = {arm: _r0_summary_from_path(arm_root / f"{arm}.jsonl") for arm in ARMS}
            value = {
                **value,
                "schema_version": manifest["execution"]["report_schema_version"],
                "document_type": manifest["execution"]["report_document_type"],
                "runtime_parity": manifest["runtime_parity"],
                "runtime_parity_action_budgets": action_budgets,
                "r0_rejection_observability": r0_by_arm,
                "historical_pairs_pooled": False,
            }
        original_write_once(path, value)

    legacy.protocol = protocol
    legacy.collect_preflight = collect_preflight
    legacy.opaque = checkpoint_gate
    legacy._policy = _policy
    primary.run_arm_continuation = continuation
    operations.submit_build_result_impl = parent_submit_through_bound_wrapper
    legacy.v3_runner._write_once = write_once
    try:
        return operation()
    finally:
        legacy.protocol = original_protocol
        legacy.collect_preflight = original_collect
        legacy.opaque = original_opaque
        legacy._policy = original_policy
        primary.run_arm_continuation = original_continuation
        operations.submit_build_result_impl = original_submit_impl
        legacy.v3_runner._write_once = original_write_once


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    return _with_execution_hooks(
        manifest,
        output_dir,
        lambda: legacy.execute_reachability(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            model_factory=model_factory,
        ),
    )


def execute_pair(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    _with_execution_hooks(
        manifest,
        output_dir,
        lambda: legacy.execute_pair(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            model_factory=model_factory,
        ),
    )
    return legacy.v3_runner._load_json(output_dir / manifest["evidence"]["canary_report"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "preflight", "reachability", "pair"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        protocol.verify_frozen_components(manifest)
        result: Any = {
            "status": "valid",
            "manifest_sha256": protocol.canonical_sha256(manifest),
            "provider_calls": 0,
            "formal_attempts": 0,
            "model_tokens": 0,
        }
    elif args.command == "preflight":
        result = collect_preflight(
            manifest,
            output_dir=args.output_dir,
            require_empty=True,
        )
    elif args.command == "reachability":
        result = execute_reachability(manifest, output_dir=args.output_dir)
    else:
        result = execute_pair(manifest, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
