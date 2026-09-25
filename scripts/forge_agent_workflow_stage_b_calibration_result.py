#!/usr/bin/env python3
"""从 Phase 5 append-only evidence 生成只读停止结果审计。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_agent_workflow_stage_b_calibration_authorized_protocol as protocol  # noqa: E402

SCHEMA_VERSION = "forge-agent-workflow-stage-b-calibration-result-1.0.0"
DOCUMENT_TYPE = "forge_agent_workflow_stage_b_calibration_result"
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_SESSIONS_ROOT = REPO_ROOT / ".compile-sessions"
DEFAULT_EVIDENCE_DIR = DEFAULT_SESSIONS_ROOT / Path(protocol.candidate.EVIDENCE_DIRECTORY).name
DEFAULT_JSON_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-agent-workflow-stage-b-calibration-failed.json"
DEFAULT_MARKDOWN_REPORT = REPO_ROOT / "benchmarks" / "reports" / "cpp-agent-workflow-stage-b-calibration-failed.md"


class Phase5ResultAuditError(RuntimeError):
    """Phase 5 停止结果与冻结 identity 或 append-only evidence 不一致。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5ResultAuditError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise Phase5ResultAuditError(f"JSON 根节点必须是对象: {path}")
    return value


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise Phase5ResultAuditError(f"evidence 路径越出冻结根: {path}") from exc


def _reference(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": _relative(path, root),
        "sha256": protocol.candidate.file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _require_identity(value: dict[str, Any], *, digest: str, revision: str, label: str) -> None:
    if value.get("manifest_sha256") != digest or value.get("release_revision") != revision:
        raise Phase5ResultAuditError(f"{label} identity 发生漂移")


def _run_checked(command: Sequence[str], failure: str) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise Phase5ResultAuditError(failure)
    return result.stdout.strip()


def collect_managed_resources() -> dict[str, Any]:
    names = [name for name in _run_checked(["docker", "ps", "-a", "--format", "{{.Names}}"], "无法核验受管容器").splitlines() if name.startswith(("deerflow-compile-", "deerflow-replay-"))]
    paused = _run_checked(
        ["docker", "ps", "-q", "--filter", "status=paused", "--filter", "label=deerflow.compile.managed=true"],
        "无法核验 paused parent",
    ).splitlines()
    images = _run_checked(
        ["docker", "images", "-q", "--filter", "label=deerflow.compile.managed=true"],
        "无法核验受管镜像",
    ).splitlines()
    return {
        "managed_containers": sorted(names),
        "managed_images": sorted(images),
        "paused_parents": sorted(paused),
        "zero_managed_resources": not names and not paused and not images,
    }


def _stopped_session(manifest: dict[str, Any], sessions_root: Path, task_id: str, digest: str) -> tuple[Path, dict[str, Any]]:
    thread_root = sessions_root / f"phase5-{task_id}-{digest[:12]}"
    matches = sorted(thread_root.glob("*/session.json"))
    if len(matches) != 1:
        raise Phase5ResultAuditError(f"{task_id} 必须恰有一个 Compile Session")
    path = matches[0]
    session = _load_json(path)
    task = next(item for item in manifest["tasks"] if item["task_id"] == task_id)
    if session.get("repo_url") != task["repository_url"] or session.get("commit_sha") != task["commit_sha"]:
        raise Phase5ResultAuditError(f"{task_id} Session repository identity 发生漂移")
    if session.get("status") != "failed" or not session.get("finalized_at"):
        raise Phase5ResultAuditError(f"{task_id} Session 未形成清理后的失败终态")
    observed = session.get("build_system")
    if observed == task["build_system"] or not isinstance(observed, str):
        raise Phase5ResultAuditError(f"{task_id} 未形成可审计 build-system identity drift")
    return path, session


def build_report(
    manifest: dict[str, Any],
    evidence_dir: Path,
    sessions_root: Path,
    *,
    resource_probe: Callable[[], dict[str, Any]] = collect_managed_resources,
) -> dict[str, Any]:
    digest = protocol.candidate.canonical_sha256(manifest)
    order = manifest["schedule"]["order"]
    reachability = manifest["authorized_execution"]["reachability"]
    reachability_marker_path = evidence_dir / reachability["marker"]
    reachability_report_path = evidence_dir / reachability["report"]
    batch_marker_path = evidence_dir / manifest["authorized_execution"]["batch_marker"]
    reachability_marker = _load_json(reachability_marker_path)
    reachability_report = _load_json(reachability_report_path)
    batch_marker = _load_json(batch_marker_path)
    revision = batch_marker.get("release_revision")
    if not isinstance(revision, str):
        raise Phase5ResultAuditError("batch marker 缺少 release revision")
    for label, value in (("reachability marker", reachability_marker), ("reachability report", reachability_report), ("batch marker", batch_marker)):
        _require_identity(value, digest=digest, revision=revision, label=label)
    if reachability_marker.get("status") != "passed" or reachability_report.get("passed") is not True or reachability_report.get("request_count") != 1:
        raise Phase5ResultAuditError("唯一 reachability 未形成通过终态")
    if batch_marker.get("status") != "failed" or batch_marker.get("error_class") != "Phase5AuthorizedRunnerError":
        raise Phase5ResultAuditError("batch 未形成预期失败终态")
    for relative in (manifest["authorized_execution"]["batch_report"], manifest["authorized_execution"]["stage_c_decision_package"]):
        if (evidence_dir / relative).exists():
            raise Phase5ResultAuditError(f"停止 batch 不得存在 {relative}")

    outcomes: list[dict[str, Any]] = []
    evidence_references = [_reference(reachability_marker_path, evidence_dir), _reference(reachability_report_path, evidence_dir), _reference(batch_marker_path, evidence_dir)]
    stop_index: int | None = None
    stop_marker: dict[str, Any] | None = None
    for index, task_id in enumerate(order):
        marker_path = evidence_dir / "tasks" / task_id / "attempt.json"
        result_path = evidence_dir / "tasks" / task_id / "result.json"
        if result_path.exists():
            if stop_index is not None or not marker_path.is_file():
                raise Phase5ResultAuditError("结果不是连续完成前缀")
            marker = _load_json(marker_path)
            result = _load_json(result_path)
            _require_identity(marker, digest=digest, revision=revision, label=f"{task_id} marker")
            _require_identity(result, digest=digest, revision=revision, label=f"{task_id} result")
            if marker.get("status") != "passed" or result.get("task_id") != task_id or result.get("cleanup_succeeded") is not True or result.get("zero_managed_resources") is not True:
                raise Phase5ResultAuditError(f"{task_id} 结果终态未闭合")
            outcomes.append(result)
            evidence_references.extend((_reference(marker_path, evidence_dir), _reference(result_path, evidence_dir)))
            continue
        if marker_path.exists():
            if stop_index is not None:
                raise Phase5ResultAuditError("batch 存在多个失败 attempt")
            marker = _load_json(marker_path)
            _require_identity(marker, digest=digest, revision=revision, label=f"{task_id} marker")
            if marker.get("status") != "failed" or marker.get("error_class") != "Phase5AuthorizedRunnerError":
                raise Phase5ResultAuditError(f"{task_id} 未形成预期停止 marker")
            stop_index = index
            stop_marker = marker
            evidence_references.append(_reference(marker_path, evidence_dir))
            continue
        if stop_index is None:
            raise Phase5ResultAuditError("batch 在失败 marker 前出现 evidence 缺口")
        task_dir = evidence_dir / "tasks" / task_id
        if task_dir.exists() and any(task_dir.iterdir()):
            raise Phase5ResultAuditError(f"停止点后的任务不得包含 evidence: {task_id}")
    if stop_index is None or stop_marker is None or len(outcomes) != stop_index:
        raise Phase5ResultAuditError("无法确定唯一连续停止点")

    stopped_task_id = order[stop_index]
    session_path, session = _stopped_session(manifest, sessions_root, stopped_task_id, digest)
    stopped_task = next(item for item in manifest["tasks"] if item["task_id"] == stopped_task_id)
    resources = resource_probe()
    if resources.get("zero_managed_resources") is not True:
        raise Phase5ResultAuditError("Phase 5 停止后仍存在受管资源")

    layer_names = ("S0", "S1", "S2", "S3", "S4", "S5")
    layer_passes = {name: sum(any(layer.get("layer") == name and layer.get("status") == "passed" for layer in result["s0_s5"]) for result in outcomes) for name in layer_names}
    task_reports: list[dict[str, Any]] = []
    for task_id in order:
        result = next((item for item in outcomes if item["task_id"] == task_id), None)
        if result is not None:
            task_reports.append(
                {
                    "task_id": task_id,
                    "attempt_status": "completed",
                    "candidate_generated": result["candidate_generated_observed"],
                    "candidate_submitted": result["candidate_submitted"],
                    "layers": [
                        {
                            "layer": layer["layer"],
                            "status": layer["status"],
                            "reason_codes": layer["reason_codes"],
                        }
                        for layer in result["s0_s5"]
                    ],
                    "strict_reproducible_build_success": result["strict_reproducible_build_success"],
                    "bitwise_reproducible": result["bitwise_reproducible"],
                    "recorded_tokens": result["recorded_tokens"],
                    "duration_ms": result["duration_ms"],
                    "session_status": result["session_status"],
                }
            )
        elif task_id == stopped_task_id:
            task_reports.append(
                {
                    "task_id": task_id,
                    "attempt_status": "stopped_before_model",
                    "error_class": stop_marker["error_class"],
                    "frozen_build_system": stopped_task["build_system"],
                    "observed_build_system": session["build_system"],
                    "exact_commit_checked_out": session["commit_sha"],
                    "recorded_tokens": 0,
                    "session_status": session["status"],
                    "session_finalized_at": session["finalized_at"],
                }
            )
        else:
            task_reports.append({"task_id": task_id, "attempt_status": "not_attempted", "recorded_tokens": 0})

    batch_tokens = sum(result["recorded_tokens"] for result in outcomes)
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "status": "stopped_on_pre_model_identity_drift",
        "manifest_sha256": digest,
        "release_revision": revision,
        "issue_url": manifest["issue_url"],
        "reachability": {
            "passed": True,
            "request_count": 1,
            "recorded_tokens": reachability_report["recorded_tokens"],
            "actual_model": reachability_report["actual_model"],
        },
        "batch": {
            "marker_status": batch_marker["status"],
            "error_class": batch_marker["error_class"],
            "completed_task_count": len(outcomes),
            "attempted_task_count": stop_index + 1,
            "authorized_task_count": len(order),
            "stopped_task_id": stopped_task_id,
            "unattempted_tasks": order[stop_index + 1 :],
            "original_batch_must_not_resume": True,
        },
        "summary": {
            "candidate_generated": sum(result["candidate_generated_observed"] is True for result in outcomes),
            "candidate_submitted": sum(result["candidate_submitted"] is True for result in outcomes),
            "strict_success": sum(result["strict_reproducible_build_success"] is True for result in outcomes),
            "bitwise_reproducible": sum(result["bitwise_reproducible"] is True for result in outcomes),
            "s0_s5_passed": layer_passes,
            "batch_recorded_tokens": batch_tokens,
            "reachability_recorded_tokens": reachability_report["recorded_tokens"],
            "total_recorded_tokens": batch_tokens + reachability_report["recorded_tokens"],
            "authorized_recorded_token_ceiling": manifest["authorization"]["model_tokens_authorized"],
        },
        "tasks": task_reports,
        "stop_audit": {
            "classification": "frozen_build_system_identity_mismatch",
            "model_invocation_reached": False,
            "frozen_build_system": stopped_task["build_system"],
            "observed_build_system": session["build_system"],
            "exact_commit": stopped_task["commit_sha"],
            "session_reference": {
                "path": _relative(session_path, sessions_root),
                "sha256": protocol.candidate.file_sha256(session_path),
                "size_bytes": session_path.stat().st_size,
            },
        },
        "resource_audit": resources,
        "stage_c": {
            "authorized": False,
            "decision_package_generated": False,
            "reason": "phase5_six_task_terminal_set_incomplete",
            "required_next_action": "review_stopped_phase5_and_preregister_new_identity",
        },
        "interpretation": {
            "descriptive_only": True,
            "unbiased_success_rate_claim_allowed": False,
            "historical_evidence_reused": False,
            "replacement_or_backfill_allowed": False,
        },
        "evidence_references": evidence_references,
        "observed_at": batch_marker["updated_at"],
    }


def render_markdown(report: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return "-" if value is None else str(value).lower()

    summary = report["summary"]
    batch = report["batch"]
    lines = [
        "# Forge 单 Agent Workflow Node Phase 5 停止结果审计",
        "",
        "> 本报告由只读分析器从冻结 manifest、append-only marker/result 和停止 Session 确定性生成。",
        "",
        "## 结论",
        "",
        f"- 唯一 reachability 通过：1 request / {summary['reachability_recorded_tokens']:,} recorded tokens。",
        f"- 完成 {batch['completed_task_count']}/{batch['authorized_task_count']} 个项目结果；第 {batch['attempted_task_count']} 个项目 `{batch['stopped_task_id']}` 在模型调用前因 build-system identity drift 停止。",
        f"- generated={summary['candidate_generated']}，submitted={summary['candidate_submitted']}，strict={summary['strict_success']}，bitwise={summary['bitwise_reproducible']}。",
        f"- batch 使用 {summary['batch_recorded_tokens']:,} tokens；含 reachability 共 {summary['total_recorded_tokens']:,}/{summary['authorized_recorded_token_ceiling']:,}。",
        "- batch marker 为 failed；未生成 batch report 或 Stage C 决策包，Stage C 保持阻断。",
        "",
        "## 项目结果",
        "",
        "| 项目 | Attempt | Generated | Submitted | S0-S5 passed | Strict | Bitwise | Tokens |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for task in report["tasks"]:
        layers = task.get("layers", [])
        passed = sum(layer.get("status") == "passed" for layer in layers)
        lines.append(
            f"| `{task['task_id']}` | {task['attempt_status']} | {cell(task.get('candidate_generated'))} | "
            f"{cell(task.get('candidate_submitted'))} | {passed if layers else '-'} | "
            f"{cell(task.get('strict_reproducible_build_success'))} | {cell(task.get('bitwise_reproducible'))} | {task['recorded_tokens']:,} |"
        )
    stop = report["stop_audit"]
    lines.extend(
        [
            "",
            "## 停止点",
            "",
            f"- `{batch['stopped_task_id']}` exact commit `{stop['exact_commit']}` 检出成功。",
            f"- manifest 冻结 `{stop['frozen_build_system']}`，Forge 探测器记录 `{stop['observed_build_system']}`；模型调用未开始。",
            f"- 未执行后续项目：{', '.join(f'`{name}`' for name in batch['unattempted_tasks'])}。",
            "- 停止后 0 managed compile/replay container、0 managed image、0 paused parent。",
            "",
            "## 解释边界",
            "",
            "- 结果仅用于工程校准和失败机制审计，不构成无偏成功率或模型排名。",
            "- 原 batch 不重跑、不 replacement、不 backfill；任何后续执行必须采用新 identity 和新预注册协议。",
            "- 新协议至少需要修正 c-ares build-system identity，并为服务型 executable 定义不会触发三个 600 秒通用 smoke 的验证合同。",
            "",
            "## 复算",
            "",
            "```bash",
            "python scripts/forge_agent_workflow_stage_b_calibration_result.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(report: dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    markdown_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--sessions-root", type=Path, default=DEFAULT_SESSIONS_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    args = parser.parse_args(argv)
    try:
        manifest = protocol.load_manifest(args.manifest)
        report = build_report(manifest, args.evidence_dir, args.sessions_root)
        write_reports(report, json_path=args.json_output, markdown_path=args.markdown_output)
    except (Phase5ResultAuditError, protocol.Phase5AuthorizedProtocolError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
