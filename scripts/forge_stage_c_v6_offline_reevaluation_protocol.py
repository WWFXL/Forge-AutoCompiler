#!/usr/bin/env python3
"""生成、校验并授权 Stage C v6 零 Provider 离线定向重评。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_stage_c_protocol as base  # noqa: E402
import forge_stage_c_task_qualification as qualification  # noqa: E402
import forge_stage_c_v6_measurement_remediation_protocol as candidate  # noqa: E402

SCHEMA_VERSION = "forge-stage-c-v6-offline-reevaluation-authorized-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_v6_offline_reevaluation_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/333"
AUTHORIZATION_BASELINE_COMMIT = "9fecc8d5cbf89bf11489a9724cc01782c6a83b68"
CANDIDATE_MANIFEST_SHA256 = "739201108b9389a30d1f2c620e124ba30f1232c764c315674e1122b524084698"
CANDIDATE_MANIFEST_PATH = candidate.MANIFEST_RELATIVE_PATH
SOURCE_RECEIPT_PATH = "benchmarks/reports/cpp-stage-c-v6-source-candidate-receipt.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-stage-c-v6-offline-reevaluation-authorized.md"
PROTOCOL_PATH = "scripts/forge_stage_c_v6_offline_reevaluation_protocol.py"
RUNNER_PATH = "scripts/forge_stage_c_v6_offline_reevaluation_runner.py"
MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-stage-c-v6-offline-reevaluation-authorized.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-stage-c-v6-offline-reevaluation-authorized.schema.json"
V5_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-stage-c-paired-calibration-v5-session-identity"
DEFAULT_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-stage-c-v6-measurement-remediation"
DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH

canonical_sha256 = base.canonical_sha256
file_sha256 = base.file_sha256


class StageCV6OfflineProtocolError(RuntimeError):
    """Stage C v6 离线重评身份、来源证据或授权边界无效。"""


def _require_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise StageCV6OfflineProtocolError(f"{label} 不存在或不是普通文件: {path}")
    return path


def _artifact_inventory(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise StageCV6OfflineProtocolError(f"artifact 目录无效: {root}")
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise StageCV6OfflineProtocolError(f"artifact 不得为符号链接: {path}")
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return {
        "file_count": len(files),
        "total_size_bytes": sum(item["size_bytes"] for item in files),
        "manifest_sha256": canonical_sha256(files),
    }


def _source_thread_id(pair_id: str) -> str:
    pair_digest = hashlib.sha256(pair_id.encode("utf-8")).hexdigest()
    return f"stage-c-b-{pair_digest}-{candidate.V5_MANIFEST_SHA256[:16]}"


def _read_events(path: Path) -> list[dict[str, Any]]:
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StageCV6OfflineProtocolError(f"事件 JSONL 第 {line_number} 行无效: {path}") from exc
        if not isinstance(value, dict):
            raise StageCV6OfflineProtocolError(f"事件必须为对象: {path}")
        events.append(value)
    if not events:
        raise StageCV6OfflineProtocolError(f"事件文件为空: {path}")
    return events


def _source_evaluation_result(workflow_dir: Path) -> tuple[str | None, dict[str, Any] | None]:
    paths = sorted(workflow_dir.glob("evaluations/*/result.json"))
    if len(paths) > 1:
        raise StageCV6OfflineProtocolError(f"原 evaluator result 不唯一: {workflow_dir}")
    if not paths:
        return None, None
    path = _require_file(paths[0], "原 evaluator result")
    return path.relative_to(workflow_dir.parent.parent).as_posix(), qualification.load_json(path)


def capture_source_receipt(
    *,
    repo_root: Path = REPO_ROOT,
    compile_sessions_root: Path = Path("/workspace/.compile-sessions"),
) -> dict[str, Any]:
    manifest = candidate.load_manifest(repo_root=repo_root)
    if canonical_sha256(manifest) != CANDIDATE_MANIFEST_SHA256:
        raise StageCV6OfflineProtocolError("Stage C v6 candidate identity 漂移")
    v5_root = compile_sessions_root / Path(V5_EVIDENCE_DIRECTORY).name
    if v5_root.is_symlink() or not v5_root.is_dir():
        raise StageCV6OfflineProtocolError("Stage C v5 evidence 目录不可读")

    entries = []
    for evaluation in manifest["schedule"]["evaluations"]:
        pair_id = evaluation["source_pair_id"]
        attempt_id = evaluation["source_attempt_id"]
        thread_id = _source_thread_id(pair_id)
        thread_root = compile_sessions_root / thread_id
        session_dirs = sorted(path for path in thread_root.iterdir() if path.is_dir())
        if len(session_dirs) != 1:
            raise StageCV6OfflineProtocolError(f"{pair_id} 来源 Session 数量不是 1")
        session_root = session_dirs[0]
        session_path = _require_file(session_root / "session.json", "来源 session")
        session = qualification.load_json(session_path)
        workflow_dir = session_root / "agent-workflow" / attempt_id
        input_path = _require_file(workflow_dir / "input.json", "来源 node input")
        candidate_path = _require_file(workflow_dir / "candidate.json", "来源 candidate")
        events_path = _require_file(workflow_dir / "events.jsonl", "来源事件链")
        arm_result_path = _require_file(v5_root / "pairs" / pair_id / "B" / "result.json", "来源 B 臂结果")
        node_input = qualification.load_json(input_path)
        frozen_candidate = qualification.load_json(candidate_path)
        arm_result = qualification.load_json(arm_result_path)
        events = _read_events(events_path)
        accepted = [event for event in events if event.get("event_type") == "candidate.submit_accepted"]
        terminal = events[-1]
        if (
            len(accepted) != 1
            or terminal.get("event_type") != "node.terminal"
            or arm_result.get("candidate_submitted") is not True
            or arm_result.get("pair_id") != pair_id
            or arm_result.get("attempt_id") != attempt_id
            or node_input.get("task_id") != evaluation["task_id"]
            or node_input.get("attempt_id") != attempt_id
            or node_input.get("session_id") != session.get("session_id")
            or session.get("thread_id") != thread_id
            or session.get("commit_sha") != node_input.get("commit_sha")
            or session.get("image_id") != manifest["environment"]["image_id"]
        ):
            raise StageCV6OfflineProtocolError(f"{pair_id} 来源语义不一致")
        accepted_payload = accepted[0].get("payload", {})
        candidate_sha256 = canonical_sha256(frozen_candidate)
        if accepted_payload.get("candidate_record_sha256") != candidate_sha256:
            raise StageCV6OfflineProtocolError(f"{pair_id} candidate identity 漂移")

        evaluator_relative, evaluator_result = _source_evaluation_result(workflow_dir)
        original_evaluator = None
        if evaluator_relative is not None and evaluator_result is not None:
            evaluator_path = session_root / evaluator_relative
            original_evaluator = {
                "path": evaluator_relative,
                "file_sha256": file_sha256(evaluator_path),
                "node_result_sha256": evaluator_result["node_result_sha256"],
                "strict_reproducible_build_success": evaluator_result["strict_reproducible_build_success"],
            }

        entries.append(
            {
                "evaluation_id": evaluation["evaluation_id"],
                "source_pair_id": pair_id,
                "source_attempt_id": attempt_id,
                "task_id": evaluation["task_id"],
                "replicate": evaluation["replicate"],
                "source_thread_id": thread_id,
                "source_session_id": session["session_id"],
                "source_session_relative_path": f"{thread_id}/{session['session_id']}",
                "source_session_file_sha256": file_sha256(session_path),
                "source_node_input_file_sha256": file_sha256(input_path),
                "source_node_input_sha256": canonical_sha256(node_input),
                "source_candidate_file_sha256": file_sha256(candidate_path),
                "source_candidate_record_sha256": candidate_sha256,
                "source_events_file_sha256": file_sha256(events_path),
                "source_event_count": len(events),
                "source_evidence_head_sha256": terminal["event_hash"],
                "submission_id": accepted_payload["submission_id"],
                "source_commands_sha256": canonical_sha256(session.get("commands", [])),
                "source_command_count": len(session.get("commands", [])),
                "source_artifacts": _artifact_inventory(session_root / "artifacts"),
                "source_arm_result_file_sha256": file_sha256(arm_result_path),
                "source_usage": {
                    "model_requests": arm_result["model_requests"],
                    "recorded_tokens": arm_result["recorded_tokens"],
                    "tool_calls": arm_result["tool_calls"],
                    "commands": arm_result["commands"],
                },
                "original_evaluator": original_evaluator,
            }
        )

    if len(entries) != 22 or len({entry["evaluation_id"] for entry in entries}) != 22:
        raise StageCV6OfflineProtocolError("来源收据必须覆盖 22 条唯一重评")
    return {
        "schema_version": "forge-stage-c-v6-source-candidate-receipt-1.0.0",
        "document_type": "forge_stage_c_v6_source_candidate_receipt",
        "source_v5_identity": {
            "manifest_sha256": candidate.V5_MANIFEST_SHA256,
            "release_revision": candidate.V5_RELEASE_REVISION,
            "evidence_directory": V5_EVIDENCE_DIRECTORY,
            "read_only": True,
        },
        "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "evaluation_count": len(entries),
        "excluded_no_candidate_pairs": manifest["schedule"]["excluded_no_candidate_pairs"],
        "entries": entries,
    }


def write_source_receipt(value: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_candidate(repo_root: Path) -> dict[str, Any]:
    value = candidate.load_manifest(repo_root=repo_root)
    if canonical_sha256(value) != CANDIDATE_MANIFEST_SHA256:
        raise StageCV6OfflineProtocolError("Stage C v6 candidate identity 漂移")
    return value


def _load_source_receipt(repo_root: Path) -> dict[str, Any]:
    path = repo_root / SOURCE_RECEIPT_PATH
    value = qualification.load_json(path)
    if (
        value.get("schema_version") != "forge-stage-c-v6-source-candidate-receipt-1.0.0"
        or value.get("candidate_manifest_sha256") != CANDIDATE_MANIFEST_SHA256
        or value.get("evaluation_count") != 22
        or len(value.get("entries", [])) != 22
        or len({entry.get("evaluation_id") for entry in value.get("entries", [])}) != 22
        or value.get("source_v5_identity", {}).get("read_only") is not True
    ):
        raise StageCV6OfflineProtocolError("Stage C v6 来源收据无效")
    return value


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent = _load_candidate(repo_root)
    receipt = _load_source_receipt(repo_root)
    preregistration = _require_file(repo_root / PREREGISTRATION_PATH, "Stage C v6 授权预注册")
    manifest = copy.deepcopy(parent)
    manifest["$schema"] = "../schemas/forge-stage-c-v6-offline-reevaluation-authorized.schema.json"
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["document_type"] = DOCUMENT_TYPE
    manifest["issue_url"] = ISSUE_URL
    manifest["purpose"] = "stage_c_v5_offline_measurement_remediation_reevaluation"
    manifest["status"] = "authorized_not_executed"
    manifest["authorization"] = {
        "offline_reevaluation_authorized": True,
        "credential_read_authorized": False,
        "provider_calls_authorized": False,
        "model_creation_authorized": False,
        "reachability_request_authorized": False,
        "docker_execution_authorized": True,
        "evidence_write_authorized": True,
        "formal_stage_c_attempts_authorized": True,
        "model_tokens_authorized": 0,
        "stage_c_execution_started": False,
    }
    manifest["execution"] = {
        "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
        "release_branch": "main",
        "release_revision_policy": ("descendant_of_authorization_baseline_and_record_each_evaluation"),
        "evidence_directory": DEFAULT_EVIDENCE_DIRECTORY,
        "source_v5_evidence_directory": V5_EVIDENCE_DIRECTORY,
        "source_v5_evidence_read_only": True,
        "source_receipt_path": SOURCE_RECEIPT_PATH,
        "source_receipt_file_sha256": file_sha256(repo_root / SOURCE_RECEIPT_PATH),
        "create_once": True,
        "resume_policy": "completed_contiguous_evaluation_prefix_only",
        "commands": ["validate", "preflight", "run", "report"],
        "execution_authorized": True,
        "network_policy": "exact_source_acquisition_then_replay_network_none",
        "batch_started_marker": "markers/batch-started.json",
        "batch_completed_marker": "markers/batch-completed.json",
        "result_path": "evaluations/{evaluation_id}/result.json",
        "result_report": "reports/stage-c-v6-result.json",
        "result_report_markdown": "reports/stage-c-v6-result.md",
        "inventory_report": "reports/stage-c-v6-inventory.json",
    }
    manifest["parent_candidate_identity"] = {
        "manifest_path": CANDIDATE_MANIFEST_PATH,
        "manifest_file_sha256": file_sha256(repo_root / CANDIDATE_MANIFEST_PATH),
        "manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "candidate_execution_authorized": False,
    }
    manifest["source_candidate_receipt"] = {
        "path": SOURCE_RECEIPT_PATH,
        "file_sha256": file_sha256(repo_root / SOURCE_RECEIPT_PATH),
        "canonical_sha256": canonical_sha256(receipt),
        "evaluation_count": receipt["evaluation_count"],
        "v5_evidence_read_only": True,
    }
    manifest["preregistration"] = {
        "path": PREREGISTRATION_PATH,
        "file_sha256": file_sha256(preregistration),
    }
    component_paths = (
        "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
        "backend/packages/harness/deerflow/compile/external_evaluator.py",
        "backend/packages/harness/deerflow/compile/external_evaluator_v3.py",
        "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
        "backend/packages/harness/deerflow/compile/manager.py",
        "backend/packages/harness/deerflow/compile/operations.py",
        "backend/packages/harness/deerflow/compile/schemas.py",
        "scripts/forge_stage_c_runner.py",
        candidate.PROTOCOL_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
        SOURCE_RECEIPT_PATH,
        PREREGISTRATION_PATH,
        CANDIDATE_MANIFEST_PATH,
    )
    manifest["frozen_components"] = {relative: file_sha256(repo_root / relative) for relative in component_paths}
    return manifest


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ("https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-v6-offline-reevaluation-authorized.schema.json"),
        "title": "Forge Stage C v6 offline reevaluation authorized",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise StageCV6OfflineProtocolError("Stage C v6 authorized manifest 与确定性结果不一致")
    authorization = value["authorization"]
    if (
        authorization.get("offline_reevaluation_authorized") is not True
        or authorization.get("docker_execution_authorized") is not True
        or authorization.get("evidence_write_authorized") is not True
        or authorization.get("formal_stage_c_attempts_authorized") is not True
        or authorization.get("model_tokens_authorized") != 0
        or authorization.get("stage_c_execution_started") is not False
        or any(
            authorization.get(field) is not False
            for field in (
                "credential_read_authorized",
                "provider_calls_authorized",
                "model_creation_authorized",
                "reachability_request_authorized",
            )
        )
    ):
        raise StageCV6OfflineProtocolError("Stage C v6 离线授权边界漂移")
    if (
        value["budget"]["per_arm"].get("max_recorded_tokens") is not None
        or value["budget"]["token_accounting"].get("token_total_is_termination_condition") is not False
        or value["schedule"].get("evaluation_count") != 22
        or value["schedule"].get("retry") is not False
        or value["schedule"].get("replacement") is not False
        or value["schedule"].get("backfill") is not False
    ):
        raise StageCV6OfflineProtocolError("Stage C v6 schedule 或 token 边界漂移")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        if not DEFAULT_SCHEMA.is_file() or qualification.load_json(DEFAULT_SCHEMA) != schema:
            raise StageCV6OfflineProtocolError("Stage C v6 authorized const Schema 漂移")
        jsonschema.validate(value, qualification.load_json(DEFAULT_SCHEMA))
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_manifest(qualification.load_json(path), repo_root)


def release_revision(repo_root: Path = REPO_ROOT) -> str:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", AUTHORIZATION_BASELINE_COMMIT, revision],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestry.returncode != 0:
        raise StageCV6OfflineProtocolError("当前 revision 不是授权基线的后代")
    return revision


def write_generated(manifest: dict[str, Any]) -> None:
    DEFAULT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    DEFAULT_SCHEMA.write_text(
        json.dumps(generate_schema(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture-source-receipt", "generate", "validate", "show-plan"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "capture-source-receipt":
        output = args.output or (REPO_ROOT / SOURCE_RECEIPT_PATH)
        receipt = capture_source_receipt()
        write_source_receipt(receipt, output)
        result: Any = {
            "status": "source_receipt_captured",
            "path": str(output),
            "file_sha256": file_sha256(output),
            "canonical_sha256": canonical_sha256(receipt),
            "evaluation_count": receipt["evaluation_count"],
        }
    elif args.command == "generate":
        manifest = generate_manifest()
        write_generated(manifest)
        result = {
            "status": "generated_authorized",
            "manifest_sha256": canonical_sha256(manifest),
            "evaluation_count": manifest["schedule"]["evaluation_count"],
            "provider_calls_authorized": False,
            "model_tokens_authorized": 0,
        }
    else:
        manifest = load_manifest()
        if args.command == "validate":
            result = {
                "status": "valid_authorized",
                "manifest_sha256": canonical_sha256(manifest),
                "release_revision": release_revision(),
                "provider_calls": 0,
                "model_tokens": 0,
                "evaluation_count": manifest["schedule"]["evaluation_count"],
            }
        else:
            result = manifest["schedule"]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
