#!/usr/bin/env python3
"""Issue #436：Agent Token 预算语义与证据一致性零 Provider 门禁。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from langchain_core.callbacks import CallbackManagerForLLMRun  # noqa: E402
from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, BaseMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langchain_core.runnables import Runnable  # noqa: E402
from langchain_core.tools import BaseTool  # noqa: E402
from pydantic import Field  # noqa: E402

from deerflow.compile.agent_workflow_runtime import run_agent_workflow_node_v1  # noqa: E402
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)
from deerflow.compile.schemas import BuildCommandRecord, CompileSession, utc_now_iso  # noqa: E402

IDENTITY = "cpp-agent-token-budget-semantics-gate-v1"
V2_EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions/benchmark-evidence-progress-aware-harness-comparison-v2"
V2_INVENTORY_CANONICAL_SHA256 = "fb8f77bf05885dcb2f008fc2799de8361f7dd91af558815b7cff42b01cd5dce8"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
COMMIT_SHA = "d" * 40


class GateManager:
    def __init__(self, session: CompileSession):
        self.session = session

    def load_session(self, session_id: str, thread_id: str | None = None) -> CompileSession:
        if session_id != self.session.session_id or thread_id != self.session.thread_id:
            raise RuntimeError("scripted Session identity 漂移")
        return self.session


class ScriptedChatModel(BaseChatModel):
    responses: list[object]
    calls: int = 0
    bind_kwargs: list[dict[str, object]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "token-budget-gate-scripted"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice
        self.bind_kwargs.append(kwargs)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        response = self.responses[self.calls]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


class FailingChatModel(ScriptedChatModel):
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.calls += 1
        raise RuntimeError("scripted provider failure")


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _budget(
    *,
    threshold: int | None,
    response_limit: int | None,
    max_model_requests: int = 8,
) -> AgentWorkflowBudget:
    return AgentWorkflowBudget(
        max_model_requests=max_model_requests,
        max_recorded_tokens=threshold,
        max_agent_steps=24,
        max_tool_calls=32,
        max_commands=24,
        node_timeout_seconds=60,
        command_timeout_seconds=30,
        evaluator_timeout_seconds=60,
        replay_timeout_seconds=120,
        cleanup_timeout_seconds=30,
        max_recorded_tokens_per_response=response_limit,
    )


def _session(root: Path, case_id: str) -> CompileSession:
    session_id = f"session-{case_id.replace('_', '-')}"
    session_dir = root / session_id
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.joinpath("lib").mkdir(parents=True)
    artifacts_dir.joinpath("lib/libfmt.a").write_bytes(b"archive")
    now = utc_now_iso()
    commands = [
        BuildCommandRecord(
            stage="bash",
            command="cmake -S . -B build",
            workdir="/workspace/repo",
            command_id="command-configure",
            role="configure",
            completed_at=now,
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build build",
            workdir="/workspace/repo",
            command_id="command-build",
            role="build",
            completed_at=now,
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cp build/libfmt.a /artifacts/lib/libfmt.a",
            workdir="/workspace/repo",
            command_id="command-stage",
            role="artifact_stage",
            completed_at=now,
            exit_code=0,
        ),
    ]
    return CompileSession(
        session_id=session_id,
        thread_id="thread-token-budget-gate",
        repo_url="https://github.com/fmtlib/fmt.git",
        branch="main",
        image="autocompiler:gcc13",
        image_id=f"sha256:{SHA256_B}",
        status="inspected",
        run_id=f"run-{case_id.replace('_', '-')}",
        commit_sha=COMMIT_SHA,
        selected_build_system="cmake",
        metadata_path=str(session_dir / "session.json"),
        leadagent_repo_dir=str(session_dir / "workspace/repo"),
        leadagent_artifacts_dir=str(artifacts_dir),
        leadagent_logs_dir=str(session_dir / "logs"),
        leadagent_repro_dir=str(session_dir / "repro"),
        commands=commands,
    )


def _node_input(session: CompileSession, case_id: str, budget: AgentWorkflowBudget) -> AgentBuildNodeInput:
    return AgentBuildNodeInput(
        task_id=f"task-{case_id.replace('_', '-')}",
        attempt_id=f"attempt-{case_id.replace('_', '-')}",
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=COMMIT_SHA,
        source_snapshot_sha256=SHA256_A,
        build_system_candidates=("cmake",),
        target_contract=AgentWorkflowTargetContract(
            target_id="fmt-library",
            artifact_types=("static_library",),
            artifact_path_patterns=("lib/libfmt.a",),
            functional_oracle_ref="oracle-fmt-link-v1",
        ),
        operation_policy_ref="compile-policy-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=f"sha256:{SHA256_B}",
            parallel_jobs=4,
            network_policy="compile-network-v1",
        ),
        budget=budget,
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=SHA256_A,
            protocol_sha256=SHA256_B,
            runner_sha256=SHA256_C,
        ),
        initial_observation={"build_system": "cmake"},
    )


def _submit_args(*, valid: bool) -> dict[str, Any]:
    return {
        "candidate_id": "candidate-001",
        "build_system": "cmake",
        "supporting_command_ids": ["command-build"],
        "artifact_paths": ["lib/libfmt.a"] if valid else ["/invalid"],
        "target_mapping": {"fmt-library": "lib/libfmt.a"},
        "recipe_command_ids": ["command-configure", "command-build", "command-stage"],
        "agent_summary": "scripted candidate",
        "known_limitations": [],
    }


def _tool_message(*, valid: bool, call_id: str, total_tokens: int) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "submit_candidate_v1",
                "args": _submit_args(valid=valid),
                "id": call_id,
                "type": "tool_call",
            }
        ],
        usage_metadata={
            "input_tokens": max(0, total_tokens - 5),
            "output_tokens": min(5, total_tokens),
            "total_tokens": total_tokens,
        },
    )


def _events(session: CompileSession, attempt_id: str) -> list[dict[str, Any]]:
    path = Path(session.metadata_path).parent / "agent-workflow" / attempt_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _case_definitions() -> list[dict[str, Any]]:
    return [
        {
            "case": "below_threshold",
            "budget": _budget(threshold=100, response_limit=70),
            "model": ScriptedChatModel(responses=[_tool_message(valid=True, call_id="submit-1", total_tokens=40)]),
            "expected": ("submitted", None, None, 40, 1),
        },
        {
            "case": "exact_threshold",
            "budget": _budget(threshold=100, response_limit=100),
            "model": ScriptedChatModel(
                responses=[
                    _tool_message(valid=True, call_id="submit-1", total_tokens=100),
                    AIMessage(content="unreachable"),
                ]
            ),
            "expected": ("no_submission", "budget_exhausted", "recorded_tokens", 100, 1),
        },
        {
            "case": "bounded_overshoot",
            "budget": _budget(threshold=100, response_limit=70),
            "model": ScriptedChatModel(
                responses=[
                    _tool_message(valid=False, call_id="invalid-1", total_tokens=70),
                    _tool_message(valid=True, call_id="submit-2", total_tokens=40),
                    AIMessage(content="unreachable"),
                ]
            ),
            "expected": ("no_submission", "budget_exhausted", "recorded_tokens", 110, 2),
        },
        {
            "case": "response_bound_violation",
            "budget": _budget(threshold=100, response_limit=50),
            "model": ScriptedChatModel(
                responses=[
                    _tool_message(valid=True, call_id="submit-1", total_tokens=60),
                    AIMessage(content="unreachable"),
                ]
            ),
            "expected": ("failed", "budget_contract_violation", "recorded_tokens_per_response", 60, 1),
        },
        {
            "case": "missing_usage",
            "budget": _budget(threshold=100, response_limit=50),
            "model": ScriptedChatModel(responses=[AIMessage(content="missing"), AIMessage(content="unreachable")]),
            "expected": ("failed", "usage_incomplete", None, 0, 1),
        },
        {
            "case": "invalid_usage",
            "budget": _budget(threshold=100, response_limit=50),
            "model": ScriptedChatModel(
                responses=[
                    AIMessage(
                        content="invalid",
                        usage_metadata={"input_tokens": 5, "output_tokens": 5, "total_tokens": 11},
                    ),
                    AIMessage(content="unreachable"),
                ]
            ),
            "expected": ("failed", "usage_incomplete", None, 0, 1),
        },
        {
            "case": "provider_failure",
            "budget": _budget(threshold=100, response_limit=50),
            "model": FailingChatModel(responses=[]),
            "expected": ("failed", "node_failed", None, 0, 1),
        },
        {
            "case": "strict_non_token_budget",
            "budget": _budget(threshold=100, response_limit=70, max_model_requests=1),
            "model": ScriptedChatModel(
                responses=[
                    _tool_message(valid=False, call_id="invalid-1", total_tokens=40),
                    _tool_message(valid=True, call_id="submit-2", total_tokens=40),
                ]
            ),
            "expected": ("no_submission", "budget_exhausted", "model_requests", 40, 1),
        },
        {
            "case": "unbounded_legacy",
            "budget": _budget(threshold=None, response_limit=None),
            "model": ScriptedChatModel(
                responses=[
                    _tool_message(valid=False, call_id="invalid-1", total_tokens=70),
                    _tool_message(valid=True, call_id="submit-2", total_tokens=40),
                ]
            ),
            "expected": ("submitted", None, None, 110, 2),
        },
    ]


def _run_case(root: Path, definition: dict[str, Any]) -> dict[str, Any]:
    case_id = definition["case"]
    budget = definition["budget"]
    model = definition["model"]
    expected_status, expected_failure, expected_reason, expected_tokens, expected_calls = definition["expected"]
    session = _session(root, case_id)
    node_input = _node_input(session, case_id, budget)
    result = asyncio.run(
        run_agent_workflow_node_v1(
            node_input=node_input,
            session=session,
            manager=GateManager(session),  # type: ignore[arg-type]
            model=model,
        )
    )
    events = _events(session, node_input.attempt_id)
    completed = [event["payload"] for event in events if event["event_type"] == "model.request_completed"]
    started_count = sum(event["event_type"] == "model.request_started" for event in events)
    failed_count = sum(event["event_type"] == "model.request_failed" for event in events)
    incomplete_count = sum(event["event_type"] == "model.request_usage_incomplete" for event in events)
    completed_tokens = sum(item["recorded_tokens"] for item in completed)
    synthetic_cost_units = sum(item["input_tokens"] + 2 * item["output_tokens"] for item in completed)
    request_closed = started_count == len(completed) + failed_count + incomplete_count
    passed = (
        result.node_status == expected_status
        and result.primary_failure == expected_failure
        and result.budget_terminal_reason == expected_reason
        and result.usage.recorded_tokens == expected_tokens
        and model.calls == expected_calls
        and completed_tokens == result.usage.recorded_tokens
        and request_closed
    )
    return {
        "case": case_id,
        "passed": passed,
        "node_status": result.node_status,
        "primary_failure": result.primary_failure,
        "budget_terminal_reason": result.budget_terminal_reason,
        "model_calls": model.calls,
        "requests_started": started_count,
        "requests_completed": len(completed),
        "requests_failed": failed_count,
        "requests_usage_incomplete": incomplete_count,
        "completed_event_recorded_tokens": completed_tokens,
        "node_result_recorded_tokens": result.usage.recorded_tokens,
        "synthetic_cost_units": synthetic_cost_units,
        "request_lifecycle_closed": request_closed,
        "authorized_recorded_tokens": budget.authorized_recorded_tokens,
    }


def _audit_v2_inventory() -> dict[str, Any]:
    inventory_path = V2_EVIDENCE_ROOT / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    files = inventory.get("files")
    valid = isinstance(files, list) and inventory.get("canonical_sha256") == V2_INVENTORY_CANONICAL_SHA256 and _canonical_sha256(files) == V2_INVENTORY_CANONICAL_SHA256
    if valid:
        valid = all((path := V2_EVIDENCE_ROOT / item["path"]).is_file() and path.stat().st_size == item["size"] and _file_sha256(path) == item["sha256"] for item in files)
    return {
        "valid": valid,
        "file_count": inventory.get("file_count"),
        "total_bytes": inventory.get("total_bytes"),
        "canonical_sha256": inventory.get("canonical_sha256"),
    }


def run_gate(*, audit_v2: bool = True) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="forge-token-budget-gate-") as raw:
        root = Path(raw)
        cases = [_run_case(root, definition) for definition in _case_definitions()]
    v2_inventory = (
        _audit_v2_inventory()
        if audit_v2
        else {
            "valid": True,
            "file_count": 30108,
            "total_bytes": 719928939,
            "canonical_sha256": V2_INVENTORY_CANONICAL_SHA256,
        }
    )
    passed = all(item["passed"] for item in cases) and v2_inventory["valid"] is True
    return {
        "schema_version": "1.0.0",
        "identity": IDENTITY,
        "tracking_issue": 436,
        "status": "passed" if passed else "failed",
        "decision": ("proceed_to_progress_aware_harness_v3_replication_decision" if passed else "stop_before_progress_aware_harness_v3_replication"),
        "cases": cases,
        "summary": {
            "passed": sum(item["passed"] for item in cases),
            "total": len(cases),
            "credential_read": False,
            "provider_requests": 0,
            "docker_runs": 0,
            "formal_effect_attempts": 0,
            "v2_evidence_mutated": not v2_inventory["valid"],
        },
        "v2_inventory": v2_inventory,
        "interpretation": {
            "supports": [
                "bounded post-response Token 合同可完整记录触阈响应",
                "达到停止阈值后不会发起下一次模型请求",
                "events、node result 和报告可使用同一实际 Token 用量",
            ],
            "does_not_support": [
                "H1 相对 H0 的成功率或成本效果",
                "动态预算 controller、Jev、自然失败或开放世界效果",
                "progress-aware harness v3 已获得执行授权",
            ],
        },
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Agent Token 预算语义与证据一致性门禁 v1",
        "",
        f"**决定：`{report['decision']}`。**",
        "",
        f"状态：`{report['status']}`；门禁通过 `{summary['passed']}/{summary['total']}`。",
        "",
        "## 门禁结果",
        "",
        "| Case | 通过 | Token（events/result） | 请求（started/completed/failed/incomplete） | 终止 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in report["cases"]:
        terminal = item["primary_failure"] or "success"
        if item["budget_terminal_reason"]:
            terminal += f":{item['budget_terminal_reason']}"
        requests = "/".join(
            str(item[field])
            for field in (
                "requests_started",
                "requests_completed",
                "requests_failed",
                "requests_usage_incomplete",
            )
        )
        lines.append(f"| `{item['case']}` | {'是' if item['passed'] else '否'} | {item['completed_event_recorded_tokens']}/{item['node_result_recorded_tokens']} | {requests} | `{terminal}` |")
    inventory = report["v2_inventory"]
    lines.extend(
        [
            "",
            "## 冻结证据检查",
            "",
            f"v2 inventory：`valid={str(inventory['valid']).lower()}`，{inventory['file_count']} files / {inventory['total_bytes']} bytes，canonical SHA-256 `{inventory['canonical_sha256']}`。",
            "",
            "## 结论边界",
            "",
            "本门禁是工程修复验证。通过只说明 bounded post-response Token 预算可以完整计量已发生的响应、在触阈后停止后续请求，并保持事件与节点结果一致；它只解除全新 H0/H1 v3 确认性复现的预算合同阻塞。",
            "",
            "本结果不改变 v2 的正式停止决定，不证明 H1 效果，不评价动态预算 controller、Jev、自然失败或开放世界。v3 尚未创建或获得执行授权。",
            "",
            "全程 0 credential、0 Provider、0 Docker、0 formal effect attempt；v2 evidence 保持只读。",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: dict[str, Any]) -> None:
    REPORT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    REPORT_MD_PATH.write_text(_render_markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run",))
    arguments = parser.parse_args()
    if arguments.command == "run":
        report = run_gate()
        write_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["status"] == "passed" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
