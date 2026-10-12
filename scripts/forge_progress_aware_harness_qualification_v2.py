#!/usr/bin/env python3
"""Issue #433：使用冻结源码归档的进展感知 Harness 零 Provider 门禁 v2。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_PATH.parent)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_progress_aware_harness_qualification_v1 as base  # noqa: E402

IDENTITY = "cpp-progress-aware-harness-qualification-v2"
TRACKING_ISSUE = 433
BRANCH = "yiwei/433-progress-aware-harness-qualification"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-progress-aware-harness-qualification-v2.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
SPEC_PATH = REPO_ROOT / "docs/superpowers/specs/2026-10-12-progress-aware-agent-harness-qualification-v2-design.md"
PLAN_PATH = REPO_ROOT / "docs/superpowers/plans/2026-10-12-progress-aware-agent-harness-qualification-v2.md"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
COMPONENT_PATHS = (
    "scripts/forge_progress_aware_harness_qualification_v1.py",
    "scripts/forge_progress_aware_harness_qualification_v2.py",
    "scripts/forge_agent_continuation_qualification_v2.py",
    "scripts/forge_checkpoint_archive.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v2.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v4.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "backend/packages/harness/deerflow/compile/external_evaluator.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v3.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "backend/tests/test_agent_workflow_runtime_v4.py",
    "backend/tests/test_forge_progress_aware_harness_qualification_v1.py",
    "backend/tests/test_forge_progress_aware_harness_qualification_v2.py",
    "benchmarks/schemas/forge-progress-aware-harness-qualification-v2.schema.json",
    "benchmarks/preregistrations/cpp-progress-aware-harness-qualification-v2.md",
    "docs/superpowers/specs/2026-10-12-progress-aware-agent-harness-qualification-v2-design.md",
    "docs/superpowers/plans/2026-10-12-progress-aware-agent-harness-qualification-v2.md",
)

_BASE_VALIDATE = base.validate_manifest
_BASE_PREFLIGHT = base.preflight
_BASE_QUALIFICATION = base._qualification


class ZeroProviderProgressModel(base.ZeroProviderProgressModel):
    @property
    def _llm_type(self) -> str:
        return "progress-aware-zero-provider-script-v2"


def _activate_base() -> None:
    base.IDENTITY = IDENTITY
    base.TRACKING_ISSUE = TRACKING_ISSUE
    base.BRANCH = BRANCH
    base.SCRIPT_PATH = SCRIPT_PATH
    base.MANIFEST_PATH = MANIFEST_PATH
    base.SCHEMA_PATH = SCHEMA_PATH
    base.PREREGISTRATION_PATH = PREREGISTRATION_PATH
    base.SPEC_PATH = SPEC_PATH
    base.PLAN_PATH = PLAN_PATH
    base.REPORT_JSON_PATH = REPORT_JSON_PATH
    base.REPORT_MD_PATH = REPORT_MD_PATH
    base.COMPONENT_PATHS = COMPONENT_PATHS
    base.ZeroProviderProgressModel = ZeroProviderProgressModel
    base.validate_manifest = validate_manifest
    base.preflight = preflight
    base._qualification = _qualification
    base._execute_gate = _execute_gate
    base.write_report = write_report


def _v1_inventory(manifest: dict[str, Any]) -> str:
    parent = manifest["remediation_parent"]
    root = REPO_ROOT / parent["evidence_root"]
    inventory = base._load_json(root / "inventory.json")
    expected = parent["inventory_canonical_sha256"]
    files = inventory.get("files")
    if not isinstance(files, list) or inventory.get("canonical_sha256") != expected or base._canonical_sha256(files) != expected:
        raise base.QualificationError("v1 remediation parent inventory 漂移")
    for item in files:
        path = root / item["path"]
        if not path.is_file() or path.stat().st_size != item["size"] or base._file_sha256(path) != item["sha256"]:
            raise base.QualificationError(f"v1 remediation parent 文件漂移: {item['path']}")
    result = base._load_json(root / "result.json")
    if result.get("qualification", {}).get("passed") is not False or result.get("layers", [])[-1:] != [{"layer": "S5", "status": "failed"}]:
        raise base.QualificationError("v1 remediation 前提漂移")
    return expected


def _source_archive(manifest: dict[str, Any]) -> Path:
    source = manifest["source_archive"]
    checkpoint, _message, _budget = base.parent_runner._checkpoint_payload(source["checkpoint_state_id"])
    task = manifest["task"]
    if (
        checkpoint["checkpoint_sha256"] != source["checkpoint_sha256"]
        or checkpoint["workspace_snapshot_sha256"] != source["sha256"]
        or checkpoint["source"]["repository_url"] != task["repository_url"]
        or checkpoint["source"]["commit_sha"] != task["commit_sha"]
    ):
        raise base.QualificationError("离线源码 checkpoint identity 漂移")
    path = REPO_ROOT / manifest["parent"]["evidence_root"] / "states" / source["checkpoint_state_id"] / "checkpoint/workspace.tar.gz"
    if not path.is_file() or base._file_sha256(path) != source["sha256"]:
        raise base.QualificationError("离线源码 archive 漂移")
    return path


def validate_manifest(manifest: dict[str, Any], *, require_components: bool = True) -> dict[str, Any]:
    _activate_base()
    _BASE_VALIDATE(manifest, require_components=require_components)
    if manifest["remediation_parent"] != {
        "identity": "cpp-progress-aware-harness-qualification-v1",
        "evidence_root": ".compile-sessions/benchmark-evidence-progress-aware-harness-qualification-v1",
        "inventory_canonical_sha256": "b45dd050963ecb033b15f246f62c4d0db4fa0b48c450e352d8d18ffc258024cd",
        "failure": "clean_replay_git_fetch_gnutls_handshake",
    }:
        raise base.QualificationError("v1 remediation parent identity 漂移")
    _v1_inventory(manifest)
    _source_archive(manifest)
    return manifest


def preflight(manifest: dict[str, Any], *, require_create_once: bool) -> dict[str, Any]:
    validate_manifest(manifest)
    result = _BASE_PREFLIGHT(manifest, require_create_once=require_create_once)
    result["remediation_parent_inventory_canonical_sha256"] = _v1_inventory(manifest)
    result["source_archive_sha256"] = base._file_sha256(_source_archive(manifest))
    return result


def _bind_source_archive(manifest: dict[str, Any], session: Any) -> str:
    source = _source_archive(manifest)
    destination = Path(session.leadagent_repro_dir) / "source.tar"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    observed = base._file_sha256(destination)
    if observed != manifest["source_archive"]["sha256"]:
        raise base.QualificationError("Session replay source archive 漂移")
    session.replay_source_archive_sha256 = observed
    base.get_compile_services().manager.save_session(session)
    return observed


def _node_input(
    manifest: dict[str, Any],
    session: Any,
    checkpoint: dict[str, Any],
    message: dict[str, Any],
    parent_budget: dict[str, Any],
    *,
    attempt_id: str,
) -> Any:
    original = base._node_input(
        manifest,
        session,
        checkpoint,
        message,
        parent_budget,
        attempt_id=attempt_id,
    )
    observation = dict(original.initial_observation)
    observation.update(
        {
            "harness": "progress-aware-runtime-v4-offline-replay-v2",
            "replay_source_archive_sha256": manifest["source_archive"]["sha256"],
        }
    )
    return replace(
        original,
        operation_policy_ref="issue-433-progress-aware-zero-provider-v2",
        initial_observation=observation,
    )


def _replay_observation(session: Any) -> dict[str, Any]:
    attempts = list(session.replay_attempts)
    checks = [check for attempt in attempts for check in attempt.checks]
    repro_script = Path(session.leadagent_repro_dir) / "build.sh"
    script = repro_script.read_text(encoding="utf-8") if repro_script.is_file() else ""
    return {
        "attempt_count": len(attempts),
        "source_snapshot_passed": any(check.name == "source_snapshot" and check.passed for check in checks),
        "git_fetch_present": "git fetch" in script,
        "source_archive_extract_present": "tar -xf" in script,
    }


async def _execute_gate(manifest: dict[str, Any], preflight_result: dict[str, Any], root: Path) -> dict[str, Any]:
    task = manifest["task"]
    attempt_id = "zero-provider-gate-v2"
    session = None
    cleanup_succeeded = False
    model = ZeroProviderProgressModel(task=task)
    started = time.monotonic()
    try:
        session, checkpoint, message, parent_budget = base.parent_runner._prepare_restored_session(
            manifest,
            task,
            task["checkpoint_state_id"],
            thread_id=f"issue-433-gate-v2-{uuid.uuid4().hex[:12]}",
            run_id=f"issue-433-gate-v2-{uuid.uuid4().hex}",
        )
        source_archive_sha256 = _bind_source_archive(manifest, session)
        node_input = _node_input(
            manifest,
            session,
            checkpoint,
            message,
            parent_budget,
            attempt_id=attempt_id,
        )
        oracle = base._oracle(task)
        node_result = await base.run_agent_workflow_node_v4(
            node_input=node_input,
            session=session,
            manager=base.get_compile_services().manager,
            model=model,
            oracle_registry={oracle.oracle_ref: oracle},
        )
        candidate_path = Path(session.metadata_path).parent / "agent-workflow" / attempt_id / "candidate.json"
        evaluation = base.run_external_evaluator_v4(
            node_input=node_input,
            node_result=node_result,
            session=session,
            manager=base.get_compile_services().manager,
            candidate_path=candidate_path,
            evaluation_id="issue-433-zero-provider-evaluation-v2",
            backend=base.ForgeCompileEvaluationBackend(oracle_registry={oracle.oracle_ref: oracle}),
        )
        current = base.get_compile_services().manager.load_session(session.session_id, session.thread_id)
        replay = _replay_observation(current)
        finalized, cleanup = base.cleanup_and_finalize_compile_session_impl(session=current)
        cleanup_succeeded = cleanup.succeeded
        managed = base._require_zero_managed_resources()
        workflow_dir = Path(finalized.metadata_path).parent / "agent-workflow" / attempt_id
        event_summary = base._event_summary(base._events(workflow_dir / "events.jsonl"))
        session_tree_sha256 = base._snapshot_session(finalized, root / "session-evidence")
        base._write_once_json(
            root / "model-observations.json",
            {
                "model_type": model._llm_type,
                "provider_requests": 0,
                "credential_reads": 0,
                "calls": model.calls,
                "progress_snapshots": model.observations,
            },
        )
        return {
            "identity": IDENTITY,
            "release_revision": preflight_result["release_revision"],
            "manifest_sha256": preflight_result["manifest_sha256"],
            "checkpoint_state_id": task["checkpoint_state_id"],
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "credential_reads": 0,
            "provider_requests": 0,
            "script_model_calls": model.calls,
            "node_status": node_result.node_status,
            "candidate_submitted": node_result.candidate_submitted,
            "usage": asdict(node_result.usage),
            "event_summary": event_summary,
            "strict_success": evaluation.strict_reproducible_build_success,
            "layers": [{"layer": layer.layer, "status": layer.status} for layer in evaluation.layers],
            "bitwise_reproducible": evaluation.bitwise_reproducible,
            "source_archive_sha256": source_archive_sha256,
            "replay": replay,
            "cleanup_succeeded": cleanup_succeeded,
            "session_status": finalized.status,
            "managed_containers_after_cleanup": managed,
            "parent_inventory_before": preflight_result["parent_inventory_canonical_sha256"],
            "parent_inventory_after": base._validate_parent_inventory(manifest),
            "remediation_parent_inventory_before": preflight_result["remediation_parent_inventory_canonical_sha256"],
            "remediation_parent_inventory_after": _v1_inventory(manifest),
            "session_tree_sha256": session_tree_sha256,
            "duration_milliseconds": round((time.monotonic() - started) * 1000),
            "completed_at": base._now(),
        }
    finally:
        if session is not None and not cleanup_succeeded:
            try:
                base.cleanup_and_finalize_compile_session_impl(
                    session=session,
                    interrupted_status="failed",
                    error="Issue #433 zero-provider v2 gate interrupted",
                )
                base._require_zero_managed_resources()
            except Exception:
                pass


def _qualification(result: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    qualification = _BASE_QUALIFICATION(result, manifest)
    replay = result.get("replay", {})
    qualification["gates"].update(
        {
            "offline_source_bound": (result.get("source_archive_sha256") == manifest["source_archive"]["sha256"]),
            "offline_source_snapshot": (replay.get("source_snapshot_passed") is True),
            "replay_network_independent": (replay.get("git_fetch_present") is False and replay.get("source_archive_extract_present") is True),
            "remediation_parent_unchanged": (result.get("remediation_parent_inventory_before") == result.get("remediation_parent_inventory_after") == manifest["remediation_parent"]["inventory_canonical_sha256"]),
        }
    )
    qualification["passed"] = all(qualification["gates"].values())
    qualification["decision"] = manifest["qualification"]["pass_decision"] if qualification["passed"] else manifest["qualification"]["fail_decision"]
    return qualification


def write_report(manifest: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT / manifest["evidence_root"]
    audited = base.audit(manifest)
    result = base._load_json(root / "result.json")
    report = {
        "schema_version": "1.0.0",
        "identity": IDENTITY,
        "status": audited["status"],
        "decision": audited["decision"],
        "passed": audited["passed"],
        "release_revision": result["release_revision"],
        "manifest_sha256": result["manifest_sha256"],
        "evidence_inventory_canonical_sha256": audited["inventory_canonical_sha256"],
        "provider_requests": 0,
        "credential_reads": 0,
        "checkpoint_state_id": result.get("checkpoint_state_id"),
        "source_archive_sha256": result.get("source_archive_sha256"),
        "replay": result.get("replay", {}),
        "strict_success": result.get("strict_success"),
        "layers": result.get("layers", []),
        "usage": result.get("usage", {}),
        "event_summary": result.get("event_summary", {}),
        "qualification": result["qualification"],
        "interpretation": {
            "engineering_gate_only": True,
            "harness_treatment_effect": False,
            "model_capability_claim": False,
            "provider_cost_claim": False,
            "v1_failure_reclassified": False,
        },
    }
    json_content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown = (
        f"# `{IDENTITY}` 结果\n\n"
        f"- 状态：`{report['status']}`；\n"
        f"- 决定：`{report['decision']}`；\n"
        f"- 严格成功：`{report['strict_success']}`；\n"
        f"- Provider 请求 / credential 读取：`0 / 0`；\n"
        f"- 离线源码 SHA-256：`{report['source_archive_sha256']}`；\n"
        f"- replay source snapshot / git fetch present："
        f"`{report['replay'].get('source_snapshot_passed')} / "
        f"{report['replay'].get('git_fetch_present')}`。\n\n"
        "## 结论边界\n\n"
        "该结果只证明 Runtime v4 的结构化 Harness 与离线 clean replay 在真实 "
        "Docker checkpoint 上闭合。它不估计 H1 相对 H0 的模型成功率、成本或"
        "动态预算效果；v1 的基础设施失败仍按原记录保留。\n"
    )
    base._write_if_equal_or_absent(REPORT_JSON_PATH, json_content)
    base._write_if_equal_or_absent(REPORT_MD_PATH, markdown)
    return report


def main() -> int:
    _activate_base()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "plan", "run", "audit", "report"))
    arguments = parser.parse_args()
    manifest = base._manifest()
    try:
        if arguments.command == "validate":
            result = validate_manifest(manifest)
            output: Any = {
                "valid": True,
                "identity": result["identity"],
                "manifest_sha256": base._canonical_sha256(result),
            }
        elif arguments.command == "plan":
            output = base.plan(manifest)
            output["offline_replay_source"] = manifest["source_archive"]
        elif arguments.command == "run":
            output = base.run(manifest)
        elif arguments.command == "audit":
            output = base.audit(manifest)
        else:
            output = write_report(manifest)
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        if arguments.command == "run":
            return 0 if output.get("qualification", {}).get("passed") else 1
        return 0
    except base.QualificationError as exc:
        print(
            json.dumps(
                {
                    "valid": False,
                    "error_class": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
