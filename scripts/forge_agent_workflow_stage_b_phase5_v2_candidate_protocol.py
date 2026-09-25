#!/usr/bin/env python3
"""生成并校验 Phase 5 v2 未授权候选身份。"""

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

import forge_agent_workflow_stage_b_calibration_protocol as parent_protocol  # noqa: E402
import forge_agent_workflow_stage_b_phase5_v2_qualification_protocol as qualification_protocol  # noqa: E402

SCHEMA_VERSION = "forge-agent-workflow-stage-b-phase5-v2-candidate-1.0.0"
DOCUMENT_TYPE = "forge_agent_workflow_stage_b_phase5_v2_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/291"
BASELINE_COMMIT = "1269d34ccb58f3545ffbd5469c141d321cdc1246"
MANIFEST_RELATIVE_PATH = (
    "benchmarks/manifests/cpp-agent-workflow-stage-b-phase5-v2-candidate.json"
)
SCHEMA_RELATIVE_PATH = (
    "benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v2-candidate.schema.json"
)
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-agent-workflow-stage-b-phase5-v2-candidate.md"
)
PROTOCOL_PATH = "scripts/forge_agent_workflow_stage_b_phase5_v2_candidate_protocol.py"
RUNNER_PATH = "scripts/forge_agent_workflow_stage_b_phase5_v2_candidate_runner.py"
QUALIFICATION_RESULT_PATH = (
    "benchmarks/fixtures/agent-workflow-stage-b-phase5-v2-qualification-result.json"
)
QUALIFICATION_RESULT_SHA256 = (
    "df98e57edfea7b42911e8008534b94a62261aa93d7c3d20ae36f6ee8f8343125"
)
QUALIFICATION_RELEASE_REVISION = BASELINE_COMMIT
EVIDENCE_DIRECTORY = (
    "/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v2"
)
STOP_REPORT_PATH = qualification_protocol.STOP_REPORT_PATH
STOP_REPORT_SHA256 = qualification_protocol.STOP_REPORT_SHA256

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH
DEFAULT_QUALIFICATION_RESULT = REPO_ROOT / QUALIFICATION_RESULT_PATH

QUALIFIED_BUILD_SYSTEMS: dict[str, tuple[tuple[str, ...], str]] = {
    "yyjson": (("cmake",), "cmake"),
    "cppitertools": (("cmake",), "cmake"),
    "openh264": (("make",), "make"),
    "uwebsockets": (("make",), "make"),
    "c-ares": (("cmake", "autotools"), "cmake"),
    "libass": (("autotools",), "autotools"),
}


class Phase5V2CandidateProtocolError(RuntimeError):
    """Phase 5 v2 candidate identity 或 qualification 来源无效。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5V2CandidateProtocolError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise Phase5V2CandidateProtocolError(f"JSON 根节点必须是对象: {path}")
    return value


def load_qualification_result(
    path: Path = DEFAULT_QUALIFICATION_RESULT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if file_sha256(path) != QUALIFICATION_RESULT_SHA256:
        raise Phase5V2CandidateProtocolError(
            "Phase 5 v2 qualification result 字节 identity 发生漂移"
        )
    result = _load_json(path)
    plan = qualification_protocol.load_plan(repo_root=repo_root)
    try:
        qualification_protocol.validate_result(result, plan)
    except qualification_protocol.Phase5V2QualificationError as exc:
        raise Phase5V2CandidateProtocolError(
            "Phase 5 v2 qualification result 合同无效"
        ) from exc
    if result.get("release_revision") != QUALIFICATION_RELEASE_REVISION:
        raise Phase5V2CandidateProtocolError(
            "Phase 5 v2 qualification release revision 发生漂移"
        )
    observed = {
        task["task_id"]: (
            tuple(task["build_system_capabilities"]),
            task["selected_build_system"],
        )
        for task in result["tasks"]
    }
    if observed != QUALIFIED_BUILD_SYSTEMS:
        raise Phase5V2CandidateProtocolError(
            "Phase 5 v2 qualification build-system 决策发生漂移"
        )
    return result


def _qualified_tasks(repo_root: Path) -> list[dict[str, Any]]:
    parent = parent_protocol.load_manifest(repo_root=repo_root)
    tasks: list[dict[str, Any]] = []
    for task in parent["tasks"]:
        qualified = copy.deepcopy(task)
        historical_label = qualified.pop("build_system")
        capabilities, selected = QUALIFIED_BUILD_SYSTEMS[qualified["task_id"]]
        qualified["historical_build_system_label"] = historical_label
        qualified["build_system_capabilities"] = list(capabilities)
        qualified["selected_build_system"] = selected
        tasks.append(qualified)
    return tasks


def _frozen_components(repo_root: Path) -> dict[str, str]:
    paths = (
        PREREGISTRATION_PATH,
        QUALIFICATION_RESULT_PATH,
        qualification_protocol.PLAN_PATH,
        qualification_protocol.PROTOCOL_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
        "backend/packages/harness/deerflow/compile/external_evaluator_v2.py",
    )
    return {path: file_sha256(repo_root / path) for path in paths}


def _qualification_receipt(repo_root: Path) -> dict[str, Any]:
    result = load_qualification_result(repo_root / QUALIFICATION_RESULT_PATH, repo_root)
    return {
        "plan_path": qualification_protocol.PLAN_PATH,
        "plan_canonical_sha256": qualification_protocol.canonical_sha256(
            qualification_protocol.load_plan(repo_root=repo_root)
        ),
        "result_path": QUALIFICATION_RESULT_PATH,
        "result_sha256": QUALIFICATION_RESULT_SHA256,
        "release_revision": result["release_revision"],
        "image_id": result["image_id"],
        "status": result["status"],
        "provider_request_count": result["provider_request_count"],
        "model_created": result["model_created"],
        "formal_attempt_created": result["formal_attempt_created"],
        "zero_managed_resources_before": result["zero_managed_resources_before"],
        "zero_managed_resources_after": result["zero_managed_resources_after"],
    }


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    parent = parent_protocol.load_manifest(repo_root=repo_root)
    if file_sha256(repo_root / STOP_REPORT_PATH) != STOP_REPORT_SHA256:
        raise Phase5V2CandidateProtocolError("首次 Phase 5 停止报告发生漂移")
    qualification = _qualification_receipt(repo_root)
    manifest = copy.deepcopy(parent)
    manifest.pop("historical_baseline", None)
    manifest.update(
        {
            "$schema": "../schemas/forge-agent-workflow-stage-b-phase5-v2-candidate.schema.json",
            "schema_version": SCHEMA_VERSION,
            "document_type": DOCUMENT_TYPE,
            "issue_url": ISSUE_URL,
            "status": "candidate_not_authorized",
            "baseline_commit": BASELINE_COMMIT,
        }
    )
    manifest["authorization"] = {
        "provider_calls_authorized": False,
        "credential_read_authorized": False,
        "model_creation_authorized": False,
        "reachability_request_authorized": False,
        "docker_execution_authorized": False,
        "evidence_write_authorized": False,
        "formal_attempts_authorized": False,
        "model_tokens_authorized": 0,
    }
    manifest["parent_phase5"] = {
        "candidate_manifest_path": parent_protocol.MANIFEST_RELATIVE_PATH,
        "candidate_manifest_canonical_sha256": parent_protocol.canonical_sha256(parent),
        "stopped_report_path": STOP_REPORT_PATH,
        "stopped_report_sha256": STOP_REPORT_SHA256,
        "outcomes_imported": False,
        "historical_evidence_reused": False,
    }
    manifest["qualification"] = qualification
    manifest["environment_candidate"]["image_id"] = qualification["image_id"]
    manifest["environment_candidate"][
        "image_id_must_be_frozen_by_authorized_amendment"
    ] = False
    manifest["tasks"] = _qualified_tasks(repo_root)
    manifest["runtime_candidate"] = {
        "orchestration_mode": "agent_workflow_node_v1",
        "protocol_path": PROTOCOL_PATH,
        "runner_path": RUNNER_PATH,
        "external_evaluator": "external-evaluator-v2",
        "clean_replay_required": True,
        "finalize_and_cleanup_required": True,
        "zero_managed_orphans_required": True,
        "qualification_revalidation_before_model_creation": True,
    }
    manifest["evidence_candidate"] = {
        "directory": EVIDENCE_DIRECTORY,
        "create_once": True,
        "historical_evidence_reused": False,
        "task_result_path": "tasks/{task_id}/result.json",
        "batch_marker": "markers/batch.json",
        "batch_report": "reports/stage-b-phase5-v2.json",
        "writes_authorized": False,
    }
    manifest["frozen_components"] = _frozen_components(repo_root)
    return manifest


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v2-candidate.schema.json",
        "title": "Forge Agent Workflow Stage B Phase 5 v2 candidate",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise Phase5V2CandidateProtocolError(
            "Phase 5 v2 candidate manifest 与确定性生成结果不一致"
        )
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(value, schema)
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    return validate_manifest(_load_json(path), repo_root)


def collect_preflight(
    value: dict[str, Any],
    qualification_result_path: Path = DEFAULT_QUALIFICATION_RESULT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    manifest = validate_manifest(value, repo_root)
    result = load_qualification_result(qualification_result_path, repo_root)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, revision],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if ancestor.returncode != 0:
        raise Phase5V2CandidateProtocolError(
            "Phase 5 v2 baseline commit 不是当前 revision 的祖先"
        )
    return {
        "status": "candidate_valid_not_authorized",
        "manifest_sha256": canonical_sha256(manifest),
        "release_revision": revision,
        "qualification_result_sha256": file_sha256(qualification_result_path),
        "qualification_release_revision": result["release_revision"],
        "task_count": len(manifest["tasks"]),
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_executions": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


def write_artifacts(repo_root: Path = REPO_ROOT) -> None:
    manifest = generate_manifest(repo_root)
    schema = generate_schema(manifest)
    for relative_path, value in (
        (MANIFEST_RELATIVE_PATH, manifest),
        (SCHEMA_RELATIVE_PATH, schema),
    ):
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "preflight"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--qualification-result", type=Path, default=DEFAULT_QUALIFICATION_RESULT
    )
    args = parser.parse_args(argv)
    if args.command == "generate":
        load_qualification_result(args.qualification_result)
        write_artifacts()
        manifest = load_manifest(args.manifest)
        result: Any = {
            "status": "generated",
            "manifest": MANIFEST_RELATIVE_PATH,
            "schema": SCHEMA_RELATIVE_PATH,
        }
    else:
        manifest = load_manifest(args.manifest)
        result = (
            {"status": "valid", "manifest_sha256": canonical_sha256(manifest)}
            if args.command == "validate"
            else collect_preflight(manifest, args.qualification_result)
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
