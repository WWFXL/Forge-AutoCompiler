#!/usr/bin/env python3
"""同源开发项目的状态/验证正负控制；不调用模型，不修改原始源码。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_repair import audit_frozen  # noqa: E402
from forge_typed_evidence import digest, seal, write_json  # noqa: E402

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.plan_agent_canary import unchanged  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanBudget, PlanWorkflow  # noqa: E402
from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402

CONTROL_NAMES = ("normal", "empty_tests", "omit_bootstrap", "delivery_drift", "foreign_configure")


class CandidateControlWorkflow(PlanWorkflow):
    """只在候选配方层注入遗漏；工作区仍执行完整原始方案。"""

    omit_bootstrap = False

    def replay_recipe(self):
        recipe = super().replay_recipe()
        if not self.omit_bootstrap:
            return recipe
        omitted = self.completed["bootstrap"]
        return operations.build_replay_recipe(
            self._session,
            supporting_command_id=recipe.supporting_command_id,
            recipe_command_ids=[step.command_id for step in recipe.steps if step.command_id != omitted],
            verification_command_ids=[step.command_id for step in recipe.verification_steps],
        )


def prepare_plan(item):
    plan = BuildPlan.model_validate(item["plan"])
    if item["control"] == "empty_tests":
        payload = plan.model_dump(mode="json")
        step = next(step for step in payload["steps"] if step["step_id"] == "configure")
        if "-DBUILD_TESTS=ON" not in step["command"]:
            raise ValueError("空测试控制必须有明确原始测试开关")
        step["command"] = step["command"].replace("-DBUILD_TESTS=ON", "-DBUILD_TESTS=OFF")
        plan = BuildPlan.model_validate(payload)
    return plan


def expected_observation(item, row):
    """只有预定的拒绝原因才算负控制成功；基础设施异常不能替代。"""
    if not row.get("fixed_source_files_unchanged") or not row.get("cleanup", {}).get("succeeded"):
        return False
    control = item["control"]
    if control == "normal":
        return row.get("status") == "verified" and row.get("session_status") == "completed"
    if control == "empty_tests":
        return row.get("status") == "needs_handoff" and row.get("handoff_step") == "check" and row.get("all_command_exit_zero") is True and row.get("test_expectation_satisfied") is False
    if control == "foreign_configure":
        return row.get("error_class") == "PlanContractError" and "权威命令记录变化" in row.get("error", "") and row.get("replay_count") == 0 and row.get("injection_exit_code") == 0
    if control in ("omit_bootstrap", "delivery_drift"):
        required_failure = "recipe_execution_failed" if control == "omit_bootstrap" else "size_mismatch"
        attempts = row.get("replay_attempts", [])
        actual_failure = attempts[-1].get("failure_classification") if attempts else None
        return row.get("status") == "needs_handoff" and row.get("handoff_reason") == "acceptance_failed" and row.get("replay_status") == "failed" and row.get("workspace_test_passed") is True and actual_failure == required_failure
    return False


def inject_change(control, workflow, runtime, manager):
    if control not in ("delivery_drift", "foreign_configure"):
        return None
    session = manager.load_session(workflow.session_id, workflow.thread_id)
    command = "printf 'FORGE_CONTROL_DRIFT' >> /artifacts/pigz" if control == "delivery_drift" else "cmake -S . -B build -DBUILD_TESTS=OFF"
    log = manager.local_logs_dir(session) / "control-injection.log"
    outcome = runtime.exec(session, command, workdir="/workspace/repo", timeout_seconds=120, log_path=str(log), strict_shell=True)
    manager.log_event(session, "control.injected", control=control, command=command, exit_code=outcome.exit_code, log_path=str(log))
    if outcome.exit_code != 0:
        raise ValueError("受控状态变化未执行成功")
    if control == "foreign_configure":
        # 显式模拟同一会话中另一个合法执行方的配置动作；不可伪装成原步骤。
        record = BuildCommandRecord(stage="controlled_external_actor", command=command, workdir="/workspace/repo", role="configure", exit_code=0, log_path=str(log), completed_at=utc_now_iso(), termination="completed")
        manager.record_command(session, record)
    return outcome.exit_code


def run_case(item, folder, protocol):
    folder.mkdir(exist_ok=False)
    plan = prepare_plan(item)
    paths = Paths(base_dir=folder / "data", workspace_root=folder, host_workspace_root=str(folder))
    manager = CompileSessionManager(paths=paths, default_image=plan.image_id, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=plan.image_id, parallel_jobs=2, replay_timeout_seconds=protocol["replay_timeout_seconds"]))
    session = manager.create_session("state-controls", plan.repository_url, image=plan.image_id)
    prior_services = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    row = {"name": item["name"], "control": item["control"], "status": "started", "provider_calls": 0}
    started = time.monotonic()
    source = Path(session.leadagent_repo_dir)
    frozen = {}
    try:
        source.mkdir(parents=True, exist_ok=True)
        archive = Path(item["source_archive"])
        if digest(archive) != plan.source_archive_sha256:
            raise ValueError("控制源码归档身份变化")
        with tarfile.open(archive) as handle:
            frozen = {member.name: hashlib.sha256(handle.extractfile(member).read()).hexdigest() for member in handle.getmembers() if member.isfile()}
            handle.extractall(source, filter="data")
        write_json(folder / "original-source-hashes.json", frozen)
        unchanged(source, frozen)
        shutil.copyfile(archive, Path(session.leadagent_repro_dir) / "source.tar")
        session.commit_sha, session.image_id = plan.commit_sha, plan.image_id
        session.replay_source_archive_sha256 = plan.source_archive_sha256
        session.build_system = session.selected_build_system = plan.build_system
        try:
            runtime.create_container(session)
        finally:
            manager.save_session(session)
        session.status = "inspected"
        manager.save_session(session)
        workflow = CandidateControlWorkflow(plan=plan, session=session, manager=manager, runtime=runtime, budget=PlanBudget(**protocol["plan_budget"]))
        workflow.omit_bootstrap = item["control"] == "omit_bootstrap"
        state = workflow.run()
        row["initial"] = state
        row["status"] = state["status"]
        if state["status"] == "ready_for_verification":
            row["injection_exit_code"] = inject_change(item["control"], workflow, runtime, manager)
            state = workflow.verify()
        handoff = state.get("handoff") or {}
        row.update(status=state["status"], final=state, handoff_step=handoff.get("step_id"), handoff_reason=handoff.get("reason"))
    except Exception as exc:
        row.update(status="stopped", error_class=type(exc).__name__, error=str(exc)[:1000])
    finally:
        current = manager.load_session(session.session_id, session.thread_id)
        row["all_command_exit_zero"] = bool(current.commands) and all(command.exit_code == 0 and not command.timed_out for command in current.commands)
        row["replay_count"] = len(current.replay_attempts)
        row["replay_status"] = current.replay_attempts[-1].status if current.replay_attempts else None
        row["verification"] = asdict(current.verification) if current.verification else None
        row["replay_attempts"] = [asdict(attempt) for attempt in current.replay_attempts]
        # 真实通过由Workflow的持久化状态给出；不把成功退出码替代测试marker。
        state_file = Path(current.metadata_path).parent / "build-plan/state.json"
        persisted = json.loads(state_file.read_text()) if state_file.exists() else {}
        row["workspace_test_passed"] = "check" in persisted.get("completed", {})
        row["test_expectation_satisfied"] = row["workspace_test_passed"]
        try:
            unchanged(source, frozen)
            row["fixed_source_files_unchanged"] = bool(frozen)
        except Exception as exc:
            row.update(fixed_source_files_unchanged=False, source_error_class=type(exc).__name__)
        try:
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            row.update(cleanup=asdict(cleanup), session_status=current.status, session_id=current.session_id)
        except Exception as exc:
            row.update(cleanup={"succeeded": False}, cleanup_error_class=type(exc).__name__)
        finally:
            operations._services = prior_services
            row["elapsed_seconds"] = time.monotonic() - started
            row["expected_observation"] = expected_observation(item, row)
            write_json(folder / "result.json", row)
    return row


def validate(protocol):
    if protocol["identity"] != "cpp-build-state-validation-controls-v1" or protocol["provider_calls"] != 0 or len(protocol["cases"]) != 7:
        raise ValueError("状态控制身份或样本边界错误")
    before_deadline(protocol["deadline_utc"], 3000)
    parent = audit_frozen(Path(protocol["parent_evidence"]))
    if parent["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("父参考资格变化")
    for path, expected in protocol["components"].items():
        if digest(REPO_ROOT / path) != expected:
            raise ValueError("控制组件变化")
    for item in protocol["cases"]:
        if item["control"] not in CONTROL_NAMES or digest(Path(item["source_archive"])) != prepare_plan(item).source_archive_sha256:
            raise ValueError("控制材料变化")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    results = []
    try:
        for item in protocol["cases"]:
            try:
                before_deadline(protocol["deadline_utc"], 3000)
            except ValueError:
                results.append({"name": item["name"], "status": "not_started_deadline", "expected_observation": False})
                continue
            row = run_case(item, root / item["name"], protocol)
            results.append(row)
            print(json.dumps({key: row.get(key) for key in ("name", "status", "expected_observation", "elapsed_seconds")}), flush=True)
            if not row.get("cleanup", {}).get("succeeded"):
                break
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "provider_calls": 0, "cases": results})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(results) == 7 and all(row["expected_observation"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
