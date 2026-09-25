#!/usr/bin/env python3
"""执行 Issue #303 授权的 Phase 5 v3 独立评测。"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_phase5_v2_authorized_runner as base  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v3_authorized_protocol as protocol  # noqa: E402

from deerflow.compile.evidence_ownership import normalize_evidence_tree  # noqa: E402
from deerflow.compile.external_evaluator_v3 import (  # noqa: E402
    EXTERNAL_EVALUATOR_RULES_SHA256,
    EXTERNAL_EVALUATOR_VERSION,
    ForgeCompileEvaluationBackend,
    run_external_evaluator_v3,
)

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path(protocol.EVIDENCE_DIRECTORY)

_ORIGINAL_PROTOCOL = base.protocol
_ORIGINAL_EVALUATOR = base.run_external_evaluator_v2
_ORIGINAL_BACKEND = base.ForgeCompileEvaluationBackend
_ORIGINAL_WRITE_ONCE = base._write_once
_ORIGINAL_SUMMARIZE = base._summarize
_ORIGINAL_EXPERIMENT_POLICY = base._experiment_policy
_ORIGINAL_ORACLE_SPEC = base._oracle_spec
_ORIGINAL_PREPARE_SESSION = base.prepare_compile_session_impl
_RUNTIME_BINDING_LOCK = threading.Lock()

_SCHEMA_RENAMES = {
    "forge-agent-workflow-stage-b-phase5-v2-attempt-1.0.0": "forge-agent-workflow-stage-b-phase5-v3-attempt-1.0.0",
    "forge-agent-workflow-stage-b-phase5-v2-reachability-1.0.0": "forge-agent-workflow-stage-b-phase5-v3-reachability-1.0.0",
    "forge-agent-workflow-stage-b-phase5-v2-task-result-1.0.0": "forge-agent-workflow-stage-b-phase5-v3-task-result-1.0.0",
    "forge-agent-workflow-stage-b-phase5-v2-report-1.0.0": "forge-agent-workflow-stage-b-phase5-v3-report-1.0.0",
}
_DOCUMENT_RENAMES = {
    "forge_agent_workflow_stage_b_phase5_v2_reachability": "forge_agent_workflow_stage_b_phase5_v3_reachability",
    "forge_agent_workflow_stage_b_phase5_v2_task_result": "forge_agent_workflow_stage_b_phase5_v3_task_result",
    "forge_agent_workflow_stage_b_phase5_v2_report": "forge_agent_workflow_stage_b_phase5_v3_report",
}


class Phase5V3AuthorizedRunnerError(RuntimeError):
    """Phase 5 v3 release、适配器或 evidence identity 无效。"""


def _write_once_v3(path: Path, value: dict[str, Any]) -> None:
    payload = copy.deepcopy(value)
    schema_version = payload.get("schema_version")
    document_type = payload.get("document_type")
    if schema_version in _SCHEMA_RENAMES:
        payload["schema_version"] = _SCHEMA_RENAMES[schema_version]
    if document_type in _DOCUMENT_RENAMES:
        payload["document_type"] = _DOCUMENT_RENAMES[document_type]
    _ORIGINAL_WRITE_ONCE(path, payload)


def _summarize_v3(
    manifest: dict[str, Any],
    revision: str,
    reachability: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    report = _ORIGINAL_SUMMARIZE(manifest, revision, reachability, outcomes)
    report.update(
        {
            "schema_version": "forge-agent-workflow-stage-b-phase5-v3-report-1.0.0",
            "document_type": "forge_agent_workflow_stage_b_phase5_v3_report",
            "evaluator_identity": copy.deepcopy(manifest["authorized_execution"]["evaluator"]),
            "independence": copy.deepcopy(manifest["authorized_execution"]["independence"]),
        }
    )
    return report


def _experiment_policy_v3(manifest: dict[str, Any], task: dict[str, Any]) -> Any:
    policy = _ORIGINAL_EXPERIMENT_POLICY(manifest, task)
    return replace(policy, benchmark_id="forge-agent-workflow-stage-b-phase5-v3-authorized-v1")


def _oracle_spec_v3(task: dict[str, Any]) -> Any:
    spec = _ORIGINAL_ORACLE_SPEC(task)
    return replace(spec, argv=tuple(item.replace("phase5-v2", "phase5-v3") for item in spec.argv))


def _prepare_session_v3(**kwargs: Any) -> Any:
    adapted = dict(kwargs)
    run_id = adapted.get("run_id")
    description = adapted.get("task_description")
    if isinstance(run_id, str):
        adapted["run_id"] = run_id.replace("phase5-v2-", "phase5-v3-", 1)
    if isinstance(description, str):
        adapted["task_description"] = description.replace("Phase 5 v2", "Phase 5 v3 independent evaluation", 1)
    return _ORIGINAL_PREPARE_SESSION(**adapted)


@contextmanager
def _runtime_binding() -> Iterator[None]:
    """在单进程串行执行期间绑定新 identity，并始终恢复父模块。"""

    if not _RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise Phase5V3AuthorizedRunnerError("Phase 5 v3 runtime binding 只允许单进程串行执行")
    originals = (
        base.protocol,
        base.run_external_evaluator_v2,
        base.ForgeCompileEvaluationBackend,
        base._write_once,
        base._summarize,
        base._experiment_policy,
        base._oracle_spec,
        base.prepare_compile_session_impl,
    )
    try:
        expected = (
            _ORIGINAL_PROTOCOL,
            _ORIGINAL_EVALUATOR,
            _ORIGINAL_BACKEND,
            _ORIGINAL_WRITE_ONCE,
            _ORIGINAL_SUMMARIZE,
            _ORIGINAL_EXPERIMENT_POLICY,
            _ORIGINAL_ORACLE_SPEC,
            _ORIGINAL_PREPARE_SESSION,
        )
        if any(actual is not original for actual, original in zip(originals, expected, strict=True)):
            raise Phase5V3AuthorizedRunnerError("Phase 5 v2 父 runner binding 已被其他 identity 修改")
        base.protocol = protocol
        base.run_external_evaluator_v2 = run_external_evaluator_v3
        base.ForgeCompileEvaluationBackend = ForgeCompileEvaluationBackend
        base._write_once = _write_once_v3
        base._summarize = _summarize_v3
        base._experiment_policy = _experiment_policy_v3
        base._oracle_spec = _oracle_spec_v3
        base.prepare_compile_session_impl = _prepare_session_v3
        try:
            yield
        finally:
            (
                base.protocol,
                base.run_external_evaluator_v2,
                base.ForgeCompileEvaluationBackend,
                base._write_once,
                base._summarize,
                base._experiment_policy,
                base._oracle_spec,
                base.prepare_compile_session_impl,
            ) = originals
    finally:
        _RUNTIME_BINDING_LOCK.release()


def _normalize_output_tree(output_dir: Path) -> bool:
    return normalize_evidence_tree(output_dir) if output_dir.exists() else False


def _normalize_without_masking_active_error(output_dir: Path) -> None:
    active_error = sys.exception()
    try:
        _normalize_output_tree(output_dir)
    except Exception as exc:
        if active_error is None:
            raise
        active_error.add_note(f"Phase 5 v3 evidence ownership 规范化同时失败: {type(exc).__name__}: {exc}")


def validate_runtime(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    evaluator = manifest["authorized_execution"]["evaluator"]
    if evaluator["version"] != EXTERNAL_EVALUATOR_VERSION or evaluator["rules_sha256"] != EXTERNAL_EVALUATOR_RULES_SHA256 or protocol.candidate.file_sha256(repo_root / evaluator["path"]) != evaluator["file_sha256"]:
        raise Phase5V3AuthorizedRunnerError("external evaluator v3 runtime identity 发生漂移")
    return {
        "status": "valid",
        "manifest_sha256": protocol.candidate.canonical_sha256(manifest),
        "parent_manifest_sha256": protocol.PARENT_MANIFEST_CANONICAL_SHA256,
        "evaluator_version": EXTERNAL_EVALUATOR_VERSION,
        "evaluator_rules_sha256": EXTERNAL_EVALUATOR_RULES_SHA256,
        "evidence_directory": manifest["evidence_candidate"]["directory"],
        "task_count": len(manifest["tasks"]),
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    with _runtime_binding():
        return base.collect_preflight(manifest, output_dir=output_dir, repo_root=repo_root, require_empty=require_empty)


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    try:
        with _runtime_binding():
            return base.execute_reachability(
                manifest,
                output_dir=output_dir,
                repo_root=repo_root,
                model_factory=model_factory,
            )
    finally:
        _normalize_without_masking_active_error(output_dir)


def run_batch(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    task_executor: Any | None = None,
) -> dict[str, Any]:
    validate_runtime(manifest, repo_root)
    kwargs: dict[str, Any] = {"output_dir": output_dir, "repo_root": repo_root}
    if task_executor is not None:
        kwargs["task_executor"] = task_executor
    try:
        with _runtime_binding():
            return base.run_batch(manifest, **kwargs)
    finally:
        _normalize_without_masking_active_error(output_dir)


def load_report(manifest: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    report = base._load_json(output_dir / manifest["authorized_execution"]["batch_report"])
    if (
        report.get("manifest_sha256") != protocol.candidate.canonical_sha256(manifest)
        or report.get("schema_version") != "forge-agent-workflow-stage-b-phase5-v3-report-1.0.0"
        or report.get("document_type") != "forge_agent_workflow_stage_b_phase5_v3_report"
        or report.get("evaluator_identity") != manifest["authorized_execution"]["evaluator"]
        or report.get("independence") != manifest["authorized_execution"]["independence"]
    ):
        raise Phase5V3AuthorizedRunnerError("Phase 5 v3 report identity 发生漂移")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "preflight", "reachability", "batch", "report"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        result: Any = validate_runtime(manifest)
    elif args.command == "preflight":
        result = collect_preflight(manifest, output_dir=args.output_dir, require_empty=not args.output_dir.exists())
    elif args.command == "reachability":
        result = execute_reachability(manifest, output_dir=args.output_dir)
    elif args.command == "batch":
        result = run_batch(manifest, output_dir=args.output_dir)
    else:
        result = load_report(manifest, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
