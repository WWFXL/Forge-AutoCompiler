#!/usr/bin/env python3
"""独立的零 Provider 方案执行入口；仅用于开发验证，不替换产品默认入口。"""

from __future__ import annotations

import argparse
import hashlib
import json
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
from deerflow.compile.plan_workflow import BuildPlan, PlanBudget, PlanWorkflow  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True, help="根目录即仓库根的 tar；SHA-256 必须已绑定在方案中")
    parser.add_argument("--output-root", type=Path, required=True, help="必须是尚不存在的独立输出目录")
    parser.add_argument("--repair-plan", type=Path, help="可选的一次脚本化修订，仅验证交接机制，不是真实Agent")
    parser.add_argument("--verify", action="store_true", help="接入既有产物验证和干净重建")
    args = parser.parse_args()
    subprocess.run(["bash", str(REPO_ROOT / "scripts" / "require-docker-runtime.sh")], check=True, timeout=30)
    plan = BuildPlan.model_validate_json(args.plan.read_text())
    archive_sha256 = hashlib.sha256(args.source_archive.read_bytes()).hexdigest()
    if plan.source_archive_sha256 != archive_sha256:
        raise ValueError("源码归档与方案不符")
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "scope.json").write_text(
        json.dumps(
            {
                "kind": "zero_provider_engineering_prototype",
                "plan_sha256": plan.fingerprint(),
                "source_archive_sha256": archive_sha256,
                "scripted_repair": args.repair_plan is not None,
                "strict_verifier_requested": args.verify,
                "provider_calls": 0,
                "cpu": 2,
                "plan_budget": PlanBudget().model_dump(),
                "replay_timeout_seconds": 180,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    paths = Paths(base_dir=root / "data", workspace_root=root, host_workspace_root=str(root))
    manager = CompileSessionManager(paths=paths, default_image=plan.image_id, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=plan.image_id, parallel_jobs=2, replay_timeout_seconds=180))
    session = manager.create_session("build-plan-prototype", plan.repository_url, image=plan.image_id)
    original_services = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    result: dict = {"status": "started", "provider_calls": 0, "runtime_agent_calls": 0}
    try:
        workspace = Path(session.leadagent_repo_dir)
        workspace.mkdir(parents=True, exist_ok=True)
        with tarfile.open(args.source_archive) as archive:
            archive.extractall(workspace, filter="data")
        repro = Path(session.leadagent_repro_dir)
        shutil.copyfile(args.source_archive, repro / "source.tar")
        session.commit_sha = plan.commit_sha
        session.image_id = plan.image_id
        session.replay_source_archive_sha256 = archive_sha256
        session.build_system = plan.build_system
        session.selected_build_system = plan.build_system
        try:
            runtime.create_container(session)
        finally:
            manager.save_session(session)
        session.status = "inspected"
        manager.save_session(session)
        runner = PlanWorkflow(plan=plan, session=session, manager=manager, runtime=runtime)
        initial = runner.run()
        result["initial"] = initial
        if initial["status"] == "needs_handoff" and args.repair_plan:
            updated = BuildPlan.model_validate_json(args.repair_plan.read_text())
            runner.apply_revision(handoff_id=initial["handoff"]["handoff_id"], plan=updated, reason="零Provider脚本化回复：验证修订与恢复")
            result["after_scripted_revision"] = runner.run()
        if runner.status == "ready_for_verification":
            recipe = runner.replay_recipe()
            result["recipe"] = asdict(recipe)
            if args.verify:
                runner.verify()
        result.update(status=runner.status, final=runner.snapshot(), session_id=session.session_id)
    except Exception as exc:
        result.update(status="error", error_type=type(exc).__name__, error=str(exc))
    finally:
        try:
            current = manager.load_session(session.session_id, session.thread_id)
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            result.update(cleanup=asdict(cleanup), session_status=current.status)
        except Exception as exc:
            result.update(cleanup={"succeeded": False}, cleanup_error=f"{type(exc).__name__}: {exc}", session_status="cleanup_failed")
        finally:
            (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            operations._services = original_services
    print(json.dumps({key: result[key] for key in ("status", "session_status", "cleanup")}, ensure_ascii=False))
    return 0 if result["status"] in {"ready_for_verification", "verified"} and result["cleanup"]["succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
