#!/usr/bin/env python3
"""Issue #440：执行 H0/H1 v3 确认性复现并审计完整 Token 计量。"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_PATH.parent)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_progress_aware_harness_comparison_v1 as base  # noqa: E402
import forge_progress_aware_harness_comparison_v3_candidate as candidate  # noqa: E402

IDENTITY = "cpp-progress-aware-harness-comparison-v3-authorized"
TRACKING_ISSUE = 440
BRANCH = "yiwei/440-h0-h1-v3-execution"
SCHEMA_ID = "forge-progress-aware-harness-comparison-v3-authorized"
CANDIDATE_REVISION = "c5ac1e0875b1de84594afa91e2a1fa5bfb2bdde7"
CANDIDATE_MANIFEST_SHA256 = "128c629dbcb5da28e0b68fb3fdfb0320e09cd1f86cac505b028d780ca692ced0"
CANDIDATE_MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-progress-aware-harness-comparison-v3-candidate.json"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas" / f"{SCHEMA_ID}.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
SPEC_PATH = REPO_ROOT / "docs/superpowers/specs/2026-10-13-progress-aware-harness-comparison-v3-design.md"
PLAN_PATH = REPO_ROOT / "docs/superpowers/plans/2026-10-13-progress-aware-harness-comparison-v3.md"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"

COMPONENT_PATHS = (
    "scripts/forge_progress_aware_harness_comparison_v3.py",
    "scripts/forge_progress_aware_harness_comparison_v3_candidate.py",
    "scripts/forge_progress_aware_harness_comparison_v1.py",
    "scripts/forge_agent_continuation_qualification_v2.py",
    "scripts/forge_checkpoint_archive.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_node.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v4.py",
    "backend/packages/harness/deerflow/compile/agent_workflow_schemas.py",
    "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "backend/packages/harness/deerflow/compile/external_evaluator_v4.py",
    "backend/packages/harness/deerflow/compile/operations.py",
    "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
    "benchmarks/manifests/cpp-progress-aware-harness-comparison-v3-candidate.json",
    "benchmarks/preregistrations/cpp-progress-aware-harness-comparison-v3-candidate.md",
    "benchmarks/preregistrations/cpp-progress-aware-harness-comparison-v3-authorized.md",
    "docs/superpowers/specs/2026-10-13-progress-aware-harness-comparison-v3-design.md",
    "docs/superpowers/plans/2026-10-13-progress-aware-harness-comparison-v3.md",
)

QualificationError = base.QualificationError
_BASE_VALIDATE = base.validate_manifest
_BASE_PREFLIGHT = base.preflight
_BASE_ARM_COMPLETE = base._arm_complete
_BASE_FORMAL_QUALIFICATION = base._formal_qualification
_BASE_AUDIT = base.audit
_BASE_WRITE_REPORT = base.write_report
_BASE_BUDGET_RECORD = base.base._budget_record
_V1_ACTIVATE = base._activate_base
_EXECUTION_ACTIVE = False
_V1_BINDINGS = {
    name: getattr(base, name)
    for name in (
        "IDENTITY",
        "TRACKING_ISSUE",
        "BRANCH",
        "SCRIPT_PATH",
        "MANIFEST_PATH",
        "SCHEMA_PATH",
        "PREREGISTRATION_PATH",
        "SPEC_PATH",
        "PLAN_PATH",
        "REPORT_JSON_PATH",
        "REPORT_MD_PATH",
        "COMPONENT_PATHS",
        "_events",
        "_arm_complete",
        "_check_total_budget",
        "_formal_qualification",
        "validate_manifest",
        "preflight",
    )
}


def _load_json(path: Path) -> dict[str, Any]:
    return base.base._load_json(path)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _frozen_components() -> dict[str, str]:
    return {relative: base.base._file_sha256(REPO_ROOT / relative) for relative in COMPONENT_PATHS}


def generate_manifest() -> dict[str, Any]:
    frozen_candidate = _load_json(CANDIDATE_MANIFEST_PATH)
    if candidate.canonical_sha256(frozen_candidate) != CANDIDATE_MANIFEST_SHA256:
        raise QualificationError("candidate manifest canonical identity 漂移")
    value = copy.deepcopy(frozen_candidate)
    value.update(
        {
            "$schema": SCHEMA_ID,
            "identity": IDENTITY,
            "issue": TRACKING_ISSUE,
            "branch": BRANCH,
            "status": "authorized_for_execution",
            "release_revision": None,
            "release_revision_policy": "clean_pushed_branch_head_descending_from_candidate_recorded_before_q0",
            "candidate_binding": {
                "identity": frozen_candidate["identity"],
                "issue": frozen_candidate["issue"],
                "revision": CANDIDATE_REVISION,
                "manifest_path": str(CANDIDATE_MANIFEST_PATH.relative_to(REPO_ROOT)),
                "manifest_canonical_sha256": CANDIDATE_MANIFEST_SHA256,
                "candidate_mutation_forbidden": True,
            },
            "authorization": {
                "zero_provider_q0": True,
                "credential_read_after_q0": True,
                "provider_canary_formal": True,
                "formal_evidence_write": True,
                "historical_evidence_write": False,
                "replacement": False,
                "backfill": False,
                "controller_implementation": False,
                "jev_calls": False,
            },
            "authorization_record": {
                "authorized_by": "research_owner",
                "authorized_at": "2026-10-13",
                "tracking_issue": TRACKING_ISSUE,
                "credential_read": True,
                "provider_calls": True,
                "docker_execution": True,
                "formal_evidence_write": True,
                "maximum_provider_requests": 1_440,
                "maximum_recorded_tokens": 24_000_000,
                "maximum_provider_cost_usd": 28.8,
            },
            "provider": {**frozen_candidate["provider"], "status": "authorized"},
            "evidence_root": ".compile-sessions/benchmark-evidence-progress-aware-harness-comparison-v3",
            "components": _frozen_components(),
            "preregistration": {
                "path": str(PREREGISTRATION_PATH.relative_to(REPO_ROOT)),
                "sha256": base.base._file_sha256(PREREGISTRATION_PATH),
            },
        }
    )
    value.pop("planned_evidence_root", None)
    value.pop("future_execution", None)
    return value


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Forge progress-aware harness H0/H1 v3 authorized replication",
        "const": copy.deepcopy(manifest if manifest is not None else generate_manifest()),
    }


def _manifest() -> dict[str, Any]:
    return _load_json(MANIFEST_PATH)


def _events(arm_dir: Path) -> list[dict[str, Any]]:
    paths = [path for path in sorted((arm_dir / "session-evidence").rglob("events.jsonl")) if "evaluations" not in path.parts]
    if len(paths) != 1:
        return []
    return [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines() if line]


def _token_observation(events_path: Path) -> dict[str, Any]:
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line]
    terminals = {
        "model.request_completed": "completed",
        "model.request_failed": "failed",
        "model.request_usage_incomplete": "usage_incomplete",
    }
    started_sequences: list[Any] = []
    terminal_by_sequence: dict[Any, list[str]] = {}
    requests: list[dict[str, Any]] = []
    budget_contract_violations = 0
    for event in events:
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        sequence = payload.get("request_sequence")
        if event_type == "model.request_started":
            started_sequences.append(sequence)
        elif event_type in terminals:
            terminal_by_sequence.setdefault(sequence, []).append(terminals[event_type])
            if event_type == "model.request_completed":
                requests.append(
                    {
                        "request_sequence": sequence,
                        "input_tokens": payload.get("input_tokens"),
                        "output_tokens": payload.get("output_tokens"),
                        "recorded_tokens": payload.get("recorded_tokens"),
                    }
                )
        elif event_type == "budget.contract_violated":
            budget_contract_violations += 1
    valid_usage = all(type(item[field]) is int and item[field] >= 0 for item in requests for field in ("request_sequence", "input_tokens", "output_tokens", "recorded_tokens")) and all(
        item["recorded_tokens"] == item["input_tokens"] + item["output_tokens"] for item in requests
    )
    lifecycle_closed = (
        all(type(sequence) is int and sequence > 0 for sequence in started_sequences)
        and len(started_sequences) == len(set(started_sequences))
        and set(terminal_by_sequence) == set(started_sequences)
        and all(len(values) == 1 for values in terminal_by_sequence.values())
    )
    terminal_counts = Counter(value for values in terminal_by_sequence.values() for value in values)
    return {
        "requests_started": len(started_sequences),
        "requests_completed": terminal_counts["completed"],
        "requests_failed": terminal_counts["failed"],
        "requests_usage_incomplete": terminal_counts["usage_incomplete"],
        "requests": requests,
        "input_tokens": sum(item["input_tokens"] for item in requests) if valid_usage else None,
        "output_tokens": sum(item["output_tokens"] for item in requests) if valid_usage else None,
        "recorded_tokens": sum(item["recorded_tokens"] for item in requests) if valid_usage else None,
        "request_lifecycle_closed": lifecycle_closed,
        "budget_contract_violations": budget_contract_violations,
        "complete": valid_usage and lifecycle_closed and terminal_counts["usage_incomplete"] == 0,
    }


def _budget_record(
    manifest: dict[str, Any],
    parent: dict[str, Any],
    node_result: Any,
    tokens: dict[str, Any],
    duration_ms: int,
    session: Any,
) -> dict[str, Any]:
    record = _BASE_BUDGET_RECORD(manifest, parent, node_result, tokens, duration_ms, session)
    record["complete"] = bool(
        node_result is not None
        and tokens.get("complete") is True
        and tokens.get("requests_usage_incomplete") == 0
        and tokens.get("recorded_tokens") == node_result.usage.recorded_tokens
        and tokens.get("requests_started") == node_result.usage.model_requests
    )
    return record


def _arm_usage_integrity(item: dict[str, Any]) -> bool:
    tokens = item.get("token_accounting", {})
    node = item.get("node_result") or {}
    usage = node.get("usage") or {}
    budget = item.get("budget") or {}
    delta = budget.get("delta") or {}
    return bool(
        tokens.get("complete") is True
        and tokens.get("request_lifecycle_closed") is True
        and tokens.get("requests_usage_incomplete") == 0
        and tokens.get("budget_contract_violations") == 0
        and node.get("primary_failure") not in {"usage_incomplete", "budget_contract_violation"}
        and usage.get("model_requests") == tokens.get("requests_started") == delta.get("provider_requests")
        and usage.get("recorded_tokens") == tokens.get("recorded_tokens")
        and tokens.get("input_tokens") == delta.get("input_tokens")
        and tokens.get("output_tokens") == delta.get("output_tokens")
    )


def _arm_complete(item: dict[str, Any]) -> bool:
    if not _BASE_ARM_COMPLETE(item) or not _arm_usage_integrity(item):
        return False
    metrics = item.get("harness_metrics", {})
    requests = item.get("token_accounting", {}).get("requests_completed")
    if item.get("treatment") == "h0_runtime_v3":
        return metrics.get("progress_snapshots") == 0 and metrics.get("context_compactions") == 0
    if item.get("treatment") == "h1_runtime_v4":
        return type(requests) is int and requests > 0 and metrics.get("progress_snapshots") == requests and metrics.get("context_compactions") == requests
    return False


def _totals(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "provider_requests": sum(item["token_accounting"]["requests_started"] for item in outcomes),
        "recorded_tokens": sum(item["token_accounting"]["recorded_tokens"] or 0 for item in outcomes),
        "provider_cost_microusd": sum(item["budget"]["delta"]["provider_cost_microusd"] for item in outcomes if item.get("budget")),
    }


def _check_total_budget(manifest: dict[str, Any], outcomes: list[dict[str, Any]]) -> None:
    totals = _totals(outcomes)
    budget = manifest["budget"]
    if (
        totals["provider_requests"] > budget["total_provider_requests"]
        or totals["recorded_tokens"] > budget["total_authorized_recorded_tokens"]
        or totals["provider_cost_microusd"] > round(budget["total_provider_cost_usd_ceiling"] * 1_000_000)
    ):
        raise QualificationError("Provider 批次授权上界被突破")


def _formal_qualification(manifest: dict[str, Any], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    result = _BASE_FORMAL_QUALIFICATION(manifest, outcomes)
    result["hard_gates"].update(
        {
            "request_lifecycle_closed": len(outcomes) == 54 and all(item.get("token_accounting", {}).get("request_lifecycle_closed") is True for item in outcomes),
            "usage_complete": len(outcomes) == 54 and all(item.get("token_accounting", {}).get("requests_usage_incomplete") == 0 for item in outcomes),
            "event_node_budget_consistent": len(outcomes) == 54 and all(_arm_usage_integrity(item) for item in outcomes),
            "no_budget_contract_violation": len(outcomes) == 54 and all(item.get("token_accounting", {}).get("budget_contract_violations") == 0 for item in outcomes),
        }
    )
    behavior_passed = bool(result["behavior_gates"]["primary_noninferiority_and_cost"] or result["behavior_gates"]["alternative_success_improvement"])
    result["passed"] = all(result["hard_gates"].values()) and behavior_passed
    result["decision"] = manifest["qualification"]["pass_decision"] if result["passed"] else manifest["qualification"]["fail_decision"]
    result["provider_totals"] = _totals(outcomes)
    return result


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
    base._check_total_budget = _check_total_budget
    base._formal_qualification = _formal_qualification
    base.validate_manifest = validate_manifest
    base.preflight = preflight
    base.base._token_observation = _token_observation
    base.base._budget_record = _budget_record
    base._activate_base()


def _restore_base() -> None:
    for name, value in _V1_BINDINGS.items():
        setattr(base, name, value)
    _V1_ACTIVATE()


def validate_manifest(manifest: dict[str, Any], *, require_components: bool = True) -> dict[str, Any]:
    frozen_candidate = _load_json(CANDIDATE_MANIFEST_PATH)
    candidate.validate_manifest(frozen_candidate, verify_inventory_files=False)
    if candidate.canonical_sha256(frozen_candidate) != CANDIDATE_MANIFEST_SHA256:
        raise QualificationError("candidate manifest 漂移")
    if manifest.get("identity") != IDENTITY or manifest.get("issue") != TRACKING_ISSUE or manifest.get("branch") != BRANCH:
        raise QualificationError("authorized identity 漂移")
    if manifest.get("status") != "authorized_for_execution" or manifest.get("release_revision") is not None:
        raise QualificationError("authorized status 漂移")
    binding = manifest.get("candidate_binding", {})
    if binding != {
        "identity": "cpp-progress-aware-harness-comparison-v3-candidate",
        "issue": 438,
        "revision": CANDIDATE_REVISION,
        "manifest_path": "benchmarks/manifests/cpp-progress-aware-harness-comparison-v3-candidate.json",
        "manifest_canonical_sha256": CANDIDATE_MANIFEST_SHA256,
        "candidate_mutation_forbidden": True,
    }:
        raise QualificationError("candidate binding 漂移")
    budget = manifest.get("budget", {})
    per_arm = budget.get("per_arm", {})
    if (
        per_arm.get("max_recorded_tokens") != 300_000
        or per_arm.get("max_recorded_tokens_per_response") != 100_000
        or budget.get("provider_arms") != 60
        or budget.get("total_provider_requests") != 1_440
        or budget.get("total_recorded_tokens_stop_threshold") != 18_000_000
        or budget.get("total_authorized_recorded_tokens") != 24_000_000
        or budget.get("total_provider_cost_usd_ceiling") != 28.8
    ):
        raise QualificationError("v3 Provider 预算漂移")
    if manifest.get("provider", {}).get("status") != "authorized":
        raise QualificationError("Provider 授权状态漂移")
    if manifest.get("authorization_record", {}).get("maximum_recorded_tokens") != 24_000_000:
        raise QualificationError("用户授权记录漂移")
    if manifest.get("tasks") != frozen_candidate.get("tasks") or manifest.get("formal_schedule") != frozen_candidate.get("formal_schedule"):
        raise QualificationError("candidate 样本或 schedule 漂移")
    if manifest.get("canary_checkpoints") != frozen_candidate.get("canary_checkpoints"):
        raise QualificationError("candidate canary 漂移")

    legacy = copy.deepcopy(manifest)
    legacy["budget"]["total_recorded_tokens"] = legacy["budget"]["total_recorded_tokens_stop_threshold"]
    legacy["budget"]["total_provider_cost_usd_ceiling"] = 21.6
    _activate_base()
    try:
        _BASE_VALIDATE(legacy, require_components=require_components)
        if require_components:
            if set(manifest.get("components", {})) != set(COMPONENT_PATHS):
                raise QualificationError("冻结组件集合无效")
            for relative, expected in manifest["components"].items():
                if base.base._file_sha256(REPO_ROOT / relative) != expected:
                    raise QualificationError(f"冻结组件漂移: {relative}")
    finally:
        if not _EXECUTION_ACTIVE:
            _restore_base()
    return manifest


def preflight(manifest: dict[str, Any], *, phase: str) -> dict[str, Any]:
    _activate_base()
    result = _BASE_PREFLIGHT(manifest, phase=phase)
    try:
        base.base._git("merge-base", "--is-ancestor", CANDIDATE_REVISION, result["release_revision"])
    except Exception as exc:
        raise QualificationError("正式 release 不包含冻结 candidate revision") from exc
    result["candidate_manifest_sha256"] = CANDIDATE_MANIFEST_SHA256
    return result


def audit(manifest: dict[str, Any], *, seal: bool = False) -> dict[str, Any]:
    _activate_base()
    result = _BASE_AUDIT(manifest, seal=seal)
    result["candidate_manifest_sha256"] = CANDIDATE_MANIFEST_SHA256
    result["metering_contract"] = "events_equals_node_tracker_equals_budget_equals_report"
    return result


def write_report(manifest: dict[str, Any]) -> dict[str, Any]:
    _activate_base()
    report = _BASE_WRITE_REPORT(manifest)
    report["replication"] = manifest["replication"]
    report["candidate_binding"] = manifest["candidate_binding"]
    report["metering"] = report["q2"]["qualification"].get("provider_totals", {})
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown = REPORT_MD_PATH.read_text(encoding="utf-8").replace(
        "进展感知结构化 Harness H0/H1 配对比较 v1 结果",
        "进展感知结构化 Harness H0/H1 v3 确认性复现结果",
        1,
    )
    REPORT_MD_PATH.write_text(markdown, encoding="utf-8")
    return report


def plan(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest, require_components=False)
    return {
        "identity": manifest["identity"],
        "status": manifest["status"],
        "candidate_binding": manifest["candidate_binding"],
        "q0_cases": len(manifest["tasks"]),
        "q1_arms": len(manifest["canary_checkpoints"]) * 2,
        "q2_pairs": len(manifest["formal_schedule"]),
        "q2_arms": len(manifest["formal_schedule"]) * 2,
        "provider_request_ceiling": manifest["budget"]["total_provider_requests"],
        "recorded_token_stop_threshold": manifest["budget"]["total_recorded_tokens_stop_threshold"],
        "recorded_token_authorized_ceiling": manifest["budget"]["total_authorized_recorded_tokens"],
        "provider_cost_usd_ceiling": manifest["budget"]["total_provider_cost_usd_ceiling"],
        "formal_schedule": manifest["formal_schedule"],
    }


def main() -> int:
    global _EXECUTION_ACTIVE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "generate",
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
    if arguments.command == "generate":
        manifest = generate_manifest()
        _write_json(MANIFEST_PATH, manifest)
        _write_json(SCHEMA_PATH, schema_document(manifest))
        payload = {"written": True, "manifest_sha256": base.base._canonical_sha256(manifest)}
    else:
        _EXECUTION_ACTIVE = True
        manifest = _manifest()
        _activate_base()
        if arguments.command == "validate":
            validate_manifest(manifest)
            if _load_json(SCHEMA_PATH) != schema_document(manifest):
                raise QualificationError("const Schema 漂移")
            payload = {"valid": True, "manifest_sha256": base.base._canonical_sha256(manifest)}
        elif arguments.command == "plan":
            payload = plan(manifest)
        elif arguments.command.startswith("preflight-"):
            payload = preflight(manifest, phase=arguments.command.removeprefix("preflight-"))
        elif arguments.command == "q0":
            payload = base.execute_q0(manifest)
        elif arguments.command == "q1":
            payload = base.execute_q1(manifest)
        elif arguments.command == "q2":
            payload = base.execute_q2(manifest)
        elif arguments.command == "audit":
            payload = audit(manifest)
        elif arguments.command == "seal":
            payload = audit(manifest, seal=True)
        else:
            payload = write_report(manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
