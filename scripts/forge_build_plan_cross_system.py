#!/usr/bin/env python3
"""独立跨系统开发走读；脚本化门禁与真实模型结果分开保存。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_repair import handoff_for_agent, seal_attempt  # noqa: E402

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger, PlanTask  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_cross_system import CrossSystemMeter, SharedResearchBudget, before_deadline, diagnostic_packet, propose_cross_system  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanBudget, PlanContractError, PlanStep, PlanWorkflow  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scripted_plan(task: PlanTask) -> BuildPlan:
    steps = []
    if task.build_system == "autotools":
        for step_id, role, command, source in (
            ("dependency", "dependency", "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y libudev-dev", ".github/workflows/linux.yml"),
            ("bootstrap", "configure", "./bootstrap.sh", ".github/workflows/linux.yml"),
            ("configure", "configure", "./configure --enable-tests-build", "configure.ac"),
        ):
            steps.append(PlanStep(step_id=step_id, role=role, command=command, source=source, expected="脚本化接线前提"))
    steps.append(PlanStep(step_id="build", role="build", command="make -j2", source="Makefile", expected="编译目标"))
    steps.extend(task.verification_steps)
    path = "lib/libzstd.a" if task.build_system == "make" else "libusb/.libs/libusb-1.0.so.0.4.0"
    steps.append(PlanStep(step_id="stage", role="artifact_stage", command=f"cp {path} /artifacts/{task.artifact_paths[0]}", source="任务交付", expected="精确暂存"))
    return BuildPlan.model_validate({**task.model_dump(exclude={"verification_steps"}), "steps": steps})


def source_hashes(root):
    return {path.relative_to(root).as_posix(): sha(path) for path in root.rglob("*") if path.is_file() and not path.is_symlink()}


def assert_sources_unchanged(root, frozen):
    if any(not (root / name).is_file() or sha(root / name) != digest for name, digest in frozen.items()):
        raise PlanContractError("原始源码或测试被修改，不允许降低固定任务")


def run_project(*, item, protocol, root, model=None, qualify=False):
    task = PlanTask.model_validate(item["task"])
    archive = Path(item["source_archive"])
    folder = root / item["name"]
    folder.mkdir(exist_ok=False)
    meter = CrossSystemMeter(PlanAgentLedger(folder / "agent"), accepted_models=tuple(protocol["provider"]["accepted_response_models"]), deadline=protocol["request_deadline_utc"])
    paths = Paths(base_dir=folder / "data", workspace_root=folder, host_workspace_root=str(folder))
    manager = CompileSessionManager(paths=paths, default_image=task.image_id, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=task.image_id, parallel_jobs=2, replay_timeout_seconds=300))
    session = manager.create_session("cross-system", task.repository_url, image=task.image_id)
    original = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    result = {"name": item["name"], "kind": "scripted_engineering_gate" if qualify else "real_model_development_walkthrough", "status": "started", "transitions": []}
    try:
        workspace = Path(session.leadagent_repo_dir)
        workspace.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as handle:
            handle.extractall(workspace, filter="data")
        frozen = source_hashes(workspace)
        (folder / "original-source-hashes.json").write_text(json.dumps(frozen, indent=2) + "\n")
        shutil.copyfile(archive, Path(session.leadagent_repro_dir) / "source.tar")
        session.commit_sha, session.image_id = task.commit_sha, task.image_id
        session.replay_source_archive_sha256 = task.source_archive_sha256
        session.build_system = session.selected_build_system = task.build_system
        try:
            runtime.create_container(session)
        finally:
            manager.save_session(session)
        session.status = "inspected"
        manager.save_session(session)
        plan = scripted_plan(task) if qualify else propose_cross_system(model=model, task=task, source_root=workspace, meter=meter)[0]
        meter.ledger.save("initial-plan.json", plan.model_dump(mode="json"))
        workflow = PlanWorkflow(plan=plan, session=session, manager=manager, runtime=runtime, budget=PlanBudget(command_timeout_seconds=180, wall_clock_seconds=900))
        session_root = Path(session.metadata_path).parent
        while True:
            state = workflow.run()
            result["transitions"].append(state)
            assert_sources_unchanged(workspace, frozen)
            if state["status"] == "ready_for_verification":
                if task.build_system == "autotools" and "#define HAVE_LIBUDEV 1" not in (workspace / "config.h").read_text():
                    raise PlanContractError("固定libusb后端未启用，不能按原任务记成功")
                result["recipe"] = asdict(workflow.replay_recipe())
                state = workflow.verify()
                result["transitions"].append(state)
            if state["status"] != "needs_handoff" or qualify:
                break
            handoff = handoff_for_agent(state["handoff"], session_root)
            # 仍保留完整内部证据；模型上下文只取最近三条的有限尾部。
            handoff["recent_commands"] = handoff["recent_commands"][-3:]
            for command in handoff["recent_commands"]:
                command["output_tail"] = command.get("output_tail", "")[-2000:]
            handoff["diagnostic_logs"] = diagnostic_packet(session_root, handoff)
            revised, reason = propose_cross_system(model=model, task=task, source_root=workspace, meter=meter, current_plan=workflow.plan, handoff=handoff)
            workflow.apply_revision(handoff_id=state["handoff"]["handoff_id"], plan=revised, reason=reason)
        result.update(status=state["status"], session_id=session.session_id, fixed_sources_unchanged=True)
    except Exception as exc:
        result.update(status="stopped", error_class=type(exc).__name__, error_message=str(exc)[:1000] if isinstance(exc, PlanContractError) else None)
    finally:
        try:
            current = manager.load_session(session.session_id, session.thread_id)
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            result.update(cleanup=asdict(cleanup), session_status=current.status)
        except Exception as exc:
            result.update(cleanup={"succeeded": False}, cleanup_error_class=type(exc).__name__)
        finally:
            operations._services = original
            result["agent_usage"] = meter.summary()
            (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def validate(protocol):
    if protocol["identity"] != "cpp-build-plan-cross-system-v1" or protocol["max_estimated_cost_usd"] != 4:
        raise PlanContractError("阶段身份或预算不符")
    before_deadline(protocol["request_deadline_utc"], 1800)
    for name, digest in protocol["components"].items():
        path = (REPO_ROOT / name).resolve()
        if not path.is_relative_to(REPO_ROOT) or sha(path) != digest:
            raise PlanContractError("运行组件不符")
    for item in protocol["projects"]:
        task = PlanTask.model_validate(item["task"])
        if sha(Path(item["source_archive"])) != task.source_archive_sha256:
            raise PlanContractError("源码归档不符")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shared-budget-root", type=Path, required=True)
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    shared = SharedResearchBudget(args.shared_budget_root)
    if shared.authorization["deadline_utc"] != protocol["deadline_utc"] or shared.authorization["max_new_provider_cost_usd"] != 20:
        raise PlanContractError("用户总授权与阶段边界不符")
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes(args.shared_budget_root.joinpath("authorization.json").read_bytes())
    results = []
    if not args.qualify:
        shared.append({"event": "stage.started", "identity": protocol["identity"], "reserved_cost_usd": "4", "protocol_sha256": sha(args.protocol), "evidence_root": str(root)})
    try:
        model = None
        if not args.qualify:
            # 必须先验证完整协议、用户授权及共享支出准入，再读取凭据。
            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key:
                raise PlanContractError("缺少授权Provider凭据")
            model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=key, base_url="https://api.deepseek.com", max_tokens=8192, max_retries=0, timeout=120, reasoning_effort="low", extra_body={"thinking": {"type": "enabled"}})
        for item in protocol["projects"]:
            before_deadline(protocol["request_deadline_utc"], 1800)
            result = run_project(item=item, protocol=protocol, root=root, model=model, qualify=args.qualify)
            results.append(result)
            print(json.dumps({"project": item["name"], "status": result["status"], "session_status": result.get("session_status"), "usage": result["agent_usage"]}, ensure_ascii=False), flush=True)
            if not result["cleanup"]["succeeded"] or result["agent_usage"]["unknown_usage_requests"]:
                break
    finally:
        known = sum(result["agent_usage"]["estimated_cost_usd_completed_responses"] for result in results)
        unknown = sum(result["agent_usage"]["unknown_usage_requests"] for result in results)
        summary = {
            "identity": protocol["identity"],
            "kind": "scripted_engineering_gate" if args.qualify else "real_model_development_walkthrough",
            "projects": results,
            "known_estimated_cost_usd": known,
            "unknown_usage_reservation_usd": unknown * 0.4,
        }
        (root / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

        # 共用封存器只读取实际代码；此阶段没有使用meter参数。
        class SealUsage:
            def summary(self):
                return {"unknown_usage_requests": unknown}

        seal_attempt(root, protocol, SealUsage())
        if not args.qualify:
            shared.append(
                {
                    "event": "stage.completed",
                    "identity": protocol["identity"],
                    "charged_cost_usd": str(known + unknown * 0.4),
                    "known_estimate_usd": str(known),
                    "unknown_reservation_usd": str(unknown * 0.4),
                    "inventory_sha256": json.loads((root / "seal.json").read_text())["inventory_canonical_sha256"],
                }
            )
    return 0 if all(result["cleanup"]["succeeded"] for result in results) and len(results) == len(protocol["projects"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
