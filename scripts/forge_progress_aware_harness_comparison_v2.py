#!/usr/bin/env python3
"""Issue #433：修复 canary instrumentation 的 H0/H1 配对比较 v2。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_PATH.parent)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_progress_aware_harness_comparison_v1 as base  # noqa: E402

IDENTITY = "cpp-progress-aware-harness-comparison-v2"
TRACKING_ISSUE = 433
BRANCH = "yiwei/433-h0-h1-provider-comparison"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-progress-aware-harness-comparison-v2.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
SPEC_PATH = REPO_ROOT / "docs/superpowers/specs/2026-10-13-progress-aware-harness-comparison-v2-design.md"
PLAN_PATH = REPO_ROOT / "docs/superpowers/plans/2026-10-13-progress-aware-harness-comparison-v2.md"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
COMPONENT_PATHS = (
    "scripts/forge_progress_aware_harness_comparison_v1.py",
    "scripts/forge_progress_aware_harness_comparison_v2.py",
    "scripts/forge_agent_continuation_qualification_v2.py",
    "scripts/forge_checkpoint_archive.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v2.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v4.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "backend/tests/test_forge_progress_aware_harness_comparison_v2.py",
    "benchmarks/schemas/forge-progress-aware-harness-comparison-v2.schema.json",
    "benchmarks/preregistrations/cpp-progress-aware-harness-comparison-v2.md",
    "docs/superpowers/specs/2026-10-13-progress-aware-harness-comparison-v2-design.md",
    "docs/superpowers/plans/2026-10-13-progress-aware-harness-comparison-v2.md",
)

QualificationError = base.QualificationError
_BASE_VALIDATE = base.validate_manifest
_BASE_PREFLIGHT = base.preflight
_BASE_ARM_COMPLETE = base._arm_complete
_BASE_WRITE_REPORT = base.write_report


def _manifest() -> dict[str, Any]:
    return base.base._load_json(MANIFEST_PATH)


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
    base._events = _events
    base._arm_complete = _arm_complete
    base.validate_manifest = validate_manifest
    base.preflight = preflight
    base.write_report = write_report
    base._activate_base()


def _events(arm_dir: Path) -> list[dict[str, Any]]:
    paths = [path for path in sorted((arm_dir / "session-evidence").rglob("events.jsonl")) if "evaluations" not in path.parts]
    if len(paths) != 1:
        return []
    return [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines() if line]


def _arm_complete(item: dict[str, Any]) -> bool:
    if not _BASE_ARM_COMPLETE(item):
        return False
    metrics = item.get("harness_metrics", {})
    requests = item.get("token_accounting", {}).get("requests_completed")
    if item.get("treatment") == "h0_runtime_v3":
        return metrics.get("progress_snapshots") == 0 and metrics.get("context_compactions") == 0
    if item.get("treatment") == "h1_runtime_v4":
        return type(requests) is int and requests > 0 and metrics.get("progress_snapshots") == requests and metrics.get("context_compactions") == requests
    return False


def _validate_v1_parent(manifest: dict[str, Any]) -> None:
    parent = manifest.get("remediation_parent", {})
    expected = {
        "identity": "cpp-progress-aware-harness-comparison-v1",
        "evidence_root": ".compile-sessions/benchmark-evidence-progress-aware-harness-comparison-v1",
        "inventory_canonical_sha256": "3a03ec1a2bed0ab5311842ce51bc0292963871d2c9f3d9d364ce84aae51fa201",
        "decision": "supersede_before_q2_due_to_canary_instrumentation_gap",
    }
    if parent != expected:
        raise QualificationError("v1 remediation parent identity 漂移")
    root = REPO_ROOT / parent["evidence_root"]
    base._validate_inventory(root, parent["inventory_canonical_sha256"], "comparison-v1")
    if (root / "q2").exists():
        raise QualificationError("v1 不得存在 Q2 observation")
    q0 = base.base._load_json(root / "q0/result.json")
    q1 = base.base._load_json(root / "q1/result.json")
    if q0.get("passed") is not True or q1.get("passed") is not True:
        raise QualificationError("v1 Q0/Q1 前提漂移")
    h1_arms = [path.parent for path in sorted((root / "q1/arms").glob("*h1_runtime_v4/result.json"))]
    snapshot_counts = [sum(event.get("event_type") == "harness.progress_snapshot" for event in _events(path)) for path in h1_arms]
    if snapshot_counts != [5, 6, 7]:
        raise QualificationError("v1 raw H1 treatment observation 漂移")


def validate_manifest(manifest: dict[str, Any], *, require_components: bool = True) -> dict[str, Any]:
    _activate_base()
    _BASE_VALIDATE(manifest, require_components=require_components)
    _validate_v1_parent(manifest)
    return manifest


def preflight(manifest: dict[str, Any], *, phase: str) -> dict[str, Any]:
    _activate_base()
    result = _BASE_PREFLIGHT(manifest, phase=phase)
    result["remediation_parent_inventory_canonical_sha256"] = manifest["remediation_parent"]["inventory_canonical_sha256"]
    return result


def write_report(manifest: dict[str, Any]) -> dict[str, Any]:
    _activate_base()
    report = _BASE_WRITE_REPORT(manifest)
    markdown = REPORT_MD_PATH.read_text(encoding="utf-8")
    REPORT_MD_PATH.write_text(
        markdown.replace(
            "进展感知结构化 Harness H0/H1 配对比较 v1 结果",
            "进展感知结构化 Harness H0/H1 配对比较 v2 结果",
            1,
        ),
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "plan",
            "preflight-q0",
            "preflight-q1",
            "preflight-q2",
            "q0",
            "q1",
            "q2",
            "audit",
            "seal",
            "report",
        ),
    )
    arguments = parser.parse_args()
    manifest = _manifest()
    _activate_base()
    if arguments.command == "validate":
        payload = {
            "valid": True,
            "manifest_sha256": base.base._canonical_sha256(validate_manifest(manifest)),
        }
    elif arguments.command == "plan":
        payload = base._plan(validate_manifest(manifest, require_components=False))
    elif arguments.command.startswith("preflight-"):
        payload = preflight(manifest, phase=arguments.command.removeprefix("preflight-"))
    elif arguments.command == "q0":
        payload = base.execute_q0(manifest)
    elif arguments.command == "q1":
        payload = base.execute_q1(manifest)
    elif arguments.command == "q2":
        payload = base.execute_q2(manifest)
    elif arguments.command == "audit":
        payload = base.audit(manifest)
    elif arguments.command == "seal":
        payload = base.audit(manifest, seal=True)
    else:
        payload = write_report(manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
