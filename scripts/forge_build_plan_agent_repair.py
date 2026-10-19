#!/usr/bin/env python3
"""用户授权的修复至完成试运行；独立attempt、累计预算、冻结失败与最终验收。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from dataclasses import asdict, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "packages" / "harness"))

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.plan_agent import PlanAgentLedger, PlanAgentMeter, PlanTask, trial_budget  # noqa: E402
from deerflow.compile.plan_agent_repair import propose_plan  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanAgentMeterV2, PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanBudget, PlanContractError, PlanWorkflow  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_frozen(root):
    rows = json.loads((root / "inventory.json").read_text())
    seal = json.loads((root / "seal.json").read_text())
    canonical = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if canonical != seal["inventory_canonical_sha256"]:
        raise PlanContractError("冻结inventory不匹配")
    for row in rows:
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root.resolve()) or path.stat().st_size != row["size"] or sha(path) != row["sha256"]:
            raise PlanContractError("冻结文件已变化")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != {r["path"] for r in rows} | {"seal.json", "inventory.json"}:
        raise PlanContractError("冻结证据文件集已变化")
    return seal


def remaining_budget(parents, response_bound=50_000):
    requests = tokens = unknown = steps = tools = 0
    for root in parents:
        seal = audit_frozen(root)
        usage = json.loads((root / "result.json").read_text())["agent_usage"]
        requests += usage["model_requests"]
        tokens += usage["recorded_tokens"]
        unknown += seal["unknown_usage_requests"]
        steps += usage["agent_steps"]
        tools += usage["tool_calls"]
    if not 1 <= response_bound <= 50_000:
        raise PlanContractError("不得扩大单响应Token上界")
    threshold = 200_000 - tokens - unknown * 50_000 - response_bound
    if requests >= 12 or threshold <= 0 or steps >= 36 or tools >= 24:
        raise PlanContractError("累计试运行预算已耗尽，不得再调用模型")
    return replace(trial_budget(), max_model_requests=12 - requests, max_recorded_tokens=threshold, max_recorded_tokens_per_response=response_bound, max_agent_steps=36 - steps, max_tool_calls=24 - tools)


def validate_inputs(protocol_path, archive_path, authorization_path, campaign_root):
    protocol = json.loads(protocol_path.read_text())
    if protocol["identity"] != "cpp-build-plan-agent-repair-v1" or protocol["max_estimated_cost_usd"] != 2:
        raise PlanContractError("修复试运行身份或费用上限不匹配")
    base = json.loads((REPO_ROOT / "benchmarks/manifests/cpp-build-plan-agent-trial-v1-candidate.json").read_text())
    provider = {key: value for key, value in protocol["provider"].items() if key != "reasoning_effort"}
    if protocol["task"] != base["task"] or provider != base["provider"] or protocol["provider"].get("reasoning_effort", "high") not in ("high", "low") or sha(archive_path) != protocol["task"]["source_archive_sha256"]:
        raise PlanContractError("不得变更模型、源码或固定验收")
    for name, digest in protocol["components"].items():
        path = (REPO_ROOT / name).resolve()
        if not path.is_relative_to(REPO_ROOT) or sha(path) != digest:
            raise PlanContractError("运行组件已偏离当前协议")
    parents = []
    for item in protocol["parents"]:
        root = Path(item["path"])
        audit_frozen(root)
        if sha(root / "seal.json") != item["seal_sha256"]:
            raise PlanContractError("父证据seal不匹配")
        parents.append(root)
    attempts = sorted(campaign_root.glob("attempt-*")) if campaign_root.exists() else []
    limits = remaining_budget(parents + attempts, protocol.get("max_recorded_tokens_per_response", 50_000))
    authorization = json.loads(authorization_path.read_text())
    if authorization != {"identity": protocol["identity"], "protocol_sha256": sha(protocol_path), "decision": "approve_repair_until_success", "max_estimated_cost_usd": 2}:
        raise PlanContractError("没有匹配的修复至完成授权")
    return protocol, limits, attempts


def seal_attempt(root, protocol, meter):
    for name, digest in protocol["components"].items():
        source = REPO_ROOT / name
        if sha(source) != digest:
            raise PlanContractError("执行过程中运行组件发生变化")
        target = root / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(source.read_bytes())
    rows = [{"path": p.relative_to(root).as_posix(), "size": p.stat().st_size, "sha256": sha(p)} for p in sorted(root.rglob("*")) if p.is_file()]
    canonical = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    usage = meter.summary()
    with (root / "inventory.json").open("x") as handle:
        handle.write(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    with (root / "seal.json").open("x") as handle:
        handle.write(
            json.dumps({"identity": protocol["identity"], "files": len(rows), "bytes": sum(row["size"] for row in rows), "inventory_canonical_sha256": canonical, "unknown_usage_requests": usage["unknown_usage_requests"]}, indent=2) + "\n"
        )
    audit_frozen(root)


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
    session = manager.create_session("plan-agent-repair", plan.repository_url, image=plan.image_id)
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
        result.update(status="stopped", error_class=type(exc).__name__, error_message=str(exc)[:1000] if isinstance(exc, PlanContractError) else None)
    finally:
        result["agent_usage"] = meter.summary()
        (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol, limits, attempts = validate_inputs(args.protocol, args.source_archive, args.authorization, args.output_root)
    if any(json.loads((path / "result.json").read_text())["status"] == "completed" for path in attempts):
        raise PlanContractError("本campaign已经成功，不得追加试运行")
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0, "remaining_limits": asdict(limits)}))
        return 0
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise PlanContractError("没有授权Provider凭据")
    root = args.output_root.resolve() / f"attempt-{len(attempts) + 1:03d}"
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes(args.authorization.read_bytes())
    (root / "admitted-budget.json").write_text(json.dumps(asdict(limits), indent=2) + "\n")
    ledger = PlanAgentLedger(root / "agent")
    meter = PlanAgentMeterV2(ledger, accepted_models=tuple(protocol["provider"]["accepted_response_models"]), budget=limits)
    model = PlanThinkingDeepSeek(
        model="deepseek-v4-pro",
        api_key=key,
        base_url="https://api.deepseek.com",
        max_tokens=8192,
        max_retries=0,
        timeout=120,
        reasoning_effort=protocol["provider"].get("reasoning_effort", "high"),
        extra_body={"thinking": {"type": "enabled"}},
    )
    result = execute_trial(protocol=protocol, archive_path=args.source_archive, root=root, model=model, meter=meter)
    seal_attempt(root, protocol, meter)
    print(json.dumps({"attempt": root.name, "status": result["status"], "agent_usage": result["agent_usage"]}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
