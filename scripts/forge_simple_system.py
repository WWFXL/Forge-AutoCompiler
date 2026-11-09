#!/usr/bin/env python3
"""简洁任务统一入口；CLI仅接脚本模型，正式Provider运行另须冻结授权。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/packages/harness"))

from forge_build_simple_task import full_completion, save  # noqa: E402
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_agent_canary import source_packet  # noqa: E402
from deerflow.compile.plan_workflow import PlanBudget, PlanStep, _digest  # noqa: E402
from deerflow.compile.simple_build_agents import SimpleBuildMeter, SimpleToolBuildService, run_simple_tool_agent  # noqa: E402
from deerflow.compile.simple_build_experience import SimpleProjectRecipe, SimpleStateTargetBank, recipe_validation_succeeded, verified_simple_recipe  # noqa: E402
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow, source_unchanged  # noqa: E402
from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask, SimpleBuildPlan, propose_simple  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402

METHODS = ("forge", "forge_experience", "strong_tool_agent", "cxxcrafter")


class ScriptedSimpleModel(FakeMessagesListChatModel):
    """真实Agent图的离线回复；脚本用当前命令ID提交，不连接任何Provider。"""

    calls: list[dict] = []
    position: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, **kwargs):
        if self.position >= len(self.calls):
            raise RuntimeError("离线回复已用完，不循环或自动重试")
        row = copy.deepcopy(self.calls[self.position])
        self.position += 1
        packet = json.loads(next(m.content for m in reversed(messages) if m.type == "human"))
        commands = packet.get("commands", [])
        args = row.get("args", {})
        if args.get("supporting_command_id") == "$last_build":
            args["supporting_command_id"] = next(r["command_id"] for r in reversed(commands) if r["role"] == "build" and r["exit_code"] == 0)
        if args.get("recipe_command_ids") == "$successful_recipe":
            args["recipe_command_ids"] = [r["command_id"] for r in commands if r["role"] in {"dependency", "configure", "build"} and r["exit_code"] == 0 and not r["timed_out"]]
        self.responses = [
            AIMessage(content="", tool_calls=[dict(name=row["name"], args=args, id=f"script-{self.position}")], usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0), response_metadata=dict(model_name="zero-provider-script"))
        ]
        self.i = 0
        return super()._generate(messages, **kwargs)


def run_simple_system(
    *,
    task,
    reference,
    source_archive,
    output_root,
    method,
    model,
    accepted_models,
    family,
    recipe=None,
    bank=None,
    deadline=None,
    maximum_cost_usd="1.00",
    author_test_seconds=120,
    replay_seconds=240,
    recovery_model=None,
    recovery_accepted_models=None,
    pricing_by_model=None,
    initial_plan=None,
    state_router=None,
    validation_scope="author_tests",
    harness=None,
):
    """可复用执行接点；本函数不加载配置或凭据，不自行创建Provider。"""
    if method not in METHODS[:3]:
        raise ValueError("此接点仅接受Forge/经验Forge/强工具Agent")
    if (task.task_version == "main-build-v1") != (validation_scope == "main_build"):
        raise ValueError("公开任务版本必须与主构建/旧作者测试范围一致")
    if reference.task_sha256 != _digest(task.model_dump(mode="json")):
        raise ValueError("独立参考不属于当前公开任务")
    if method != "forge_experience" and (recipe is not None or bank is not None):
        raise ValueError("无经验处理不能读取经验库或配方")
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    if hashlib.sha256(source_archive.read_bytes()).hexdigest() != task.source_archive_sha256:
        raise ValueError("源码归档与公开任务不一致")
    root = output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    save(root / "common-public-task.json", task.model_dump(mode="json"))
    save(root / "private-reference.json", reference.model_dump(mode="json"))
    save(
        root / "scope.json",
        dict(
            method=method,
            family=family,
            accepted_models=accepted_models,
            recovery_accepted_models=recovery_accepted_models or accepted_models,
            maximum_cost_usd=maximum_cost_usd,
            deadline=deadline,
            validation_scope=validation_scope,
            kind="zero_provider_engineering" if accepted_models == ("zero-provider-script",) else "requires_external_authorized_protocol",
        ),
    )
    paths = Paths(base_dir=root / "data", workspace_root=root, host_workspace_root=str(root))
    manager = CompileSessionManager(paths=paths, default_image=task.image_id, parallel_jobs=task.parallel_jobs)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=task.image_id, parallel_jobs=task.parallel_jobs, replay_timeout_seconds=replay_seconds))
    session = manager.create_session("simple-system", task.repository_url, image=task.image_id)
    original = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    workflow, service, final_plan = None, None, None
    started = time.monotonic()
    result = dict(method=method, status="started", source_unchanged=None)
    ledger = PlanAgentLedger(root / "agent")
    initial_packet = {}
    planning_seconds, recovery_seconds = 0.0, 0.0

    def packet():
        if service:
            return dict(task=task.model_dump(mode="json"), source_packet=initial_packet.get("source_packet", []), **service.observe())
        return dict(task=task.model_dump(mode="json"), source_packet=initial_packet.get("source_packet", []))

    meter = SimpleBuildMeter(ledger, accepted_models=accepted_models, deadline=deadline or (datetime.now(UTC) + timedelta(hours=1)).isoformat(), packet=packet, maximum_cost_usd=maximum_cost_usd, pricing_by_model=pricing_by_model)
    try:
        source = Path(session.leadagent_repo_dir)
        source.mkdir(parents=True, exist_ok=True)
        with tarfile.open(source_archive) as archive:
            archive.extractall(source, filter="data")
        shutil.copyfile(source_archive, Path(session.leadagent_repro_dir) / "source.tar")
        session.commit_sha, session.image_id = task.commit_sha, task.image_id
        session.replay_source_archive_sha256 = task.source_archive_sha256
        session.build_system = session.selected_build_system = task.build_system
        try:
            runtime.create_container(session)
        finally:
            manager.save_session(session)
        session.status = "inspected"
        manager.save_session(session)
        names = [p.name for p in sorted(source.iterdir()) if p.is_file() and (p.name.lower().startswith(("readme", "install")) or p.name in {"CMakeLists.txt", "Makefile", "configure.ac", "meson.build"})][:8]
        initial_packet["source_packet"] = source_packet(source, names)
        if method == "strong_tool_agent":
            # 仅创建共享记录/外部检查对象；占位方案从不执行或送入基线上下文。
            plan = SimpleBuildPlan(task=task, steps=(PlanStep(step_id="build", role="build", command="make", source="外部检查占位，不执行", expected="不执行"),))
        else:
            if initial_plan is not None:
                plan = SimpleBuildPlan.model_validate(initial_plan)
                if plan.task != task:
                    raise ValueError("固定初始方案不属于当前任务")
                ledger.append("initial_plan.fixed", plan_sha256=plan.fingerprint(), model_planning_skipped=True)
            elif recipe is not None and recipe.match(task):
                plan = recipe.materialize(task)
                ledger.append("recipe.selected", source_id=recipe.source_id, recipe_sha256=_digest(recipe.model_dump(mode="json")), model_planning_skipped=True)
            else:
                if recipe is not None:
                    ledger.append("recipe.abstained", reason="公开任务身份变化")
                planning_start = time.monotonic()
                try:
                    plan, _ = propose_simple(model=model, task=task, source_root=source, session_root=Path(session.metadata_path).parent, meter=meter, experience_bank=bank, family=family, harness=harness)
                finally:
                    planning_seconds += time.monotonic() - planning_start
        # 作者测试统一串行；不改变构建的并行资源，也不把测试指令交给构建Agent。
        serial = reference.model_copy(update={"author_tests": tuple(s.model_copy(update={"command": "export CTEST_PARALLEL_LEVEL=1\n" + s.command}) for s in reference.author_tests)})
        workflow = SimpleBuildWorkflow(plan=plan, session=session, manager=manager, runtime=runtime, reference=serial, budget=PlanBudget(wall_clock_seconds=1200, command_timeout_seconds=180, max_commands=64, max_handoffs=8), meter=meter)
        if method == "strong_tool_agent":
            service = SimpleToolBuildService(workflow, meter)
            run_simple_tool_agent(model=model, service=service, source_root=source, session_root=Path(session.metadata_path).parent, meter=meter)
        else:
            while True:
                workflow.run()
                if workflow.status != "needs_handoff":
                    break
                if state_router is not None and state_router.handle(workflow, meter):
                    continue
                recovery_start = time.monotonic()
                try:
                    meter.accepted_models = recovery_accepted_models or accepted_models
                    revised, reason = propose_simple(
                        model=recovery_model if recovery_model is not None else model,
                        task=task,
                        source_root=source,
                        session_root=Path(session.metadata_path).parent,
                        meter=meter,
                        current_plan=workflow.plan,
                        handoff=workflow.handoff,
                        experience_bank=bank,
                        family=family,
                        harness=harness,
                        revision_validator=workflow.validate_revision,
                    )
                finally:
                    recovery_seconds += time.monotonic() - recovery_start
                workflow.apply_revision(handoff_id=workflow.handoff["handoff_id"], plan=revised, reason=reason)
        if workflow.status == "primary_completed":
            # Workflow自身计时始于初始规划之后；系统比较必须另存包含规划/准备的时间。
            workflow.timings["time_to_primary_from_arm_start_seconds"] = time.monotonic() - started
            final_plan = workflow.plan
            result.update(workflow.postchecks(author_test_seconds=author_test_seconds, validation_scope=validation_scope))
        source_unchanged(source, workflow.baseline)
        result["source_unchanged"] = True
        result.update(status=workflow.status, layers=workflow.layers, timings=workflow.timings)
    except Exception as exc:
        result.update(status="error", error_type=type(exc).__name__, error=str(exc))
        if "原源码/测试" in str(exc):
            result["source_unchanged"] = False
        if workflow:
            result.update(layers=workflow.layers, timings=workflow.timings)
    finally:
        try:
            current = manager.load_session(session.session_id, session.thread_id)
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            result.update(cleanup=asdict(cleanup), session_status=current.status)
        except Exception as exc:
            result.update(cleanup=dict(succeeded=False), cleanup_error=f"{type(exc).__name__}: {exc}")
        result.update(agent_usage=meter.summary(), arm_total_wall_seconds=time.monotonic() - started)
        result.setdefault("timings", {}).update(initial_planning_seconds=planning_seconds, recovery_agent_seconds=recovery_seconds)
        if result.get("layers"):
            if validation_scope == "main_build":
                result["layers"]["main_build_task_completed"] = bool(result["layers"]["primary_build_completed"] and result["source_unchanged"] is True and result["cleanup"]["succeeded"])
                result["layers"]["full_completed"] = None  # 旧完整任务包含作者测试，不能冒称通过。
            else:
                result["layers"]["full_completed"] = full_completion(result["layers"], result["cleanup"]["succeeded"])
            result["layers"]["reproducible_delivery_completed"] = bool(
                result["layers"].get("primary_build_completed")
                and result["layers"].get("delivery") == "passed"
                and result["layers"].get("final_verification_passed") is True
                and result["layers"].get("clean_replay") == "passed"
                and result["source_unchanged"] is True
                and result["cleanup"]["succeeded"]
            )
            if result["status"] == "error" or result["source_unchanged"] is False:
                result["layers"]["full_completed"] = False
                result["layers"]["reproducible_delivery_completed"] = False
                if validation_scope == "main_build":
                    result["layers"]["main_build_task_completed"] = False
        result["validation_scope"] = validation_scope
        if state_router is not None:
            result["router_usage"] = state_router.summary()
        if final_plan is not None and method != "strong_tool_agent" and recipe_validation_succeeded(task, result):
            value = verified_simple_recipe(source_id=root.name, plan=final_plan, validation=result)
            save(root / "verified-simple-recipe.json", value.model_dump(mode="json"))
        save(root / "result.json", result)
        operations._services = original
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--agent-script", type=Path, required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--recipe", type=Path)
    parser.add_argument("--experience-bank", type=Path)
    args = parser.parse_args()
    if args.method != "forge_experience" and (args.recipe or args.experience_bank):
        parser.error("只有经验Forge可读取方案库/经验库")
    if args.method == "cxxcrafter":
        from forge_simple_cxx_reference import run_scripted_cxx

        result = run_scripted_cxx(
            task=PublicBuildTask.model_validate_json(args.task.read_text()),
            reference=BuildReference.model_validate_json(args.reference.read_text()),
            source_archive=args.source_archive,
            output_root=args.output_root,
            calls=json.loads(args.agent_script.read_text()),
        )
    else:
        result = run_simple_system(
            task=PublicBuildTask.model_validate_json(args.task.read_text()),
            reference=BuildReference.model_validate_json(args.reference.read_text()),
            source_archive=args.source_archive,
            output_root=args.output_root,
            method=args.method,
            model=ScriptedSimpleModel(responses=[], calls=json.loads(args.agent_script.read_text())),
            accepted_models=("zero-provider-script",),
            family=args.family,
            recipe=SimpleProjectRecipe.model_validate_json(args.recipe.read_text()) if args.recipe else None,
            bank=SimpleStateTargetBank.load(args.experience_bank) if args.experience_bank else None,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("layers", {}).get("primary_build_completed") and result["cleanup"]["succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
