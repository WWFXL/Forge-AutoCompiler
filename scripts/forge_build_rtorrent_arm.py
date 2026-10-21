#!/usr/bin/env python3
"""rtorrent三策略共同任务入口；旧身份和组件保持只读。"""

from __future__ import annotations

import shutil
import tarfile
import time
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

from forge_build_plan_agent_canary import (
    CanaryMeter,
    CompileDockerRuntime,
    CompileSessionManager,
    Paths,
    PlanAgentLedger,
    PlanBudget,
    RuntimeConfig,
    diagnostic_packet,
    digest,
    handoff_for_agent,
    operations,
    propose,
    run_tool_agent,
    source_packet,
    unchanged,
    write_json,
)

from deerflow.compile.generated_file_boundary import (
    FileBoundary,
    guard_main,
    guard_plan,
    original_plan,
)
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.source_preparation import (
    paths_fingerprint,
    preparation_step,
    with_preparation,
)
from deerflow.compile.staged_verification import StagedBoundaryToolService as BoundaryToolService
from deerflow.compile.staged_verification import StagedBoundaryWorkflow as BoundaryWorkflow
from deerflow.compile.staged_verification import StagedVerificationTask


def public_workflow_state(boundary, plan, state):
    """可逆投影状态与交接的同一身份；权威状态文件保持原包装方案。"""
    projected = deepcopy(state)
    guarded = plan.fingerprint()
    public = original_plan(boundary, plan, strip_preparation=True)
    if projected["plan_sha256"] != guarded:
        raise PlanContractError("状态与实际包装方案身份不一致")
    projected["guarded_plan_sha256"] = guarded
    projected["plan_sha256"] = public.fingerprint()
    if projected.get("handoff"):
        if projected["handoff"]["plan_sha256"] != guarded:
            raise PlanContractError("权威交接与包装方案身份不一致")
        projected["handoff"]["guarded_plan_sha256"] = guarded
        projected["handoff"]["plan_sha256"] = public.fingerprint()
    return projected, public


def run_arm(
    *,
    item,
    arm,
    protocol,
    root,
    model=None,
    reference=None,
    meter_factory=CanaryMeter,
    planner=propose,
    tool_runner=run_tool_agent,
    probe_reads=False,
    command_timeout_seconds=180,
    replay_timeout_seconds=300,
):
    boundary = FileBoundary.model_validate(item["file_boundary"])
    folder = root / f"{item['name']}-{arm}"
    folder.mkdir(exist_ok=False)
    task = StagedVerificationTask.model_validate(item["task"])
    if digest(Path(item["source_archive"])) != task.source_archive_sha256:
        raise PlanContractError("源码归档SHA与任务不符")
    paths = Paths(base_dir=folder / "data", workspace_root=folder, host_workspace_root=str(folder))
    manager = CompileSessionManager(paths=paths, default_image=task.image_id, parallel_jobs=2)
    runtime = CompileDockerRuntime(
        manager=manager,
        config=RuntimeConfig(
            image=task.image_id,
            parallel_jobs=2,
            replay_timeout_seconds=replay_timeout_seconds,
            network="none",
        ),
    )
    session = manager.create_session("plan-agent-canary", task.repository_url, image=task.image_id)
    workspace, session_root = (
        Path(session.leadagent_repo_dir),
        Path(session.metadata_path).parent,
    )
    original = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    workflow = service = meter = None
    context = {
        "task": task.model_dump(mode="json"),
        "source_packet": [],
        "state": {"session_status": "inspected"},
        "current_plan": None,
        "handoff": None,
    }

    def packet():
        if service:
            context["state"] = service.observe()
        elif workflow:
            state, public = public_workflow_state(boundary, workflow.plan, workflow.snapshot())
            context["state"] = state
            context["current_plan"] = public.model_dump(mode="json")
        return context

    result = {
        "name": item["name"],
        "arm": arm,
        "kind": "scripted_engineering_gate" if reference else "real_model_development_canary",
        "status": "started",
        "transitions": [],
    }
    frozen = {}
    context["file_boundary"] = {
        "sha256": boundary.fingerprint(),
        "generations": [r.model_dump(mode="json") for r in boundary.generations],
        "protected_original_file_count": len(boundary.protected_inputs),
        "protected_scope": "全部原作者文件（818项），除精确generations输出外禁止修改；原文件可通过只读源码工具逐项查看。",
        "rule": "作者源码/测试/语义输入不可写。仅列表中的精确标准生成命令可更新声明输出。不要返回边界包装脚本，系统会统一加入。",
    }
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        with tarfile.open(item["source_archive"]) as archive:
            archive.extractall(workspace, filter="data")
        if any(p.is_symlink() for p in workspace.rglob("*")):
            raise PlanContractError("当前边界资格不接纳原归档符号链接")
        frozen = {p.relative_to(workspace).as_posix(): digest(p) for p in workspace.rglob("*") if p.is_file() and not p.is_symlink()}
        if frozen != boundary.baseline:
            raise PlanContractError("新任务文件边界与原归档不符")
        frozen = boundary.protected
        write_json(folder / "original-source-hashes.json", frozen)
        write_json(folder / "file-boundary.json", boundary.model_dump(mode="json"))
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
        meter = meter_factory(
            PlanAgentLedger(folder / "agent"),
            accepted_models=("scripted-gate",) if reference else tuple(protocol["provider"]["accepted_response_models"]),
            deadline=protocol["deadline_utc"],
            packet=packet,
        )
        meter.tracker.limits = replace(
            meter.tracker.limits,
            command_timeout_seconds=command_timeout_seconds,
            replay_timeout_seconds=replay_timeout_seconds,
        )
        started = time.monotonic()
        expected_source_paths = paths_fingerprint(boundary.baseline)
        prepare = preparation_step(expected_source_paths)
        preparation_service = BoundaryToolService(
            boundary=boundary,
            task=task,
            session=session,
            manager=manager,
            source_root=workspace,
            frozen=frozen,
            meter=meter,
        )
        meter.ledger.append("source.preparation_started", expected_paths_sha256=expected_source_paths)
        preparation_started = time.monotonic()
        prepared, preparation_result = preparation_service.execute(prepare.command, prepare.role, prepare.workdir)
        result["source_preparation"] = {
            **prepared,
            "expected_paths_sha256": expected_source_paths,
            "wall_seconds": time.monotonic() - preparation_started,
        }
        meter.ledger.append("source.preparation_completed", **result["source_preparation"])
        if preparation_result.exit_code != 0 or not all(marker in preparation_result.combined_output for marker in prepare.required_output):
            raise PlanContractError("共同源码准备失败：停止于首次模型/模板操作之前")
        context["common_source_preparation"] = {
            "status": "prepared",
            "expected_paths_sha256": expected_source_paths,
            "command": prepare.command,
            "execution_contract": "系统已执行且会绑定clean replay；建议不得返回forge-source-prepare或重复git init/add。保留原索引文件集合。",
        }
        if arm == "plan":
            active_model = model
            plan, _ = planner(
                model=active_model,
                task=task,
                source_root=workspace,
                session_root=session_root,
                meter=meter,
            )
            plan = guard_plan(boundary, with_preparation(plan, expected_source_paths))
            workflow = BoundaryWorkflow(
                task=task,
                boundary=boundary,
                preparation_command_id=prepared["command_id"],
                plan=plan,
                session=session,
                manager=manager,
                runtime=runtime,
                budget=PlanBudget(
                    wall_clock_seconds=1200,
                    command_timeout_seconds=command_timeout_seconds,
                ),
                meter=meter,
                source_root=workspace,
                frozen=frozen,
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
                public_plan = original_plan(boundary, workflow.plan, strip_preparation=True)
                handoff["guarded_plan_sha256"] = handoff["plan_sha256"]
                handoff["plan_sha256"] = public_plan.fingerprint()
                revised, reason = planner(
                    model=active_model,
                    task=task,
                    source_root=workspace,
                    session_root=session_root,
                    meter=meter,
                    current_plan=public_plan,
                    handoff=handoff,
                )
                revised = guard_plan(boundary, with_preparation(revised, expected_source_paths))
                workflow.apply_revision(
                    handoff_id=state["handoff"]["handoff_id"],
                    plan=revised,
                    reason=reason,
                )
            result["status"] = state["status"]
        else:
            service = BoundaryToolService(
                boundary=boundary,
                task=task,
                session=session,
                manager=manager,
                source_root=workspace,
                frozen=frozen,
                meter=meter,
            )
            active_model = model
            tool_runner(
                model=active_model,
                service=service,
                source_root=workspace,
                session_root=session_root,
                meter=meter,
            )
            result["status"] = "verified" if service.verified else "no_verified_delivery"
        result["node_and_acceptance_seconds"] = time.monotonic() - started
        unchanged(workspace, frozen)
        result["protected_sources_unchanged"] = True
    except Exception as exc:
        result.update(
            status="stopped",
            error_class=type(exc).__name__,
            error_message=str(exc)[:1000] if isinstance(exc, (PlanContractError, ValueError)) else None,
        )
    finally:
        try:
            current = manager.load_session(session.session_id, session.thread_id)
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            result.update(
                cleanup=asdict(cleanup),
                session_status=current.status,
                session_id=current.session_id,
            )
        except Exception as exc:
            result.update(cleanup={"succeeded": False}, cleanup_error_class=type(exc).__name__)
        finally:
            operations._services = original
            try:
                guard_main(
                    boundary.model_dump(mode="json"),
                    ":",
                    str(workspace),
                    str(workspace),
                )
                result["protected_sources_unchanged"] = True
                result["file_boundary_passed"] = True
            except Exception as exc:
                result.update(
                    file_boundary_passed=False,
                    boundary_error_class=type(exc).__name__,
                    boundary_error_message=str(exc)[:1000],
                )
            result["agent_usage"] = (
                meter.summary()
                if meter
                else {
                    "model_requests": 0,
                    "recorded_tokens": 0,
                    "unknown_usage_requests": 0,
                    "estimated_cost_usd_completed_responses": 0,
                }
            )
            result["strict_completed"] = (
                result["status"] == "verified" and result.get("session_status") == "completed" and result["cleanup"]["succeeded"] and result.get("protected_sources_unchanged", False) and result.get("file_boundary_passed", False)
            )
            write_json(folder / "result.json", result)
    return result
