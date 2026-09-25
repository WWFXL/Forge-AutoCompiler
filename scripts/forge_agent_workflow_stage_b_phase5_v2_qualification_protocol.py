#!/usr/bin/env python3
"""生成并校验 Phase 5 v2 exact-commit build-system qualification。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent

SCHEMA_VERSION = "forge-agent-workflow-stage-b-phase5-v2-qualification-1.0.0"
RESULT_SCHEMA_VERSION = "forge-agent-workflow-stage-b-phase5-v2-qualification-result-1.0.0"
DOCUMENT_TYPE = "forge_agent_workflow_stage_b_phase5_v2_qualification"
RESULT_DOCUMENT_TYPE = "forge_agent_workflow_stage_b_phase5_v2_qualification_result"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/294"
PARENT_MANIFEST_PATH = "benchmarks/manifests/cpp-agent-workflow-stage-b-calibration-candidate.json"
PARENT_MANIFEST_CANONICAL_SHA256 = "303b41c0ee95c4732eb9388a39176789064e131c19217632175fa19e1526434f"
STOP_REPORT_PATH = "benchmarks/reports/cpp-agent-workflow-stage-b-calibration-failed.json"
STOP_REPORT_SHA256 = "00d2463d3bfc4da9ca59c4b23f3eb0d9dba57144cffbe680ca4c808ced1f565e"
IMAGE = "autocompiler:gcc13"
IMAGE_ID = "sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a"
PLAN_PATH = "benchmarks/manifests/cpp-agent-workflow-stage-b-phase5-v2-qualification.json"
SCHEMA_PATH = "benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v2-qualification.schema.json"
PROTOCOL_PATH = "scripts/forge_agent_workflow_stage_b_phase5_v2_qualification_protocol.py"
RUNNER_PATH = "scripts/forge_agent_workflow_stage_b_phase5_v2_qualification_runner.py"
SPEC_PATH = "docs/superpowers/specs/2026-09-25-phase5-v2-qualification-oracle-design.md"
SUPPORTED_BUILD_SYSTEMS = frozenset({"cmake", "make", "autotools"})


class Phase5V2QualificationError(RuntimeError):
    """Phase 5 v2 qualification plan 或 result 无效。"""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


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
        raise Phase5V2QualificationError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise Phase5V2QualificationError(f"JSON 根节点必须是对象: {path}")
    return value


def _parent_manifest(repo_root: Path) -> dict[str, Any]:
    parent = _load_json(repo_root / PARENT_MANIFEST_PATH)
    if canonical_sha256(parent) != PARENT_MANIFEST_CANONICAL_SHA256:
        raise Phase5V2QualificationError("Phase 5 父候选 manifest identity 发生漂移")
    return parent


def _qualification_tasks(repo_root: Path) -> list[dict[str, Any]]:
    parent = _parent_manifest(repo_root)
    order = parent["schedule"]["order"]
    by_id = {task["task_id"]: task for task in parent["tasks"]}
    return [
        {
            "task_id": task_id,
            "repository_url": by_id[task_id]["repository_url"],
            "commit_sha": by_id[task_id]["commit_sha"],
            "historical_build_system_label": by_id[task_id]["build_system"],
        }
        for task_id in order
    ]


def generate_plan(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if file_sha256(repo_root / STOP_REPORT_PATH) != STOP_REPORT_SHA256:
        raise Phase5V2QualificationError("首次 Phase 5 停止报告发生漂移")
    frozen_paths = (
        "backend/packages/harness/deerflow/compile/operations.py",
        "backend/packages/harness/deerflow/compile/schemas.py",
        "backend/packages/harness/deerflow/compile/external_evaluator_v2.py",
        PROTOCOL_PATH,
        RUNNER_PATH,
        SPEC_PATH,
    )
    return {
        "$schema": "../schemas/forge-agent-workflow-stage-b-phase5-v2-qualification.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "issue_url": ISSUE_URL,
        "status": "awaiting_manual_execution",
        "purpose": "offline_exact_commit_build_system_qualification",
        "parent_manifest": {
            "path": PARENT_MANIFEST_PATH,
            "canonical_sha256": PARENT_MANIFEST_CANONICAL_SHA256,
        },
        "stopped_phase5_report": {
            "path": STOP_REPORT_PATH,
            "sha256": STOP_REPORT_SHA256,
            "historical_evidence_reused": False,
        },
        "authorization": {
            "provider_calls_authorized": False,
            "credential_read_authorized": False,
            "model_creation_authorized": False,
            "formal_attempts_authorized": False,
            "formal_evidence_write_authorized": False,
            "docker_qualification_execution_owner": "user",
        },
        "environment": {
            "compile_image": IMAGE,
            "image_id": IMAGE_ID,
            "parallel_jobs": 4,
        },
        "requirements": {
            "exact_commit_checkout": True,
            "forge_build_system_probe": "inspect_build_system_impl",
            "freeze_capabilities_and_selection": True,
            "cleanup_each_task": True,
            "zero_managed_orphans_before_and_after": True,
            "output_outside_formal_evidence": True,
        },
        "tasks": _qualification_tasks(repo_root),
        "frozen_components": {path: file_sha256(repo_root / path) for path in frozen_paths},
    }


def generate_schema(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-agent-workflow-stage-b-phase5-v2-qualification.schema.json",
        "title": "Forge Agent Workflow Stage B Phase 5 v2 build-system qualification",
        "const": plan,
    }


def validate_plan(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_plan(repo_root)
    if value != expected:
        raise Phase5V2QualificationError("Phase 5 v2 qualification plan 与确定性生成结果不一致")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(value, schema)
    return value


def load_plan(path: Path | None = None, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return validate_plan(_load_json(path or repo_root / PLAN_PATH), repo_root)


def validate_result(value: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != RESULT_SCHEMA_VERSION or value.get("document_type") != RESULT_DOCUMENT_TYPE:
        raise Phase5V2QualificationError("qualification result schema identity 无效")
    if value.get("status") != "passed" or value.get("qualification_plan_sha256") != canonical_sha256(plan):
        raise Phase5V2QualificationError("qualification result 未通过或 plan identity 不匹配")
    if value.get("image") != plan["environment"]["compile_image"] or value.get("image_id") != plan["environment"]["image_id"]:
        raise Phase5V2QualificationError("qualification result 镜像 identity 不匹配")
    if value.get("provider_request_count") != 0 or value.get("model_created") is not False or value.get("formal_attempt_created") is not False:
        raise Phase5V2QualificationError("qualification result 违反 0 Provider 边界")
    if value.get("zero_managed_resources_before") is not True or value.get("zero_managed_resources_after") is not True:
        raise Phase5V2QualificationError("qualification result 未闭合 0 orphan")
    expected_tasks = plan["tasks"]
    observed_tasks = value.get("tasks")
    if not isinstance(observed_tasks, list) or [task.get("task_id") for task in observed_tasks] != [task["task_id"] for task in expected_tasks]:
        raise Phase5V2QualificationError("qualification result task 顺序或数量不匹配")
    for expected, observed in zip(expected_tasks, observed_tasks, strict=True):
        for key in ("repository_url", "commit_sha"):
            if observed.get(key) != expected[key]:
                raise Phase5V2QualificationError(f"{expected['task_id']} {key} 发生漂移")
        capabilities = observed.get("build_system_capabilities")
        selected = observed.get("selected_build_system")
        if (
            not isinstance(capabilities, list)
            or not capabilities
            or len(capabilities) != len(set(capabilities))
            or any(capability not in SUPPORTED_BUILD_SYSTEMS for capability in capabilities)
            or selected not in capabilities
            or selected != capabilities[0]
        ):
            raise Phase5V2QualificationError(f"{expected['task_id']} build-system qualification 无效")
        if observed.get("cleanup_succeeded") is not True:
            raise Phase5V2QualificationError(f"{expected['task_id']} cleanup 未闭合")
    return value


def write_artifacts(repo_root: Path = REPO_ROOT) -> None:
    plan = generate_plan(repo_root)
    schema = generate_schema(plan)
    for relative_path, value in ((PLAN_PATH, plan), (SCHEMA_PATH, schema)):
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "validate-result"))
    parser.add_argument("--plan", type=Path, default=REPO_ROOT / PLAN_PATH)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)
    if args.command == "generate":
        write_artifacts()
        value = load_plan(args.plan)
    else:
        value = load_plan(args.plan)
        if args.command == "validate-result":
            if args.result is None:
                parser.error("validate-result requires --result")
            validate_result(_load_json(args.result), value)
    print(json.dumps({"status": "valid", "qualification_plan_sha256": canonical_sha256(value)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
