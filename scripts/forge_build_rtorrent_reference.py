#!/usr/bin/env python3
"""固定rtorrent独立参考；使用现有严格交付/replay与显式原测试CLI绑定。"""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend/packages/harness")]
from forge_build_plan_agent_canary import unchanged as protected_unchanged  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig  # noqa: E402
from deerflow.compile.generated_file_boundary import FileBoundary, guard_plan  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanBudget, PlanWorkflow  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402

IDENTITY = "cpp-build-rtorrent-reference-v1"


def validate(spec):
    if spec["identity"] != IDENTITY or spec["provider_calls"] != 0 or spec["credentials_read"] is not False:
        raise ValueError("参考身份/零Provider边界不符")
    parent = Path(spec["parent_raw"])
    if audit(parent)["inventory_canonical_sha256"] != spec["parent_inventory_sha256"]:
        raise ValueError("准备父证据变化")
    plan = BuildPlan.model_validate(spec["plan"])
    boundary = FileBoundary.model_validate(spec["file_boundary"])
    if plan.commit_sha != "d316b21cf02ae923d0cb1b6e75064a05016238bd" or plan.artifact_paths != ("rtorrent", "libtorrent.so.53"):
        raise ValueError("主源码或精确交付变化")
    if boundary.baseline != json.loads((parent / "original-source-hashes.json").read_text()) or digest(parent / "source.tar") != plan.source_archive_sha256:
        raise ValueError("两原源码身份变化")
    for name, expected in spec["components"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("冻结组件变化:" + name)
    return plan, boundary


def run(spec, root, plan, boundary):
    folder = root / "reference"
    folder.mkdir()
    paths = Paths(base_dir=folder / "data", workspace_root=folder, host_workspace_root=str(folder))
    manager = CompileSessionManager(paths=paths, default_image=plan.image_id, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=plan.image_id, parallel_jobs=2, network="none", replay_timeout_seconds=spec["replay_timeout_seconds"]))
    session = manager.create_session("rtorrent-reference", plan.repository_url, image=plan.image_id)
    old = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    source = Path(session.leadagent_repo_dir)
    result = {"identity": IDENTITY, "qualified": False, "provider_calls": 0, "session_id": session.session_id, "status": "started", "tests": "not_observed", "replay": "not_observed"}
    try:
        source.mkdir(parents=True, exist_ok=True)
        archive = Path(spec["parent_raw"]) / "source.tar"
        with tarfile.open(archive) as handle:
            handle.extractall(source, filter="data")
        protected_unchanged(source, boundary.baseline)
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
        workflow = PlanWorkflow(plan=guard_plan(boundary, plan), session=session, manager=manager, runtime=runtime, budget=PlanBudget(**spec["plan_budget"]))
        state = workflow.run()
        result["workflow"] = state
        result["status"] = state["status"]
        if state["status"] == "ready_for_verification":
            recipe = workflow.replay_recipe()
            current = manager.load_session(session.session_id, session.thread_id)
            artifacts = Path(current.metadata_path).parent / "artifacts"
            if {p.name for p in artifacts.iterdir()} != set(plan.artifact_paths):
                raise ValueError("精确交付集合不符")
            record = next(r for r in current.commands if r.command_id == workflow.completed["full-author-tests"])
            output = Path(record.log_path).read_text()
            if "FORGE_RTORRENT_FULL_TESTS=" not in output or record.exit_code != 0:
                raise ValueError("全部作者测试缺失")
            evidence = operations.SuccessfulCommandVerification(
                command_id=record.command_id, command=record.command, workdir=record.workdir, exit_code=record.exit_code, output=output, output_sha256=hashlib.sha256(output.encode()).hexdigest()
            )
            policy = operations.ExecutableVerificationPolicy.successful_commands({"rtorrent": evidence})
            result["tests"] = "passed"
            result["submission"] = operations.submit_build_result_impl(
                session=current,
                supporting_command_id=recipe.supporting_command_id,
                recipe_command_ids=[s.command_id for s in recipe.steps],
                verification_command_ids=[s.command_id for s in recipe.verification_steps],
                executable_verification_policy=policy,
            )
            current = manager.load_session(session.session_id, session.thread_id)
            result.update(status=current.status, replay=current.replay_attempts[-1].status if current.replay_attempts else "not_observed")
        protected_unchanged(source, boundary.baseline)
        result["author_files_unchanged"] = True
    except Exception as exc:
        result.update(status="stopped", error_class=type(exc).__name__, error=str(exc)[:1000])
    finally:
        try:
            current = manager.load_session(session.session_id, session.thread_id)
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            result.update(cleanup=asdict(cleanup), session_status=current.status)
            protected_unchanged(source, boundary.baseline)
            result["author_files_unchanged"] = True
        except Exception as exc:
            result.update(cleanup={"succeeded": False}, cleanup_error_class=type(exc).__name__)
        operations._services = old
        result["qualified"] = result["status"] == "verified" and result.get("session_status") == "completed" and result.get("replay") == "passed" and result.get("author_files_unchanged", False) and result["cleanup"]["succeeded"]
        write_json(folder / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    spec = json.loads(args.protocol.read_text())
    plan, boundary = validate(spec)
    before_deadline(spec["deadline_utc"], spec["reserve_seconds"])
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", spec)
    write_json(root / "execution.json", {"release": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "provider_calls": 0, "model_cost_usd": 0})
    result = {"qualified": False, "status": "not_observed"}
    try:
        result = run(spec, root, plan, boundary)
    finally:
        write_json(root / "result.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        print(json.dumps(seal(root, spec, ROOT)), flush=True)
    return 0 if result["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
