#!/usr/bin/env python3
"""执行 Issue #190 授权的 reachability 与 runtime-parity 单 pair。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_provenance_minimal_canary_execution_runner as legacy  # noqa: E402
import forge_opaque_provenance_runtime_parity_execution_protocol as protocol  # noqa: E402
import forge_opaque_provenance_runtime_parity_gate as parity  # noqa: E402

primary = legacy.primary
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-runtime-parity-amendment-v1")
ARMS = ("baseline", "treatment")


class ExecutionGateError(RuntimeError):
    """Execution identity、runtime-parity、evidence 或 cleanup 无效。"""


def _output_dir(manifest: dict[str, Any], output_dir: Path) -> Path:
    expected = Path(manifest["evidence"]["directory"]).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise ExecutionGateError("evidence 必须写入 #188 冻结的新目录")
    return output_dir


def _historical_report(manifest: dict[str, Any], output_dir: Path) -> Path:
    sessions_root = output_dir.parent
    historical_name = PurePosixPath(manifest["historical_evidence"]["directory"]).name
    return sessions_root / historical_name / manifest["historical_evidence"]["canary_report"]


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
    historical = _historical_report(manifest, output_dir)
    if not historical.is_file() or protocol.file_sha256(historical) != manifest["historical_evidence"]["canary_report_sha256"]:
        raise ExecutionGateError("#184 historical canary report missing or drifted")
    entries = sorted(str(path.relative_to(output_dir)).replace("\\", "/") for path in output_dir.rglob("*") if path.is_file()) if output_dir.exists() else []
    if require_empty and entries:
        raise ExecutionGateError("reachability 前要求新 evidence 目录为空")
    return {
        "ready": True,
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release["revision"],
        "network_access_medium": medium,
        "historical_canary_report_sha256": manifest["historical_evidence"]["canary_report_sha256"],
        "evidence_files": entries,
        "zero_managed_containers": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


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

    from deerflow.agents.middlewares.tool_error_handling_middleware import build_subagent_runtime_middlewares
    from deerflow.agents.thread_state import ThreadState
    from deerflow.compile.operations import get_compile_services
    from deerflow.subagents.builtins.compiler_agent import COMPILER_AGENT_CONFIG
    from deerflow.tools.bound_compile_tools import get_bound_compile_tools

    if arm not in ARMS:
        raise ExecutionGateError("unknown checkpoint arm")
    session = lifecycle_arm.session
    policy = primary._policy(manifest, arm=arm, image_id=session.image_id)
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
    adapter: parity.RuntimeParityToolAdapter | None = None
    try:
        model = model_factory(manifest["provider"], session.thread_id) if model_factory is not None else primary._create_provider_model(manifest["provider"], experiment_thread_id=session.thread_id)
        tools = get_bound_compile_tools(session)
        run_tool = next(item for item in tools if item.name == "run_container_bash")
        submit_tool = next(item for item in tools if item.name == "submit_build_result")
        adapter = parity.RuntimeParityToolAdapter(
            run_tool=run_tool,
            submit_tool=submit_tool,
            staged_artifacts_present=lambda: any(path.is_file() and not path.is_symlink() for path in Path(session.leadagent_artifacts_dir).rglob("*")),
        )

        @tool("run_container_bash", parse_docstring=True)
        def runtime_parity_run_container_bash(
            command: str,
            timeout_seconds: int = 300,
            workdir: str | None = None,
            command_role: str = "other",
        ) -> str:
            """在当前 arm 中执行 runtime-parity 白名单动作。

            Args:
                command: 要执行的单一 bash 命令。
                timeout_seconds: 单条命令超时，最多 300 秒。
                workdir: 容器内工作目录。
                command_role: evidence 命令角色。
            """
            return adapter.run(command, timeout_seconds=timeout_seconds, workdir=workdir, command_role=command_role)

        @tool("submit_build_result", parse_docstring=True)
        def runtime_parity_submit_build_result(supporting_command_id: str | None = None) -> str:
            """提交当前 arm 的 staged artifacts。

            Args:
                supporting_command_id: 可选的成功构建命令 ID。
            """
            return adapter.submit(supporting_command_id)

        agent = create_agent(
            model=model,
            tools=[runtime_parity_run_container_bash, runtime_parity_submit_build_result],
            middleware=[parity.SerialToolCallMiddleware(), *build_subagent_runtime_middlewares(lazy_init=True)],
            system_prompt=COMPILER_AGENT_CONFIG.system_prompt,
            state_schema=ThreadState,
            checkpointer=InMemorySaver(),
        )
        state = {"messages": message_state["messages"], "artifacts": [], "viewed_images": {}}
        config = {
            "configurable": {"thread_id": session.thread_id},
            "recursion_limit": manifest["continuation"]["maximum_graph_steps_per_arm"],
        }
        await asyncio.wait_for(
            agent.ainvoke(state, config=config, context={"thread_id": session.thread_id, "agent_name": "compiler"}),
            timeout=manifest["continuation"]["work_wall_clock_seconds_per_arm"],
        )
        primary.record_experiment_attempt_budget_completion(session.thread_id)
    finally:
        if adapter is not None:
            budget_sink[arm] = adapter.budget.snapshot()
        primary.deactivate_experiment(session.thread_id)

    authoritative = get_compile_services().manager.load_session(session.session_id, session.thread_id)
    result = primary.validate_arm_evidence(manifest, arm=arm, ledger=ledger, session=authoritative)
    result["runtime_parity_action_budget"] = budget_sink[arm]
    ledger.append("experiment.completed", {"status": "passed"})
    return result


def _with_execution_hooks(manifest: dict[str, Any], output_dir: Path, operation: Any) -> Any:
    from deerflow.compile import operations
    from deerflow.tools import bound_compile_tools

    original_protocol = legacy.protocol
    original_collect = legacy.collect_preflight
    original_continuation = primary.run_arm_continuation
    original_submit_impl = operations.submit_build_result_impl
    original_write_once = legacy.v3_runner._write_once
    action_budgets: dict[str, dict[str, Any]] = {}
    report_path = output_dir / manifest["evidence"]["canary_report"]

    def parent_submit_through_bound_wrapper(*, session: Any, supporting_command_id: str | None = None) -> str:
        return bound_compile_tools._submit_with_post_build_phase(session, supporting_command_id=supporting_command_id)

    async def continuation(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return await run_arm_continuation(*args, **kwargs, budget_sink=action_budgets)

    def write_once(path: Path, value: Any) -> None:
        if path.resolve(strict=False) == report_path.resolve(strict=False):
            value = {
                **value,
                "schema_version": manifest["execution"]["report_schema_version"],
                "document_type": manifest["execution"]["report_document_type"],
                "runtime_parity": manifest["runtime_parity"],
                "runtime_parity_action_budgets": action_budgets,
                "historical_canary_report_sha256": manifest["historical_evidence"]["canary_report_sha256"],
                "historical_pair_replacement": False,
            }
        original_write_once(path, value)

    legacy.protocol = protocol
    legacy.collect_preflight = collect_preflight
    primary.run_arm_continuation = continuation
    operations.submit_build_result_impl = parent_submit_through_bound_wrapper
    legacy.v3_runner._write_once = write_once
    try:
        return operation()
    finally:
        legacy.protocol = original_protocol
        legacy.collect_preflight = original_collect
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
        lambda: legacy.execute_reachability(manifest, output_dir=output_dir, repo_root=repo_root, model_factory=model_factory),
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
        lambda: legacy.execute_pair(manifest, output_dir=output_dir, repo_root=repo_root, model_factory=model_factory),
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
        result: Any = {"status": "valid", "manifest_sha256": protocol.canonical_sha256(manifest), "provider_calls": 0, "formal_attempts": 0, "model_tokens": 0}
    elif args.command == "preflight":
        result = collect_preflight(manifest, output_dir=args.output_dir, require_empty=True)
    elif args.command == "reachability":
        result = execute_reachability(manifest, output_dir=args.output_dir)
    else:
        result = execute_pair(manifest, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
