#!/usr/bin/env python3
"""只读审计 Phase 5 v2 唯一 batch，并生成紧凑的描述性结论。"""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_phase5_v2_authorized_protocol as protocol  # noqa: E402

from deerflow.compile.evidence_ownership import normalize_evidence_path  # noqa: E402

SCHEMA_VERSION = "forge-agent-workflow-stage-b-phase5-v2-result-audit-1.0.0"
DOCUMENT_TYPE = "forge_agent_workflow_stage_b_phase5_v2_result_audit"
MANIFEST_SHA256 = "aa1f9ec280cbbecf91b5e10a9724e9b2462aed8dccc44bfb906c5e3e1ef962ed"
RELEASE_REVISION = "5ed549ea92add2403a91512d3148f29686559d67"
SOURCE_REPORT_SHA256 = "4cab2400927ef2a557ab81e7deeba26d3ee5aad85e716ca56157516a865c4d6c"
SOURCE_DECISION_SHA256 = "7e8000f10b8c6026a5908b1b6634e4c8ccbf323762e369d3d47ae5c7b0045a5d"
SOURCE_BATCH_MARKER_SHA256 = "5bcb669a7744b1f546aecbef78f3969374dca9bcb2c7d9f1071b52f53ce9f968"
FROZEN_EVALUATOR_V2_SHA256 = "19044e161b321fe5afed8458c0138f1bcfbe41582af2d5f4efcdf6846c3d579b"
FROZEN_AUTHORIZED_RUNNER_SHA256 = "af3ec35814f566736ec6fae6d47567a9d10deb4e23034fc8cc24840a8ba13c48"
POST_BUILD_REJECTION = "The bounded post-build inspection budget is exhausted. Stage final outputs into /artifacts or submit the existing build."
POST_BUILD_REJECTION_SHA256 = "8b872d3ecea20be5053da15d0a6ddd17bbaf3ef9dbfc8241cef37c33435e916c"
DEFAULT_SESSIONS_ROOT = REPO_ROOT / ".compile-sessions"
DEFAULT_EVIDENCE_DIR = DEFAULT_SESSIONS_ROOT / "benchmark-evidence-agent-workflow-stage-b-phase5-v2-authorized"
DEFAULT_JSON_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-agent-workflow-stage-b-phase5-v2-audit.json"
DEFAULT_MARKDOWN_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-agent-workflow-stage-b-phase5-v2-audit.md"
EVALUATOR_INVALID_TASKS = frozenset(("openh264", "c-ares", "libass"))


class Phase5V2ResultAuditError(RuntimeError):
    """原始 Phase 5 v2 evidence 与已知 identity 或审计不变量不一致。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5V2ResultAuditError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise Phase5V2ResultAuditError(f"JSON 根节点必须是对象: {path}")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return _sha256_bytes(payload.encode("utf-8"))


def _reference(path: Path, root: Path) -> dict[str, Any]:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise Phase5V2ResultAuditError(f"evidence 路径越出根目录: {path}") from exc
    return {"path": relative, "sha256": _file_sha256(path), "size_bytes": path.stat().st_size}


def _require_file_sha256(path: Path, expected: str, label: str) -> None:
    if _file_sha256(path) != expected:
        raise Phase5V2ResultAuditError(f"{label} SHA-256 发生漂移")


def _local_session_path(recorded_path: str, sessions_root: Path) -> Path:
    recorded = PurePosixPath(recorded_path)
    prefix = PurePosixPath("/workspace/.compile-sessions")
    try:
        relative = recorded.relative_to(prefix)
    except ValueError as exc:
        raise Phase5V2ResultAuditError("Session metadata path 不在冻结容器 evidence 根") from exc
    local = sessions_root.joinpath(*relative.parts)
    resolved_root = sessions_root.resolve(strict=True)
    resolved = local.resolve(strict=True)
    if not resolved.is_relative_to(resolved_root):
        raise Phase5V2ResultAuditError("Session metadata path 越出本地 sessions 根")
    return resolved


def _layer(result: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [layer for layer in result.get("s0_s5", []) if layer.get("layer") == name]
    if len(matches) != 1:
        raise Phase5V2ResultAuditError(f"{result.get('task_id')} 缺少唯一 {name} 结果")
    return matches[0]


def _load_node_events(path: Path, result: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous = "0" * 64
    for sequence, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        event = json.loads(raw)
        if event.get("sequence") != sequence or event.get("previous_hash") != previous:
            raise Phase5V2ResultAuditError("uwebsockets node event hash chain 不连续")
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        digest = _canonical_sha256(unsigned)
        if event.get("event_hash") != digest:
            raise Phase5V2ResultAuditError("uwebsockets node event hash 无效")
        previous = digest
        events.append(event)
    if previous != result["node_result"]["evidence_head_sha256"]:
        raise Phase5V2ResultAuditError("uwebsockets node result 未绑定 event hash chain")
    return events


def _classify_reliable_success(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    if task_id != "cppitertools" or result.get("strict_reproducible_build_success") is not True or any(layer.get("status") != "passed" for layer in result.get("s0_s5", [])):
        raise Phase5V2ResultAuditError("cppitertools 不满足可靠成功不变量")
    return {
        "task_id": task_id,
        "audit_classification": "reliable_success",
        "raw_strict_success": True,
        "raw_bitwise_reproducible": result["bitwise_reproducible"],
        "reason": "all_s0_s5_layers_passed",
    }


def _classify_yyjson(result: dict[str, Any], session: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    s2 = _layer(result, "S2")
    declared = set(candidate.get("artifact_paths", []))
    delivered = {PurePosixPath(item["source_path"]).relative_to("/artifacts").as_posix() for item in session.get("artifacts", [])}
    if (
        result.get("candidate_submitted") is not True
        or s2.get("status") != "failed"
        or "candidate_artifact_set_mismatch" not in s2.get("reason_codes", [])
        or "libyyjson.a" not in declared
        or "lib/libyyjson.a" in declared
        or not {"libyyjson.a", "lib/libyyjson.a"}.issubset(delivered)
    ):
        raise Phase5V2ResultAuditError("yyjson 未形成预期的额外 compiled artifact 失败")
    return {
        "task_id": "yyjson",
        "audit_classification": "workflow_failure",
        "raw_strict_success": False,
        "raw_bitwise_reproducible": result["bitwise_reproducible"],
        "reason": "undeclared_compiled_artifact",
        "declared_artifact": "libyyjson.a",
        "undeclared_compiled_artifact": "lib/libyyjson.a",
    }


def _classify_uwebsockets(result: dict[str, Any], session: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    rejection = next(
        (
            event
            for event in events
            if event.get("event_type") == "candidate.submit_rejected" and event.get("payload", {}).get("candidate_id") == "probe-incomplete-1" and event.get("payload", {}).get("rejection_codes") == ["invalid_contract"]
        ),
        None,
    )
    successful_staging = [item.get("command", "") for item in session.get("commands", []) if item.get("role") == "artifact_stage" and item.get("exit_code") == 0]
    if (
        result.get("candidate_submitted") is not False
        or result.get("node_status") != "failed"
        or result.get("node_result", {}).get("primary_failure") != "node_failed"
        or rejection is None
        or "GraphRecursionError" not in {event.get("payload", {}).get("error_class") for event in events if event.get("event_type") == "node.failed"}
        or not any("HelloWorld" in command and "uSockets.a" in command for command in successful_staging)
    ):
        raise Phase5V2ResultAuditError("uwebsockets 未形成预期的 candidate/workflow 失败")
    return {
        "task_id": "uwebsockets",
        "audit_classification": "workflow_failure",
        "raw_strict_success": False,
        "raw_bitwise_reproducible": None,
        "reason": "invalid_candidate_contract_then_graph_recursion_limit",
        "rejected_candidate_id": "probe-incomplete-1",
    }


def _classify_evaluator_invalid(
    task_id: str,
    result: dict[str, Any],
    session: dict[str, Any],
    evaluation: dict[str, Any],
    stderr_path: Path,
) -> dict[str, Any]:
    s3 = _layer(result, "S3")
    command_evidence = next((item for item in s3.get("evidence", []) if item.get("kind") == "command"), None)
    if command_evidence is None:
        raise Phase5V2ResultAuditError(f"{task_id} S3 缺少 oracle command evidence")
    command = next((item for item in session.get("commands", []) if item.get("command_id") == command_evidence.get("identifier")), None)
    if (
        task_id not in EVALUATOR_INVALID_TASKS
        or result.get("candidate_submitted") is not True
        or s3.get("status") != "failed"
        or s3.get("reason_codes") != ["functional_oracle_failed"]
        or command_evidence.get("exit_code") != 126
        or command is None
        or command.get("termination") != "policy_rejected"
        or session.get("post_build_commands_remaining") != 0
        or evaluation.get("evaluator_version") != "forge-external-evaluator-1.1.0"
        or _file_sha256(stderr_path) != POST_BUILD_REJECTION_SHA256
        or stderr_path.read_text(encoding="utf-8").strip() != POST_BUILD_REJECTION
    ):
        raise Phase5V2ResultAuditError(f"{task_id} 不满足 evaluator 污染不变量")
    return {
        "task_id": task_id,
        "audit_classification": "invalid_due_to_evaluator_defect",
        "raw_strict_success": False,
        "raw_bitwise_reproducible": None,
        "reason": "system_oracle_inherited_agent_post_build_budget",
        "oracle_command_id": command["command_id"],
        "oracle_exit_code": 126,
        "oracle_stderr_sha256": POST_BUILD_REJECTION_SHA256,
    }


def _ownership_finding(evidence_dir: Path, task_order: list[str]) -> dict[str, Any]:
    affected: list[str] = []
    for task_id in task_order:
        path = evidence_dir / "tasks" / task_id / "experiment.jsonl"
        metadata = path.stat()
        if metadata.st_uid == 0 and metadata.st_gid == 0 and stat.S_IMODE(metadata.st_mode) == 0o600:
            affected.append(path.relative_to(evidence_dir).as_posix())
    return {
        "root_owned_private_ledger_count": len(affected),
        "root_owned_private_ledgers": affected,
        "historical_evidence_modified": False,
        "fix_scope": "future_evidence_only",
    }


def build_report(
    *,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    sessions_root: Path = DEFAULT_SESSIONS_ROOT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    manifest = protocol.load_manifest(repo_root / protocol.MANIFEST_RELATIVE_PATH, repo_root)
    if protocol.candidate.canonical_sha256(manifest) != MANIFEST_SHA256:
        raise Phase5V2ResultAuditError("authorized manifest canonical SHA-256 发生漂移")
    frozen_files = {
        "external_evaluator_v2": (repo_root / "backend/packages/harness/deerflow/compile/external_evaluator_v2.py", FROZEN_EVALUATOR_V2_SHA256),
        "authorized_runner": (repo_root / protocol.RUNNER_PATH, FROZEN_AUTHORIZED_RUNNER_SHA256),
    }
    for label, (path, digest) in frozen_files.items():
        _require_file_sha256(path, digest, label)

    source_report_path = evidence_dir / manifest["authorized_execution"]["batch_report"]
    source_decision_path = evidence_dir / manifest["authorized_execution"]["stage_c_decision_package"]
    batch_marker_path = evidence_dir / manifest["authorized_execution"]["batch_marker"]
    _require_file_sha256(source_report_path, SOURCE_REPORT_SHA256, "Phase 5 v2 source report")
    _require_file_sha256(source_decision_path, SOURCE_DECISION_SHA256, "Phase 5 v2 Stage C decision")
    _require_file_sha256(batch_marker_path, SOURCE_BATCH_MARKER_SHA256, "Phase 5 v2 batch marker")
    source_report = _load_json(source_report_path)
    source_decision = _load_json(source_decision_path)
    batch_marker = _load_json(batch_marker_path)
    if (
        source_report.get("manifest_sha256") != MANIFEST_SHA256
        or source_report.get("release_revision") != RELEASE_REVISION
        or batch_marker.get("status") != "passed"
        or source_decision.get("phase5_complete") is not True
        or source_decision.get("stage_c_authorized") is not False
        or source_decision.get("report_sha256") != SOURCE_REPORT_SHA256
        or source_report.get("task_count") != 6
        or source_report.get("strict_success") != 1
    ):
        raise Phase5V2ResultAuditError("Phase 5 v2 source summary 或 Stage C 决策发生漂移")

    outcomes_by_id = {item["task_id"]: item for item in source_report["outcomes"]}
    audited_tasks: list[dict[str, Any]] = []
    references = [
        _reference(source_report_path, evidence_dir),
        _reference(source_decision_path, evidence_dir),
        _reference(batch_marker_path, evidence_dir),
    ]
    for task_id in source_report["task_order"]:
        result_path = evidence_dir / "tasks" / task_id / "result.json"
        result = _load_json(result_path)
        if result != outcomes_by_id.get(task_id):
            raise Phase5V2ResultAuditError(f"{task_id} task result 与 batch report 不一致")
        session_path = _local_session_path(result["session_metadata_path"], sessions_root)
        session = _load_json(session_path)
        attempt_dir = session_path.parent / "agent-workflow" / result["attempt_id"]
        references.append(_reference(result_path, evidence_dir))
        if task_id == "cppitertools":
            audited = _classify_reliable_success(task_id, result)
        elif task_id == "yyjson":
            audited = _classify_yyjson(result, session, _load_json(attempt_dir / "candidate.json"))
        elif task_id == "uwebsockets":
            audited = _classify_uwebsockets(result, session, _load_node_events(attempt_dir / "events.jsonl", result))
        else:
            evaluation_dir = attempt_dir / "evaluations" / f"phase5-v2-{task_id}-evaluation-v2"
            evaluation = _load_json(evaluation_dir / "result.json")
            if _canonical_sha256(evaluation) != result.get("evaluation_sha256"):
                raise Phase5V2ResultAuditError(f"{task_id} evaluation canonical SHA-256 发生漂移")
            audited = _classify_evaluator_invalid(task_id, result, session, evaluation, evaluation_dir / "oracle" / "stderr.log")
        audited_tasks.append(
            {
                **audited,
                "candidate_generated": result["candidate_generated_observed"],
                "candidate_submitted": result["candidate_submitted"],
                "recorded_tokens": result["recorded_tokens"],
            }
        )

    counts = {classification: sum(item["audit_classification"] == classification for item in audited_tasks) for classification in ("reliable_success", "workflow_failure", "invalid_due_to_evaluator_defect")}
    if counts != {"reliable_success": 1, "workflow_failure": 2, "invalid_due_to_evaluator_defect": 3}:
        raise Phase5V2ResultAuditError("Phase 5 v2 审计分类计数不满足 1/2/3")
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/299",
        "manifest_sha256": MANIFEST_SHA256,
        "release_revision": RELEASE_REVISION,
        "source_identity": {
            "report_sha256": SOURCE_REPORT_SHA256,
            "stage_c_decision_sha256": SOURCE_DECISION_SHA256,
            "batch_marker_sha256": SOURCE_BATCH_MARKER_SHA256,
            "external_evaluator_v2_sha256": FROZEN_EVALUATOR_V2_SHA256,
            "authorized_runner_sha256": FROZEN_AUTHORIZED_RUNNER_SHA256,
        },
        "raw_result": {
            "execution_completed": True,
            "batch_marker_status": "passed",
            "candidate_generated": source_report["candidate_generated"],
            "candidate_submitted": source_report["candidate_submitted"],
            "strict_success": source_report["strict_success"],
            "bitwise_reproducible": source_report["bitwise_reproducible"],
            "batch_recorded_tokens": source_report["batch_recorded_tokens"],
            "reachability_recorded_tokens": source_report["reachability_recorded_tokens"],
            "total_recorded_tokens": source_report["batch_recorded_tokens"] + source_report["reachability_recorded_tokens"],
        },
        "audit_result": {
            **counts,
            "unbiased_success_rate_claim_allowed": False,
            "evaluator_invalid_tasks_may_be_counted_as_success": False,
        },
        "tasks": audited_tasks,
        "stage_c": {
            "authorized": False,
            "current_batch_rerun_allowed": False,
            "retry_replacement_backfill_allowed": False,
            "required_next_action": "merge_evaluator_v3_fix_then_design_new_authorized_evaluation",
        },
        "evidence_ownership": _ownership_finding(evidence_dir, source_report["task_order"]),
        "source_references": references,
        "historical_evidence_mutated": False,
        "source_completed_at": source_report["completed_at"],
    }


def render_markdown(report: dict[str, Any]) -> str:
    raw = report["raw_result"]
    audit = report["audit_result"]
    raw_summary = (
        f"唯一 batch 已完成调度和报告生成。generated={raw['candidate_generated']}/6，submitted={raw['candidate_submitted']}/6，"
        f"strict={raw['strict_success']}/6，bitwise={raw['bitwise_reproducible']}/6；总 recorded tokens={raw['total_recorded_tokens']:,}。"
        "batch marker 的 `passed` 只表示执行闭合，不表示六项目严格通过。"
    )
    audit_summary = (
        f"可靠成功 {audit['reliable_success']} 项，明确工作流失败 {audit['workflow_failure']} 项，"
        f"evaluator 缺陷导致不可判定 {audit['invalid_due_to_evaluator_defect']} 项。"
        "该分类是事后审计，不能用于无偏成功率主张，也不能把不可判定项目追认为成功。"
    )
    evidence_summary = (
        f"原始报告 SHA-256：`{report['source_identity']['report_sha256']}`。"
        f"原始 decision SHA-256：`{report['source_identity']['stage_c_decision_sha256']}`。"
        f"历史 evidence 未修改。发现 {report['evidence_ownership']['root_owned_private_ledger_count']} 个 root:root/0600 ledger；修复只作用于未来 evidence。"
    )
    rows = [f"| `{item['task_id']}` | `{item['audit_classification']}` | {'是' if item['raw_strict_success'] else '否'} | {item['reason']} |" for item in report["tasks"]]
    return "\n".join(
        [
            "# Phase 5 v2 结果审计",
            "",
            f"源 release：`{report['release_revision']}`；manifest：`{report['manifest_sha256']}`。",
            "",
            "## 原始结果",
            "",
            raw_summary,
            "",
            "## 审计判定",
            "",
            audit_summary,
            "",
            "| 项目 | 审计分类 | 原始 strict | 依据 |",
            "|---|---|---:|---|",
            *rows,
            "",
            "## 决策",
            "",
            "Stage C 继续阻断。当前 batch 已全部消费，不允许重跑、retry、replacement 或 backfill。下一步是合并 evaluator v3 修复，再为新的独立评测设计授权 identity。",
            "",
            "## Evidence 完整性",
            "",
            evidence_summary,
            "",
        ]
    )


def _write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def compact_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "audited",
        "execution_completed": report["raw_result"]["execution_completed"],
        "raw_strict_success": report["raw_result"]["strict_success"],
        "reliable_success": report["audit_result"]["reliable_success"],
        "workflow_failure": report["audit_result"]["workflow_failure"],
        "evaluator_invalid": report["audit_result"]["invalid_due_to_evaluator_defect"],
        "stage_c_authorized": report["stage_c"]["authorized"],
        "current_batch_rerun_allowed": report["stage_c"]["current_batch_rerun_allowed"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate"))
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--sessions-root", type=Path, default=DEFAULT_SESSIONS_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    args = parser.parse_args(argv)
    actual = build_report(evidence_dir=args.evidence_dir, sessions_root=args.sessions_root)
    if args.command == "generate":
        _write_report(args.json_output, json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        _write_report(args.markdown_output, render_markdown(actual))
        normalize_evidence_path(args.json_output)
        normalize_evidence_path(args.markdown_output)
    else:
        if _load_json(args.json_output) != actual or args.markdown_output.read_text(encoding="utf-8") != render_markdown(actual):
            raise Phase5V2ResultAuditError("已提交审计报告与当前只读复算不一致")
    print(json.dumps(compact_summary(actual), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
