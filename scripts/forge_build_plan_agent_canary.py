#!/usr/bin/env python3
"""同任务完整方案/工具Agent开发canary；零Provider接线门禁与真实采集分离。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_repair import audit_frozen, handoff_for_agent  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger, PlanTask  # noqa: E402
from deerflow.compile.plan_agent_canary import CanaryMeter, CanaryWorkflow, ToolBuildService, propose, run_tool_agent, source_packet, unchanged  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import SharedResearchBudget, before_deadline, diagnostic_packet  # noqa: E402
from deerflow.compile.plan_workflow import PlanBudget, PlanContractError  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402


def scripted_model(reference, arm, service=None, probe_reads=False):
    """仅零Provider接线使用人工配方；真实模型永远不进入本分支。"""
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    def reply(calls):
        return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": f"gate-{i}"} for i, (name, args) in enumerate(calls)],
            usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            response_metadata={"model_name": "scripted-gate"},
        )

    class GateModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if arm == "tool" and self.i == len(self.responses) - 1:
                records = service.current().commands
                self.responses[-1] = reply(
                    [
                        (
                            "submit_verified_build",
                            {
                                "supporting_command_id": [r.command_id for r in records if r.role == "build" and r.exit_code == 0][-1],
                                "recipe_command_ids": [r.command_id for r in records if r.role in ("dependency", "configure", "build", "artifact_stage") and r.exit_code == 0],
                            },
                        )
                    ]
                )
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    if arm == "plan":
        responses = [reply([("PlanProposal", {"reason": "脚本化Docker接线，不是模型科研结果", "steps": reference["steps"]})])]
    else:
        calls = [("run_fixed_tests", {}) if step["role"] == "smoke" else ("run_build_command", {"command": step["command"], "command_role": step["role"], "workdir": step["workdir"]}) for step in reference["steps"]]
        responses = [reply(calls), reply([])]
    if probe_reads:
        responses.insert(0, reply([("list_source", {"directory": "/workspace/repo"}), ("list_source", {"directory": "forge_expected_absent_directory"})]))
    return GateModel(responses=responses)


def run_arm(*, item, arm, protocol, root, model=None, reference=None, meter_factory=CanaryMeter, planner=propose, tool_runner=run_tool_agent, probe_reads=False, command_timeout_seconds=180, replay_timeout_seconds=300):
    folder = root / f"{item['name']}-{arm}"
    folder.mkdir(exist_ok=False)
    task = PlanTask.model_validate(item["task"])
    paths = Paths(base_dir=folder / "data", workspace_root=folder, host_workspace_root=str(folder))
    manager = CompileSessionManager(paths=paths, default_image=task.image_id, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=task.image_id, parallel_jobs=2, replay_timeout_seconds=replay_timeout_seconds))
    session = manager.create_session("plan-agent-canary", task.repository_url, image=task.image_id)
    workspace, session_root = Path(session.leadagent_repo_dir), Path(session.metadata_path).parent
    original = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    workflow = service = meter = None
    context = {"task": task.model_dump(mode="json"), "source_packet": [], "state": {"session_status": "inspected"}, "current_plan": None, "handoff": None}

    def packet():
        if service:
            context["state"] = service.observe()
        elif workflow:
            context["state"] = workflow.snapshot()
            context["current_plan"] = workflow.plan.model_dump(mode="json")
        return context

    result = {"name": item["name"], "arm": arm, "kind": "scripted_engineering_gate" if reference else "real_model_development_canary", "status": "started", "transitions": []}
    frozen = {}
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        with tarfile.open(item["source_archive"]) as archive:
            archive.extractall(workspace, filter="data")
        frozen = {p.relative_to(workspace).as_posix(): digest(p) for p in workspace.rglob("*") if p.is_file() and not p.is_symlink()}
        write_json(folder / "original-source-hashes.json", frozen)
        shutil.copyfile(item["source_archive"], Path(session.leadagent_repro_dir) / "source.tar")
        session.commit_sha, session.image_id = task.commit_sha, task.image_id
        session.replay_source_archive_sha256 = task.source_archive_sha256
        session.build_system = session.selected_build_system = task.build_system
        try:
            runtime.create_container(session)
        finally:
            manager.save_session(session)
        session.status = "inspected"
        manager.save_session(session)
        context["source_packet"] = source_packet(workspace, item["source_paths"])
        meter = meter_factory(PlanAgentLedger(folder / "agent"), accepted_models=("scripted-gate",) if reference else tuple(protocol["provider"]["accepted_response_models"]), deadline=protocol["deadline_utc"], packet=packet)
        started = time.monotonic()
        if arm == "plan":
            active_model = scripted_model(reference, arm, probe_reads=probe_reads) if reference else model
            plan, _ = planner(model=active_model, task=task, source_root=workspace, session_root=session_root, meter=meter)
            workflow = CanaryWorkflow(
                plan=plan, session=session, manager=manager, runtime=runtime, budget=PlanBudget(wall_clock_seconds=1200, command_timeout_seconds=command_timeout_seconds), meter=meter, source_root=workspace, frozen=frozen
            )
            while True:
                state = workflow.run()
                result["transitions"].append(state)
                if state["status"] == "ready_for_verification":
                    state = workflow.verify()
                    result["transitions"].append(state)
                if state["status"] != "needs_handoff":
                    break
                handoff = handoff_for_agent(state["handoff"], session_root)
                handoff["recent_commands"] = handoff["recent_commands"][-3:]
                for row in handoff["recent_commands"]:
                    row["output_tail"] = row.get("output_tail", "")[-2000:]
                handoff["diagnostic_logs"] = diagnostic_packet(session_root, handoff)
                context["handoff"] = handoff
                revised, reason = planner(model=active_model, task=task, source_root=workspace, session_root=session_root, meter=meter, current_plan=workflow.plan, handoff=handoff)
                workflow.apply_revision(handoff_id=state["handoff"]["handoff_id"], plan=revised, reason=reason)
            result["status"] = state["status"]
        else:
            service = ToolBuildService(task=task, session=session, manager=manager, source_root=workspace, frozen=frozen, meter=meter)
            active_model = scripted_model(reference, arm, service, probe_reads=probe_reads) if reference else model
            tool_runner(model=active_model, service=service, source_root=workspace, session_root=session_root, meter=meter)
            result["status"] = "verified" if service.verified else "no_verified_delivery"
        result["node_and_acceptance_seconds"] = time.monotonic() - started
        unchanged(workspace, frozen)
        result["fixed_sources_unchanged"] = True
    except Exception as exc:
        result.update(status="stopped", error_class=type(exc).__name__, error_message=str(exc)[:1000] if isinstance(exc, (PlanContractError, ValueError)) else None)
    finally:
        try:
            current = manager.load_session(session.session_id, session.thread_id)
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            result.update(cleanup=asdict(cleanup), session_status=current.status, session_id=current.session_id)
            unchanged(workspace, frozen)
            result["fixed_sources_unchanged"] = True
        except Exception as exc:
            result.update(cleanup={"succeeded": False}, cleanup_error_class=type(exc).__name__)
        finally:
            operations._services = original
            result["agent_usage"] = meter.summary() if meter else {"model_requests": 0, "recorded_tokens": 0, "unknown_usage_requests": 0, "estimated_cost_usd_completed_responses": 0}
            result["strict_completed"] = result["status"] == "verified" and result.get("session_status") == "completed" and result["cleanup"]["succeeded"]
            write_json(folder / "result.json", result)
    return result


def validate(protocol):
    if protocol["identity"] != "cpp-build-plan-agent-canary-v1" or protocol["max_estimated_cost_usd"] != 12 or protocol["deadline_utc"] != "2026-10-19T23:00:00Z":
        raise PlanContractError("阶段身份、预算或截止时间不符")
    before_deadline(protocol["deadline_utc"], 1800)
    parent = audit_frozen(Path(protocol["source_qualification_root"]))
    if parent["inventory_canonical_sha256"] != protocol["source_qualification_inventory_sha256"]:
        raise PlanContractError("参考任务资格身份变化")
    for name, expected in protocol["components"].items():
        path = (REPO_ROOT / name).resolve()
        if not path.is_relative_to(REPO_ROOT) or digest(path) != expected:
            raise PlanContractError("运行组件与协议不符")
    if len(protocol["schedule"]) != 8 or {(row["project"], row["arm"]) for row in protocol["schedule"]} != {(item["name"], arm) for item in protocol["projects"] for arm in ("plan", "tool")}:
        raise PlanContractError("固定双臂顺序不完整")
    for item in protocol["projects"]:
        task = PlanTask.model_validate(item["task"])
        if digest(Path(item["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源码归档变化")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shared-budget-root", type=Path, required=True)
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--gate-root", type=Path, help="真实调用前必须核验同协议零Provider双臂Docker门禁")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    shared = SharedResearchBudget(args.shared_budget_root)
    if shared.authorization["deadline_utc"] != protocol["deadline_utc"] or shared.authorization["max_new_provider_cost_usd"] != 20:
        raise PlanContractError("共享用户授权不匹配")
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    if not args.qualify:
        if args.gate_root is None:
            raise PlanContractError("缺少已封存的零Provider门禁")
        audit(args.gate_root)
        gate = json.loads((args.gate_root / "result.json").read_text())
        if (
            digest(args.gate_root / "protocol.json") != digest(args.protocol)
            or gate["kind"] != "scripted_engineering_gate"
            or len(gate["arms"]) != 8
            or not all(r["strict_completed"] and r["agent_usage"]["recorded_tokens"] == 0 for r in gate["arms"])
        ):
            raise PlanContractError("双臂Docker门禁未通过或与当前协议不符")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes((args.shared_budget_root / "authorization.json").read_bytes())
    if not args.qualify:
        shared.append({"event": "stage.started", "identity": protocol["identity"], "reserved_cost_usd": "12", "protocol_sha256": digest(args.protocol), "evidence_root": str(root)})
    results = []
    try:
        model = None
        references = {}
        if args.qualify:
            references = {item["name"]: item["plan"] for item in json.loads((Path(protocol["source_qualification_root"]) / "protocol.json").read_text())["projects"]}
        else:
            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key:
                raise PlanContractError("缺少已授权Provider凭据")
            model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=key, base_url="https://api.deepseek.com", max_tokens=32768, max_retries=0, timeout=240, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
        projects = {item["name"]: item for item in protocol["projects"]}
        for row in protocol["schedule"]:
            before_deadline(protocol["deadline_utc"], 1800)
            result = run_arm(item=projects[row["project"]], arm=row["arm"], protocol=protocol, root=root, model=model, reference=references.get(row["project"]))
            results.append(result)
            print(json.dumps({k: result.get(k) for k in ("name", "arm", "status", "strict_completed", "agent_usage")}, ensure_ascii=False), flush=True)
            if not result["cleanup"]["succeeded"] or result["agent_usage"]["unknown_usage_requests"]:
                break
    finally:
        known = sum((Decimal(str(r["agent_usage"]["estimated_cost_usd_completed_responses"])) for r in results), Decimal(0))
        unknown = sum(r["agent_usage"]["unknown_usage_requests"] for r in results)
        write_json(
            root / "result.json",
            {
                "identity": protocol["identity"],
                "kind": "scripted_engineering_gate" if args.qualify else "real_model_development_canary",
                "arms": results,
                "known_estimated_cost_usd": str(known),
                "unknown_usage_reservation_usd": str(Decimal("0.40") * unknown),
            },
        )
        sealed = seal(root, protocol, REPO_ROOT, unknown)
        if not args.qualify:
            shared.append(
                {
                    "event": "stage.completed",
                    "identity": protocol["identity"],
                    "charged_cost_usd": str(known + Decimal("0.40") * unknown),
                    "known_estimate_usd": str(known),
                    "unknown_reservation_usd": str(Decimal("0.40") * unknown),
                    "inventory_sha256": sealed["inventory_canonical_sha256"],
                }
            )
    return 0 if len(results) == 8 and all(r["strict_completed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
