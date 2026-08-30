#!/usr/bin/env python3
"""Issue #222 R3 Make 完整 agent construction 的零 provider 门禁。"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langchain.agents import create_agent
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.memory import InMemorySaver

import forge_opaque_provenance_r1_execution_runner as r1
import forge_opaque_provenance_r3_make_execution_failure_gate as failure_gate
import forge_opaque_provenance_r3_make_execution_protocol as protocol
import forge_opaque_provenance_r3_make_execution_runner as frozen_runner

from deerflow.agents.middlewares import tool_error_handling_middleware
from deerflow.agents.middlewares.tool_error_handling_middleware import (
    build_subagent_runtime_middlewares,
)
from deerflow.agents.thread_state import ThreadState
from deerflow.compile.evidence import (
    ExperimentAttemptBudget,
    ExperimentLedger,
    activate_experiment,
    deactivate_experiment,
    get_active_experiment,
    record_experiment_attempt_budget_completion,
)
from deerflow.subagents.builtins.compiler_agent import COMPILER_AGENT_CONFIG

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "forge-opaque-provenance-r3-make-agent-construction-gate-1.0.0"
EXPECTED_MANIFEST_SHA256 = failure_gate.EXPECTED_MANIFEST_SHA256
PROBE_THREAD_ID = "r3-make-agent-construction-probe"


class AgentConstructionGateError(RuntimeError):
    """Agent 构造、首请求、异常分类或 cleanup 顺序未闭合。"""


class ProbeChatModel(BaseChatModel):
    """只产生一条终结文本的本地 fake model。"""

    model_name: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    calls: int = 0
    bound_tool_count: int = 0
    parallel_tool_calls: bool | None = None

    @property
    def _llm_type(self) -> str:
        return "r3-make-agent-construction-probe"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tool_choice
        self.bound_tool_count = len(tools)
        self.parallel_tool_calls = kwargs.get("parallel_tool_calls")
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.calls += 1
        if self.calls != 1:
            raise AgentConstructionGateError("fake model request count exceeded one")
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="CONSTRUCTION_GATE_OK",
                        response_metadata={"model_name": self.model_name},
                        usage_metadata={
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "total_tokens": 0,
                        },
                    )
                )
            ]
        )


def checkpoint_messages() -> list[BaseMessage]:
    return [
        HumanMessage(
            content=(
                "Continue from the failed submit and satisfy the verifier without "
                "changing the frozen repository or target."
            )
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "submit_build_result",
                    "args": {},
                    "id": "r3-parent-submit",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content=json.dumps(
                {
                    "status": "failed",
                    "classification": "build_system_unproven",
                },
                sort_keys=True,
            ),
            tool_call_id="r3-parent-submit",
        ),
    ]


def _probe_tools() -> tuple[list[BaseTool], Any]:
    parity, observability = failure_gate.build_runtime_bindings()

    @tool("raw_run_container_bash", parse_docstring=True)
    def raw_run_container_bash(
        command: str,
        timeout_seconds: int = 300,
        workdir: str | None = None,
        command_role: str = "other",
    ) -> str:
        """拒绝 construction gate 中意外发生的容器命令。

        Args:
            command: 未执行的探针命令。
            timeout_seconds: 未使用的探针超时。
            workdir: 未使用的探针目录。
            command_role: 未使用的探针角色。
        """
        del command, timeout_seconds, workdir, command_role
        raise AgentConstructionGateError("construction gate must not execute tools")

    @tool("raw_submit_build_result", parse_docstring=True)
    def raw_submit_build_result(supporting_command_id: str | None = None) -> str:
        """拒绝 construction gate 中意外发生的提交。

        Args:
            supporting_command_id: 未使用的 supporting command identity。
        """
        del supporting_command_id
        raise AgentConstructionGateError("construction gate must not submit")

    action_policy = parity.FrozenActionPolicy()
    adapter = observability.ObservableRuntimeParityToolAdapter(
        run_tool=raw_run_container_bash,
        submit_tool=raw_submit_build_result,
        policy=action_policy,
        staged_artifacts_present=lambda: False,
    )

    @tool("run_container_bash", parse_docstring=True)
    def observable_run_container_bash(
        command: str,
        timeout_seconds: int = 300,
        workdir: str | None = None,
        command_role: str = "other",
    ) -> str:
        """通过 R3 adapter 验证工具绑定，但不允许 fake model 调用。

        Args:
            command: R3 action command。
            timeout_seconds: 动作超时。
            workdir: 冻结构建目录。
            command_role: evidence command role。
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
        """通过 R3 adapter 验证 submit 绑定，但不允许 fake model 调用。

        Args:
            supporting_command_id: 成功 producer identity。
        """
        return adapter.submit(supporting_command_id)

    return [observable_run_container_bash, observable_submit_build_result], adapter


def _request_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    return {
        name: sum(event["event"] == name for event in events)
        for name in (
            "model.request_started",
            "model.request_completed",
            "model.request_failed",
            "model.request_cancelled",
        )
    }


async def run_success_probe(
    manifest: dict[str, Any],
    *,
    ledger_path: Path,
) -> dict[str, Any]:
    if protocol.canonical_sha256(manifest) != EXPECTED_MANIFEST_SHA256:
        raise AgentConstructionGateError("R3 execution manifest identity drifted")
    ledger = ExperimentLedger.create(
        ledger_path,
        experiment_id="experiment_33333333333333333333333333333333",
        physical_attempt_id="mechanism_attempt_33333333333333333333333333333333",
        context={"scope": "r3-make-agent-construction-probe"},
    )
    policy = frozen_runner._policy(
        manifest,
        arm="baseline",
        image_id="sha256:" + "3" * 64,
    )
    budget = ExperimentAttemptBudget(
        total_wall_clock_seconds=60,
        cleanup_reserve_seconds=10,
        max_compiler_invocations=1,
        max_model_requests=1,
    )
    activate_experiment(
        thread_id=PROBE_THREAD_ID,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
        attempt_budget=budget,
    )

    parity, observability = failure_gate.build_runtime_bindings()
    registry = observability.RejectionObservationRegistry()
    tools, adapter = _probe_tools()
    middlewares = [
        parity.SerialToolCallMiddleware(),
        *build_subagent_runtime_middlewares(lazy_init=True),
    ]
    observed_middleware, original_request_completed = r1._install_model_origin_observer(
        middlewares,
        registry,
    )
    original_failure_recorder = tool_error_handling_middleware.record_agent_tool_failure

    def observed_failure(
        request: Any,
        exc: Exception,
        *,
        execution_mode: str,
    ) -> dict[str, Any] | None:
        failure, _observation = registry.record_tool_failure(
            request,
            exc,
            execution_mode=execution_mode,
        )
        return failure

    tool_error_handling_middleware.record_agent_tool_failure = observed_failure
    model = ProbeChatModel()
    try:
        agent = create_agent(
            model=model,
            tools=tools,
            middleware=middlewares,
            system_prompt=COMPILER_AGENT_CONFIG.system_prompt,
            state_schema=ThreadState,
            checkpointer=InMemorySaver(),
        )
        final_state = await agent.ainvoke(
            {
                "messages": checkpoint_messages(),
                "artifacts": [],
                "viewed_images": {},
            },
            config={
                "configurable": {"thread_id": PROBE_THREAD_ID},
                "recursion_limit": 8,
            },
            context={
                "thread_id": PROBE_THREAD_ID,
                "agent_name": "compiler",
            },
        )
        record_experiment_attempt_budget_completion(PROBE_THREAD_ID)
    finally:
        tool_error_handling_middleware.record_agent_tool_failure = (
            original_failure_recorder
        )
        observed_middleware._request_completed = original_request_completed
        deactivate_experiment(PROBE_THREAD_ID)

    ledger.append("experiment.completed", {"status": "passed"})
    events = ledger.read()
    counts = _request_counts(events)
    if (
        counts
        != {
            "model.request_started": 1,
            "model.request_completed": 1,
            "model.request_failed": 0,
            "model.request_cancelled": 0,
        }
        or model.calls != 1
        or model.bound_tool_count != 2
        or model.parallel_tool_calls is not False
        or get_active_experiment(PROBE_THREAD_ID) is not None
        or adapter.budget.snapshot()["consumed"]
        != {"inspection": 0, "repair_build": 0, "artifact_stage": 0, "submit": 0}
    ):
        raise AgentConstructionGateError("successful construction probe did not close")
    messages = final_state["messages"]
    if len(messages) != 4 or messages[-1].content != "CONSTRUCTION_GATE_OK":
        raise AgentConstructionGateError("checkpoint message continuation drifted")
    return {
        "status": "passed",
        "restored_message_count": 3,
        "restored_message_types": [
            type(message).__name__ for message in checkpoint_messages()
        ],
        "final_message_count": len(messages),
        "model_calls": model.calls,
        "bound_tool_count": model.bound_tool_count,
        "parallel_tool_calls": model.parallel_tool_calls,
        "request_evidence": counts,
        "action_budget_consumed": adapter.budget.snapshot()["consumed"],
        "active_experiment_released": True,
    }


def run_failure_probe(*, ledger_path: Path) -> dict[str, Any]:
    ledger = ExperimentLedger.create(
        ledger_path,
        experiment_id="experiment_44444444444444444444444444444444",
        physical_attempt_id="mechanism_attempt_44444444444444444444444444444444",
        context={"scope": "r3-make-pre-model-failure-probe"},
    )
    policy = frozen_runner._policy(
        protocol.load_manifest(),
        arm="baseline",
        image_id="sha256:" + "4" * 64,
    )
    activate_experiment(
        thread_id=PROBE_THREAD_ID,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    try:
        failure_gate.build_runtime_bindings()
        raise AttributeError("injected construction failure")
    except AttributeError as exc:
        deactivate_experiment(PROBE_THREAD_ID)
        result = failure_gate.classify_pre_model_failure(
            arm="baseline",
            ledger=ledger,
            error=exc,
        )
    finally:
        deactivate_experiment(PROBE_THREAD_ID)
    if (
        result is None
        or result["status"] != "invalid"
        or result["model_requests"] != 0
        or result["model_behavior"]["terminal_error_class"] != "AttributeError"
        or get_active_experiment(PROBE_THREAD_ID) is not None
    ):
        raise AgentConstructionGateError("pre-model failure probe did not close")
    return {
        "status": "passed",
        "classification": "pre_model_execution_error",
        "terminal_error_class": "AttributeError",
        "model_requests": 0,
        "active_experiment_released": True,
    }


def run_cleanup_probe() -> dict[str, Any]:
    calls: list[str] = []

    class ProbeGate:
        def cleanup(self, capture_id: str, *, parent_session: Any) -> Any:
            calls.append(f"cleanup:{capture_id}:{parent_session.session_id}")
            return SimpleNamespace(phase="cleaned")

    result = failure_gate.cleanup_after_deactivation(
        ProbeGate(),
        "r3-construction-probe",
        parent_session=SimpleNamespace(session_id="parent-probe"),
        experiment_thread_ids=["parent-probe", "baseline-probe", "treatment-probe"],
        deactivate=lambda thread_id: calls.append(f"deactivate:{thread_id}"),
    )
    expected = [
        "deactivate:parent-probe",
        "deactivate:baseline-probe",
        "deactivate:treatment-probe",
        "cleanup:r3-construction-probe:parent-probe",
    ]
    if result.phase != "cleaned" or calls != expected:
        raise AgentConstructionGateError("cleanup ordering probe did not close")
    return {"status": "passed", "calls": calls}


async def validate_gate(manifest: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="forge-r3-agent-construction-"
    ) as directory:
        root = Path(directory)
        success = await run_success_probe(
            manifest,
            ledger_path=root / "success.jsonl",
        )
        failure = run_failure_probe(ledger_path=root / "failure.jsonl")
        cleanup = run_cleanup_probe()
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_opaque_provenance_r3_make_agent_construction_gate",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "success_probe": success,
        "failure_probe": failure,
        "cleanup_probe": cleanup,
        "temporary_ledger_deleted": True,
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "formal_evidence_writes": 0,
        "model_tokens": 0,
        "checkpoint_created": False,
        "pair_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.add_argument("--manifest", type=Path, default=protocol.DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest, args.repo_root)
    result = asyncio.run(validate_gate(manifest))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
