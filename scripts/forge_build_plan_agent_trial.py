#!/usr/bin/env python3
"""独立小规模方案 Agent 试运行；只有协议与明确授权匹配后才读取模型凭据。"""

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
sys.path.insert(0, str(REPO_ROOT / "backend" / "packages" / "harness"))

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger, PlanAgentMeter, PlanTask, propose_plan, trial_budget  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanBudget, PlanContractError, PlanWorkflow  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_inputs(protocol_path: Path, archive_path: Path, authorization_path: Path | None = None) -> dict:
    protocol = json.loads(protocol_path.read_text())
    if protocol["identity"] != "cpp-build-plan-agent-trial-v1" or protocol["kind"] != "development_trial_not_effect_comparison":
        raise PlanContractError("试运行身份不匹配")
    task = PlanTask.model_validate(protocol["task"])
    if task.source_archive_sha256 != sha(archive_path):
        raise PlanContractError("源码归档哈希不匹配")
    if protocol["agent_budget"] != asdict(trial_budget()) or protocol["max_estimated_cost_usd"] != 2:
        raise PlanContractError("试运行预算不匹配")
    expected_provider = {
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com",
        "thinking": True,
        "max_output_tokens": 8192,
        "max_retries": 0,
        "timeout_seconds": 120,
        "accepted_response_models": ["DeepSeek-V4-Pro-0813", "deepseek-v4-pro"],
        "input_usd_per_million": 1.32,
        "output_usd_per_million": 3.96,
    }
    if protocol["provider"] != expected_provider:
        raise PlanContractError("Provider 或估算单价不匹配")
    for name, digest in protocol["components"].items():
        path = (REPO_ROOT / name).resolve()
        if not path.is_relative_to(REPO_ROOT) or sha(path) != digest:
            raise PlanContractError("运行组件已偏离协议")
    required = {
        "scripts/forge_build_plan_agent_trial.py",
        "backend/packages/harness/deerflow/compile/plan_agent.py",
        "backend/packages/harness/deerflow/compile/plan_workflow.py",
        "backend/packages/harness/deerflow/models/patched_deepseek.py",
        "backend/packages/harness/deerflow/compile/agent_workflow_node.py",
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
        "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    }
    if not required.issubset(protocol["components"]):
        raise PlanContractError("协议缺少必要组件身份")
    if authorization_path is not None:
        authorization = json.loads(authorization_path.read_text())
        if authorization != {"identity": protocol["identity"], "protocol_sha256": sha(protocol_path), "decision": "approve_trial", "max_estimated_cost_usd": 2}:
            raise PlanContractError("没有与当前协议匹配的明确试运行授权")
    return protocol


def handoff_for_agent(handoff: dict, session_root: Path) -> dict:
    copied = json.loads(json.dumps(handoff))
    for record in copied.get("recent_commands", []):
        for name in ("log_path", "diagnostic_directory"):
            if record.get(name):
                record[name] = Path(record[name]).relative_to(session_root).as_posix()
    return copied


def inject_controlled_target(plan: BuildPlan) -> BuildPlan:
    changed = False
    steps = []
    for step in plan.steps:
        if step.role == "build" and not changed:
            step = step.model_copy(update={"command": "cmake --build build --parallel 2 --target forge_trial_missing_target", "source": "受控工程故障注入；不是自然失败"})
            changed = True
        steps.append(step)
    return BuildPlan.model_validate({**plan.model_dump(), "steps": steps})


def run_case(*, name: str, plan: BuildPlan, archive_path: Path, root: Path, task: PlanTask, model, meter: PlanAgentMeter) -> dict:
    folder = root / name
    folder.mkdir(exist_ok=False)
    paths = Paths(base_dir=folder / "data", workspace_root=folder, host_workspace_root=str(folder))
    manager = CompileSessionManager(paths=paths, default_image=plan.image_id, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=plan.image_id, parallel_jobs=2, replay_timeout_seconds=180))
    session = manager.create_session("plan-agent-trial-v1", plan.repository_url, image=plan.image_id)
    original = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    result = {"name": name, "status": "started", "controlled_failure": name == "controlled-recovery", "transitions": [], "agent_revisions": []}
    try:
        workspace = Path(session.leadagent_repo_dir)
        workspace.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path) as archive:
            archive.extractall(workspace, filter="data")
        shutil.copyfile(archive_path, Path(session.leadagent_repro_dir) / "source.tar")
        session.commit_sha, session.image_id = plan.commit_sha, plan.image_id
        session.replay_source_archive_sha256 = plan.source_archive_sha256
        session.build_system = session.selected_build_system = plan.build_system
        try:
            runtime.create_container(session)
        finally:
            manager.save_session(session)
        session.status = "inspected"
        manager.save_session(session)
        workflow = PlanWorkflow(plan=plan, session=session, manager=manager, runtime=runtime, budget=PlanBudget())
        session_root = Path(session.metadata_path).parent
        while True:
            state = workflow.run()
            result["transitions"].append(state)
            if state["status"] == "ready_for_verification":
                result["recipe"] = asdict(workflow.replay_recipe())
                state = workflow.verify()
                result["transitions"].append(state)
            if state["status"] != "needs_handoff":
                break
            revised, reason = propose_plan(
                model=model,
                task=task,
                source_root=workspace,
                evidence_root=session_root,
                meter=meter,
                current_plan=workflow.plan,
                handoff=handoff_for_agent(state["handoff"], session_root),
            )
            workflow.apply_revision(handoff_id=state["handoff"]["handoff_id"], plan=revised, reason=reason)
            result["agent_revisions"].append({"revision": revised.revision, "reason": reason, "plan_sha256": revised.fingerprint()})
        result.update(status=state["status"], session_id=session.session_id)
    except Exception as exc:
        result.update(status="stopped", error_class=type(exc).__name__)
    finally:
        try:
            current = manager.load_session(session.session_id, session.thread_id)
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            result.update(cleanup=asdict(cleanup), session_status=current.status)
        except Exception as exc:
            result.update(cleanup={"succeeded": False}, cleanup_error_class=type(exc).__name__)
        finally:
            operations._services = original
            (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def execute_trial(*, protocol: dict, archive_path: Path, root: Path, model, meter: PlanAgentMeter) -> dict:
    task = PlanTask.model_validate(protocol["task"])
    source = root / "input-source"
    source.mkdir(exist_ok=False)
    result = {"identity": protocol["identity"], "kind": protocol["kind"], "status": "started", "cases": []}
    try:
        with tarfile.open(archive_path) as archive:
            archive.extractall(source, filter="data")
        plan, reason = propose_plan(model=model, task=task, source_root=source, meter=meter)
        meter.ledger.save("generated-plan.json", {"plan": plan.model_dump(mode="json"), "reason": reason})
        for name, selected in (("normal", plan), ("controlled-recovery", inject_controlled_target(plan))):
            case = run_case(name=name, plan=selected, archive_path=archive_path, root=root, task=task, model=model, meter=meter)
            result["cases"].append(case)
            if case["status"] != "verified" or not case["cleanup"]["succeeded"]:
                result["status"] = "stopped"
                break
        else:
            result["status"] = "completed"
    except Exception as exc:
        result.update(status="stopped", error_class=type(exc).__name__)
    finally:
        result["agent_usage"] = meter.summary()
        (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = validate_inputs(args.protocol, args.source_archive, args.authorization)
    if args.validate_only:
        print(json.dumps({"identity": protocol["identity"], "valid": True, "provider_calls": 0}))
        return 0
    if args.authorization is None or args.output_root is None:
        parser.error("真实运行需要 --authorization 与全新 --output-root")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes(args.authorization.read_bytes())
    ledger = PlanAgentLedger(root / "agent")
    meter = PlanAgentMeter(ledger, accepted_models=tuple(protocol["provider"]["accepted_response_models"]))
    # 此前所有输入与授权均已核对；只有此处读取凭据，绝不输出凭据或客户端对象。
    from deerflow.models.patched_deepseek import PatchedChatDeepSeek

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        ledger.append("trial.preflight_failed", error_class="MissingCredential")
        (root / "result.json").write_text(json.dumps({"status": "stopped", "error_class": "MissingCredential", "agent_usage": meter.summary()}) + "\n")
        return 1
    model = PatchedChatDeepSeek(model="deepseek-v4-pro", api_key=api_key, base_url="https://api.deepseek.com", max_tokens=8192, max_retries=0, timeout=120, extra_body={"thinking": {"type": "enabled"}})
    result = execute_trial(protocol=protocol, archive_path=args.source_archive, root=root, model=model, meter=meter)
    print(json.dumps({"status": result["status"], "agent_usage": result["agent_usage"]}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
