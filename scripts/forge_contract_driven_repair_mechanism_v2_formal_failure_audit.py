#!/usr/bin/env python3
"""只读审计 mechanism v2 formal checkpoint 构造失败并冻结脱敏报告。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_contract_driven_repair_mechanism_v2_formal_protocol as protocol  # noqa: E402
from deerflow.compile.evidence import ExperimentLedger  # noqa: E402

SCHEMA_VERSION = "forge-contract-repair-mechanism-v2-formal-failure-audit-1.0.0"
DOCUMENT_TYPE = "forge_contract_repair_mechanism_v2_formal_failure_audit"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/379"
IMPLEMENTATION_PR_URL = "https://github.com/WWFXL/Forge-AutoCompiler/pull/378"
MANIFEST_CANONICAL_SHA256 = (
    "491d877c0d4b94380e4541a23dfd65e7ec83eee2f110d2420c2673597f873609"
)
MANIFEST_FILE_SHA256 = (
    "c655a09a4e60ac8dc6bf3bf2dbcdad9f071bde9d81091ca2ea84f9742385e6cf"
)
RUNNER_FILE_SHA256 = "c4ae111ac7df6e12616e2245ac61b94e2b68abd5d85e321a2b68b6c55e207f77"
FROZEN_ENGINE_FILE_SHA256 = (
    "5bb1797d2a3a5a8c700ba8da5677b195d0c0db969498521df878f669c815e358"
)
RELEASE_REVISION = "fe36cf137dbaa3a0dd29793ae67e74e97a631c61"
AVAILABILITY_MARKER_SHA256 = (
    "73a505f396278eaa93430264fb3ef8d86964891763d242d419e4793b475f21ee"
)
INVENTORY_SHA256 = "5c885b2a9d2bb2156f28913365c73b32d11a60ffcce7804d85d6cae718eb9d11"
EXPECTED_FILE_COUNT = 70
EXPECTED_TOTAL_SIZE_BYTES = 689_742
EXPECTED_COMPLETED_CHECKPOINTS = 4
EXPECTED_COMPLETED_ARMS = 12
EXPECTED_PROVIDER_REQUESTS = 75
EXPECTED_INPUT_TOKENS = 907_258
EXPECTED_OUTPUT_TOKENS = 161_276
EXPECTED_TOTAL_TOKENS = 1_068_534
FAILURE_CHECKPOINT_SEQUENCE = 5
FAILURE_CHECKPOINT_ID = "lz4:delivery_target"
FAILURE_MESSAGE_SHA256 = (
    "8e7adb776b6ef3ff643ebd25b8b3bba91dd94c55814a84b1314e3539207f2dd9"
)

# sequence 对应：(checkpoint、condition、strict、requests、input、output、total、
# model terminal、runtime event count)。
EXPECTED_ARM_OBSERVATIONS = {
    1: (
        "rnnoise-0.1.1:delivery_target",
        "t2",
        True,
        4,
        39_076,
        7_896,
        46_972,
        None,
        33,
    ),
    2: (
        "rnnoise-0.1.1:delivery_target",
        "c0",
        True,
        6,
        61_424,
        8_879,
        70_303,
        None,
        38,
    ),
    3: (
        "rnnoise-0.1.1:delivery_target",
        "t1",
        True,
        6,
        45_754,
        3_674,
        49_428,
        None,
        38,
    ),
    4: (
        "rnnoise-0.1.1:provenance",
        "c0",
        False,
        8,
        167_480,
        28_067,
        195_547,
        "budget_exhausted",
        57,
    ),
    5: (
        "rnnoise-0.1.1:provenance",
        "t1",
        False,
        8,
        141_463,
        26_540,
        168_003,
        "budget_exhausted",
        59,
    ),
    6: (
        "rnnoise-0.1.1:provenance",
        "t2",
        False,
        8,
        91_739,
        19_162,
        110_901,
        "budget_exhausted",
        48,
    ),
    7: (
        "libsoundio:provenance",
        "t1",
        False,
        8,
        109_682,
        28_497,
        138_179,
        "budget_exhausted",
        59,
    ),
    8: (
        "libsoundio:provenance",
        "t2",
        False,
        8,
        70_255,
        7_103,
        77_358,
        "budget_exhausted",
        59,
    ),
    9: (
        "libsoundio:provenance",
        "c0",
        False,
        8,
        109_122,
        20_489,
        129_611,
        "budget_exhausted",
        55,
    ),
    10: ("libsoundio:delivery_target", "t2", True, 4, 27_709, 3_684, 31_393, None, 33),
    11: ("libsoundio:delivery_target", "t1", True, 4, 24_266, 2_170, 26_436, None, 28),
    12: ("libsoundio:delivery_target", "c0", True, 3, 19_288, 5_115, 24_403, None, 23),
}

FORBIDDEN_REPORT_KEYS = frozenset(
    {
        "api_key",
        "capture",
        "command",
        "credential",
        "messages",
        "parent_command_history",
        "prompt",
        "response",
        "session_id",
        "stderr",
        "stdout",
    }
)

DEFAULT_EVIDENCE_DIR = (
    REPO_ROOT
    / ".compile-sessions"
    / "benchmark-evidence-contract-driven-repair-mechanism-v2-independent"
)
DEFAULT_JSON_REPORT = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "cpp-contract-driven-repair-mechanism-v2-formal-failure-audit.json"
)
DEFAULT_MARKDOWN_REPORT = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "cpp-contract-driven-repair-mechanism-v2-formal-failure-audit.md"
)
DEFAULT_SCHEMA = (
    REPO_ROOT
    / "benchmarks"
    / "schemas"
    / "forge-contract-driven-repair-mechanism-v2-formal-failure-audit.schema.json"
)
V2_RUNNER = SCRIPT_ROOT / "forge_contract_driven_repair_mechanism_v2_formal_runner.py"
FROZEN_ENGINE = (
    SCRIPT_ROOT / "forge_contract_driven_repair_mechanism_v1_formal_runner.py"
)


class FormalFailureAuditError(RuntimeError):
    """冻结 formal failure evidence 不满足审计不变量。"""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalFailureAuditError(f"无法读取 {label}") from exc
    if not isinstance(value, dict):
        raise FormalFailureAuditError(f"{label} 顶层必须为对象")
    return value


def _reference(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _inventory_sha256(references: list[dict[str, Any]]) -> str:
    payload = "".join(f"{item['sha256']}  ./{item['path']}\n" for item in references)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _checkpoint_slug(checkpoint: dict[str, Any]) -> str:
    return f"{checkpoint['task_id']}-{checkpoint['stratum']}".replace("_", "-")


def _checkpoint_prefix(checkpoint: dict[str, Any]) -> str:
    return (
        f"checkpoints/{checkpoint['checkpoint_sequence']:02d}-"
        f"{_checkpoint_slug(checkpoint)}"
    )


def _arm_prefix(arm: dict[str, Any]) -> str:
    return f"attempts/{arm['sequence']:02d}-{arm['opaque_clone_id']}"


def _expected_evidence_layout(
    manifest: dict[str, Any],
) -> tuple[set[str], set[str]]:
    files = {"markers/availability.json", "markers/batch.json"}
    directories = {"attempts", "checkpoints", "markers"}
    completed = manifest["schedule"]["checkpoints"][:EXPECTED_COMPLETED_CHECKPOINTS]
    for checkpoint in completed:
        checkpoint_prefix = _checkpoint_prefix(checkpoint)
        directories.add(checkpoint_prefix)
        files.update(
            {
                f"{checkpoint_prefix}/checkpoint.json",
                f"{checkpoint_prefix}/experiment.jsonl",
            }
        )
        for arm in checkpoint["arms"]:
            arm_prefix = _arm_prefix(arm)
            directories.add(arm_prefix)
            files.update(
                {
                    f"{arm_prefix}/attempt.json",
                    f"{arm_prefix}/candidate.json",
                    f"{arm_prefix}/experiment.jsonl",
                    f"{arm_prefix}/result.json",
                    f"{arm_prefix}/runtime-events.jsonl",
                }
            )
    return files, directories


def verify_source_inventory(
    evidence_dir: Path, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise FormalFailureAuditError("冻结 evidence 根不存在或不是普通目录")
    entries = sorted(evidence_dir.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise FormalFailureAuditError("冻结 evidence 不得包含符号链接")

    expected_files, expected_directories = _expected_evidence_layout(manifest)
    observed_files = {
        path.relative_to(evidence_dir).as_posix() for path in entries if path.is_file()
    }
    observed_directories = {
        path.relative_to(evidence_dir).as_posix() for path in entries if path.is_dir()
    }
    if observed_files != expected_files:
        raise FormalFailureAuditError(
            "冻结 evidence 文件集合漂移: "
            f"missing={sorted(expected_files - observed_files)}, "
            f"unexpected={sorted(observed_files - expected_files)}"
        )
    if observed_directories != expected_directories:
        raise FormalFailureAuditError(
            "冻结 evidence 目录集合漂移: "
            f"missing={sorted(expected_directories - observed_directories)}, "
            f"unexpected={sorted(observed_directories - expected_directories)}"
        )

    references = [
        _reference(evidence_dir / relative, evidence_dir)
        for relative in sorted(observed_files)
    ]
    if (
        len(references) != EXPECTED_FILE_COUNT
        or sum(item["size_bytes"] for item in references) != EXPECTED_TOTAL_SIZE_BYTES
    ):
        raise FormalFailureAuditError("冻结 evidence 文件数量或总大小漂移")
    if _inventory_sha256(references) != INVENTORY_SHA256:
        raise FormalFailureAuditError("冻结 evidence inventory SHA-256 漂移")
    return references


def _verify_checkpoint_ledger(
    path: Path, *, stratum: str, rejection_code: str
) -> dict[str, Any]:
    previous_hash = "0" * 64
    events: list[dict[str, Any]] = []
    for sequence, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FormalFailureAuditError("checkpoint ledger JSON 无效") from exc
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            raise FormalFailureAuditError("checkpoint ledger sequence 不连续")
        event_hash = event.get("event_hash")
        body = dict(event)
        body.pop("event_hash", None)
        calculated = hashlib.sha256(
            json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if event.get("previous_hash") != previous_hash or event_hash != calculated:
            raise FormalFailureAuditError("checkpoint ledger hash chain 断裂")
        previous_hash = event_hash
        events.append(event)

    expected_types = [
        "candidate.submit_started",
        "artifact.observed",
        "artifact.observed",
        "candidate.prefreeze_verification_completed",
    ]
    if stratum == "provenance":
        expected_types.append("candidate.provenance_verification_completed")
    expected_types.append("candidate.submit_rejected")
    if [event.get("event_type") for event in events] != expected_types:
        raise FormalFailureAuditError("checkpoint ledger 事件序列漂移")
    if events[-1].get("payload", {}).get("rejection_codes") != [rejection_code]:
        raise FormalFailureAuditError("checkpoint authoritative rejection 漂移")
    return {
        "event_count": len(events),
        "terminal_event": "candidate.submit_rejected",
        "terminal_head_sha256": previous_hash,
    }


def _verify_arm_ledger(path: Path, result_path: Path) -> dict[str, Any]:
    try:
        events = ExperimentLedger.verify_path(path)
    except Exception as exc:
        raise FormalFailureAuditError("arm ledger hash chain 无效") from exc
    result_hash = file_sha256(result_path)
    completions = [
        event for event in events if event["event"] == "experiment.completed"
    ]
    if (
        len(completions) != 1
        or completions[0] is not events[-1]
        or completions[0]["payload"]
        != {"result_sha256": result_hash, "status": "complete"}
    ):
        raise FormalFailureAuditError("arm ledger 终态与 result 未闭合")
    return {
        "event_count": len(events),
        "terminal_event": "experiment.completed",
        "terminal_head_sha256": events[-1]["event_sha256"],
        "result_sha256": result_hash,
    }


def _verify_token_ledger(
    result: dict[str, Any], expected: tuple[Any, ...]
) -> dict[str, int]:
    request_count, expected_input, expected_output, expected_total = expected[3:7]
    ledger = result.get("request_token_ledger")
    if not isinstance(ledger, list) or len(ledger) != request_count:
        raise FormalFailureAuditError("Provider request ledger 数量漂移")
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for sequence, item in enumerate(ledger, 1):
        if (
            not isinstance(item, dict)
            or item.get("request_sequence") != sequence
            or item.get("actual_model") != "deepseek-flash"
            or item.get("model_identity_match") is not True
            or item.get("response_received") is not True
            or item.get("retry_eligible") is not False
            or item.get("tool_side_effect_count") != 0
            or item.get("error_class") is not None
        ):
            raise FormalFailureAuditError("Provider request identity 或顺序漂移")
        values = tuple(item.get(key) for key in totals)
        if any(type(value) is not int or value < 0 for value in values):
            raise FormalFailureAuditError("Provider token 值无效")
        if values[0] + values[1] != values[2]:
            raise FormalFailureAuditError("单请求 token 不闭合")
        for key in totals:
            totals[key] += item[key]
    expected_totals = {
        "input_tokens": expected_input,
        "output_tokens": expected_output,
        "total_tokens": expected_total,
    }
    recorded_totals = {
        "input_tokens": result.get("recorded_input_tokens"),
        "output_tokens": result.get("recorded_output_tokens"),
        "total_tokens": result.get("recorded_total_tokens"),
    }
    if totals != expected_totals or recorded_totals != expected_totals:
        raise FormalFailureAuditError("Provider token 汇总不闭合")
    if result.get("provider_request_attempts") != request_count:
        raise FormalFailureAuditError("Provider request attempt 计数漂移")
    return {"request_attempts": request_count, **totals}


def _require_formal_identity(value: dict[str, Any], label: str) -> None:
    if (
        value.get("manifest_sha256") != MANIFEST_CANONICAL_SHA256
        or value.get("release_revision") != RELEASE_REVISION
    ):
        raise FormalFailureAuditError(f"{label} formal identity 漂移")


def _verify_checkpoint(
    evidence_dir: Path, checkpoint: dict[str, Any]
) -> dict[str, Any]:
    prefix = _checkpoint_prefix(checkpoint)
    marker = _load_json(evidence_dir / f"{prefix}/checkpoint.json", "checkpoint marker")
    rejection_code = (
        "target_mapping_invalid"
        if checkpoint["stratum"] == "delivery_target"
        else "build_system_unproven"
    )
    if (
        marker.get("checkpoint_id") != checkpoint["checkpoint_id"]
        or marker.get("checkpoint_sequence") != checkpoint["checkpoint_sequence"]
        or marker.get("task_id") != checkpoint["task_id"]
        or marker.get("stratum") != checkpoint["stratum"]
        or marker.get("status") != "captured"
        or marker.get("provider_calls") != 0
        or marker.get("formal_attempts") != 0
        or marker.get("formal_manifest_sha256") != MANIFEST_CANONICAL_SHA256
        or marker.get("authoritative_rejection", {})
        .get("response", {})
        .get("rejection_codes")
        != [rejection_code]
        or set(marker.get("feedback_projections", {})) != {"c0", "t1", "t2"}
    ):
        raise FormalFailureAuditError("checkpoint marker 身份或语义漂移")
    functional = marker.get("functional_precheck")
    if checkpoint["stratum"] == "delivery_target":
        if not isinstance(functional, dict) or functional.get("passed") is not True:
            raise FormalFailureAuditError(
                "delivery checkpoint functional precheck 漂移"
            )
    elif functional is not True:
        raise FormalFailureAuditError("provenance checkpoint functional precheck 漂移")
    checkpoint_manifest_sha256 = marker.get("manifest_sha256")
    if (
        not isinstance(checkpoint_manifest_sha256, str)
        or len(checkpoint_manifest_sha256) != 64
    ):
        raise FormalFailureAuditError("checkpoint state manifest SHA-256 无效")
    return {
        "checkpoint_sequence": checkpoint["checkpoint_sequence"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "task_id": checkpoint["task_id"],
        "stratum": checkpoint["stratum"],
        "status": "captured",
        "provider_calls_before_capture": 0,
        "formal_attempts_before_capture": 0,
        "authoritative_rejection_code": rejection_code,
        "functional_precheck_passed": True,
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
        "checkpoint_marker_sha256": file_sha256(
            evidence_dir / f"{prefix}/checkpoint.json"
        ),
        "ledger": _verify_checkpoint_ledger(
            evidence_dir / f"{prefix}/experiment.jsonl",
            stratum=checkpoint["stratum"],
            rejection_code=rejection_code,
        ),
        "captured_at": marker["captured_at"],
    }


def _verify_arm(
    evidence_dir: Path,
    checkpoint: dict[str, Any],
    arm: dict[str, Any],
) -> dict[str, Any]:
    sequence = arm["sequence"]
    expected = EXPECTED_ARM_OBSERVATIONS.get(sequence)
    if expected is None:
        raise FormalFailureAuditError(f"unexpected completed arm sequence: {sequence}")
    if checkpoint["checkpoint_id"] != expected[0] or arm["condition"] != expected[1]:
        raise FormalFailureAuditError("manifest schedule 与冻结 observation 漂移")
    prefix = _arm_prefix(arm)
    attempt = _load_json(evidence_dir / f"{prefix}/attempt.json", "attempt marker")
    result_path = evidence_dir / f"{prefix}/result.json"
    result = _load_json(result_path, "arm result")
    _require_formal_identity(attempt, "attempt marker")
    _require_formal_identity(result, "arm result")
    if (
        attempt.get("sequence") != sequence
        or attempt.get("checkpoint_id") != checkpoint["checkpoint_id"]
        or attempt.get("opaque_clone_id") != arm["opaque_clone_id"]
        or attempt.get("status") != "complete"
        or attempt.get("error_class") is not None
    ):
        raise FormalFailureAuditError("attempt marker 终态漂移")
    if (
        result.get("sequence") != sequence
        or result.get("checkpoint_id") != checkpoint["checkpoint_id"]
        or result.get("task_id") != checkpoint["task_id"]
        or result.get("stratum") != checkpoint["stratum"]
        or result.get("condition") != arm["condition"]
        or result.get("opaque_clone_id") != arm["opaque_clone_id"]
        or result.get("opaque_evaluation_id") != arm["opaque_evaluation_id"]
        or result.get("status") != "complete"
        or result.get("error_class") is not None
        or result.get("cleanup_closed") is not True
        or result.get("zero_managed_orphans") is not True
        or result.get("model_behavior_terminal") != expected[7]
    ):
        raise FormalFailureAuditError("arm result 身份或终态漂移")

    strict = expected[2]
    required_endpoint_fields = (
        "candidate_accepted",
        "functional_oracle_passed",
        "provenance_passed",
        "external_evaluator_v3_passed",
        "clean_replay_passed",
    )
    if result.get("strict_post_checkpoint_conversion") is not strict:
        raise FormalFailureAuditError("arm strict endpoint 漂移")
    if strict:
        if any(result.get(field) is not True for field in required_endpoint_fields):
            raise FormalFailureAuditError("strict arm endpoint layer 未闭合")
        s0_s5 = result.get("s0_s5")
        if (
            not isinstance(s0_s5, list)
            or [item.get("layer") for item in s0_s5]
            != ["S0", "S1", "S2", "S3", "S4", "S5"]
            or any(item.get("status") != "passed" for item in s0_s5)
        ):
            raise FormalFailureAuditError("strict arm S0-S5 漂移")
    elif (
        any(result.get(field) is not False for field in required_endpoint_fields)
        or result.get("s0_s5") != []
    ):
        raise FormalFailureAuditError("budget-exhausted arm outcome 漂移")

    tokens = _verify_token_ledger(result, expected)
    runtime_event_count = len(
        (evidence_dir / f"{prefix}/runtime-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    if runtime_event_count != expected[8]:
        raise FormalFailureAuditError("runtime event 数量漂移")
    return {
        "sequence": sequence,
        "checkpoint_id": checkpoint["checkpoint_id"],
        "task_id": checkpoint["task_id"],
        "stratum": checkpoint["stratum"],
        "condition": arm["condition"],
        "status": "complete",
        "strict_post_checkpoint_conversion": strict,
        "model_behavior_terminal": expected[7],
        "candidate_accepted": strict,
        "functional_oracle_passed": strict,
        "provenance_passed": strict,
        "external_evaluator_v3_passed": strict,
        "clean_replay_passed": strict,
        "cleanup_closed": True,
        "zero_managed_orphans": True,
        "s0_s5_passed": 6 if strict else 0,
        "tokens": tokens,
        "result_sha256": file_sha256(result_path),
        "ledger": _verify_arm_ledger(
            evidence_dir / f"{prefix}/experiment.jsonl", result_path
        ),
        "runtime_event_count": runtime_event_count,
        "completed_at": result["completed_at"],
    }


def _fraction(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def _build_descriptive_analysis(
    arm_results: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    outcomes = {
        (item["checkpoint_id"], item["condition"]): int(
            item["strict_post_checkpoint_conversion"]
        )
        for item in arm_results
    }
    projects: list[dict[str, Any]] = []
    comparisons = {
        "c0_vs_t1": ("t1", "c0"),
        "t1_vs_t2": ("t2", "t1"),
        "c0_vs_t2": ("t2", "c0"),
    }
    for task_id in ("rnnoise-0.1.1", "libsoundio"):
        checkpoint_outcomes: dict[str, dict[str, int]] = {}
        for stratum in ("delivery_target", "provenance"):
            checkpoint_id = f"{task_id}:{stratum}"
            checkpoint_outcomes[stratum] = {
                condition: outcomes[(checkpoint_id, condition)]
                for condition in ("c0", "t1", "t2")
            }
        scores = {}
        for comparison, (treatment, control) in comparisons.items():
            deltas = [
                checkpoint_outcomes[stratum][treatment]
                - checkpoint_outcomes[stratum][control]
                for stratum in ("delivery_target", "provenance")
            ]
            scores[comparison] = _fraction(Fraction(sum(deltas), len(deltas)))
        projects.append(
            {
                "task_id": task_id,
                "checkpoint_outcomes": checkpoint_outcomes,
                "project_scores": scores,
            }
        )

    scheduled_checkpoint_count = len(manifest["schedule"]["checkpoints"])
    completed_checkpoint_count = len(arm_results) // 3
    missing_checkpoint_count = scheduled_checkpoint_count - completed_checkpoint_count
    bound = Fraction(missing_checkpoint_count, scheduled_checkpoint_count)
    comparison_summaries = {
        comparison: {
            "observed_complete_project_count": len(projects),
            "observed_complete_estimate": "0",
            "best_worst_identification_interval": {
                "lower": _fraction(-bound),
                "upper": _fraction(bound),
            },
        }
        for comparison in comparisons
    }
    return {
        "status": "incomplete_batch_descriptive_only",
        "scheduled_project_count": 6,
        "observed_complete_project_count": 2,
        "scheduled_checkpoint_count": scheduled_checkpoint_count,
        "observed_complete_checkpoint_count": completed_checkpoint_count,
        "missing_checkpoint_count": missing_checkpoint_count,
        "projects": projects,
        "comparisons": comparison_summaries,
        "primary_test": None,
        "secondary_test": None,
        "supportive_confirmatory_test": None,
        "p_value_computed": False,
        "missing_arms_imputed_as_zero": False,
        "treatment_effect_estimated": False,
    }


def _validate_report_sanitization(report: dict[str, Any]) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            forbidden = FORBIDDEN_REPORT_KEYS & set(value)
            if forbidden:
                raise FormalFailureAuditError(f"报告包含禁止字段: {sorted(forbidden)}")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(report)
    serialized = json.dumps(report, ensure_ascii=False)
    if any(
        value in serialized for value in ("/home/", "/workspace/", "api.deepseek.com")
    ):
        raise FormalFailureAuditError("报告包含宿主、容器或 endpoint 细节")


def _verify_failure_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    if file_sha256(V2_RUNNER) != RUNNER_FILE_SHA256:
        raise FormalFailureAuditError("v2 formal runner SHA-256 漂移")
    if file_sha256(FROZEN_ENGINE) != FROZEN_ENGINE_FILE_SHA256:
        raise FormalFailureAuditError("frozen formal engine SHA-256 漂移")
    engine_source = FROZEN_ENGINE.read_text(encoding="utf-8")
    required_fragments = (
        "def _compiled_target_path(",
        "if len(compiled) != 1:",
        "必须恰有一个 target-mapped compiled artifact",
        "target_path = _compiled_target_path(task, parent)",
    )
    if any(fragment not in engine_source for fragment in required_fragments):
        raise FormalFailureAuditError("frozen engine failure path 漂移")
    failure_checkpoint = manifest["schedule"]["checkpoints"][
        FAILURE_CHECKPOINT_SEQUENCE - 1
    ]
    if failure_checkpoint["checkpoint_id"] != FAILURE_CHECKPOINT_ID:
        raise FormalFailureAuditError("failure checkpoint identity 漂移")
    tasks = {task["task_id"]: task for task in manifest["formal_execution_tasks"]}
    lz4_contract = tasks["lz4"]["target_contract"]
    compiled_targets = ["bin/lz4", "lib/liblz4.a"]
    if lz4_contract.get("required_artifacts") != [
        "bin/lz4",
        "include/lz4.h",
        "lib/liblz4.a",
    ] or not set(compiled_targets).issubset(lz4_contract["required_artifacts"]):
        raise FormalFailureAuditError("lz4 multi-target contract 漂移")
    return {
        "classification": "checkpoint_target_mapping_cardinality_failure",
        "exception_class": "FormalFatalError",
        "exception_message_sha256": FAILURE_MESSAGE_SHA256,
        "phase": "checkpoint_5_parent_capture_before_checkpoint_marker_ledger_or_sequence_13_attempt",
        "checkpoint_sequence": FAILURE_CHECKPOINT_SEQUENCE,
        "checkpoint_id": FAILURE_CHECKPOINT_ID,
        "task_id": "lz4",
        "stratum": "delivery_target",
        "required_compiled_target_cardinality": 1,
        "frozen_contract_compiled_targets": compiled_targets,
        "frozen_contract_compiled_target_cardinality": len(compiled_targets),
        "root_cause": "frozen_checkpoint_builder_requires_one_compiled_target_but_lz4_contract_requires_executable_and_static_library",
        "checkpoint_evidence_created": False,
        "sequence_13_attempt_created": False,
    }


def build_report(evidence_dir: Path = DEFAULT_EVIDENCE_DIR) -> dict[str, Any]:
    manifest = protocol.load_manifest()
    if canonical_sha256(manifest) != MANIFEST_CANONICAL_SHA256:
        raise FormalFailureAuditError("formal manifest canonical SHA-256 漂移")
    if file_sha256(protocol.DEFAULT_MANIFEST) != MANIFEST_FILE_SHA256:
        raise FormalFailureAuditError("formal manifest 文件 SHA-256 漂移")
    references = verify_source_inventory(evidence_dir, manifest)

    availability_path = evidence_dir / "markers/availability.json"
    availability = _load_json(availability_path, "availability marker")
    if (
        file_sha256(availability_path) != AVAILABILITY_MARKER_SHA256
        or availability.get("status") != "passed"
        or availability.get("request_attempt_count") != 1
        or availability.get("recorded_total_tokens") != 158
    ):
        raise FormalFailureAuditError("availability marker 漂移")

    batch_path = evidence_dir / "markers/batch.json"
    batch = _load_json(batch_path, "batch marker")
    _require_formal_identity(batch, "batch marker")
    if (
        batch.get("status") != "failed"
        or batch.get("error_class") != "FormalFatalError"
        or batch.get("completed_checkpoint_count") != EXPECTED_COMPLETED_CHECKPOINTS
        or batch.get("completed_arm_count") != EXPECTED_COMPLETED_ARMS
        or batch.get("last_completed_sequence") != EXPECTED_COMPLETED_ARMS
        or batch.get("provider_request_attempt_count") != EXPECTED_PROVIDER_REQUESTS
        or batch.get("endpoint_censored_arm_count") != 0
    ):
        raise FormalFailureAuditError("batch failure marker 漂移")

    completed_checkpoints = manifest["schedule"]["checkpoints"][
        :EXPECTED_COMPLETED_CHECKPOINTS
    ]
    checkpoint_results = [
        _verify_checkpoint(evidence_dir, checkpoint)
        for checkpoint in completed_checkpoints
    ]
    arm_results = [
        _verify_arm(evidence_dir, checkpoint, arm)
        for checkpoint in completed_checkpoints
        for arm in checkpoint["arms"]
    ]
    aggregate_tokens = {
        "request_attempts": sum(
            item["tokens"]["request_attempts"] for item in arm_results
        ),
        "input_tokens": sum(item["tokens"]["input_tokens"] for item in arm_results),
        "output_tokens": sum(item["tokens"]["output_tokens"] for item in arm_results),
        "total_tokens": sum(item["tokens"]["total_tokens"] for item in arm_results),
    }
    if aggregate_tokens != {
        "request_attempts": EXPECTED_PROVIDER_REQUESTS,
        "input_tokens": EXPECTED_INPUT_TOKENS,
        "output_tokens": EXPECTED_OUTPUT_TOKENS,
        "total_tokens": EXPECTED_TOTAL_TOKENS,
    }:
        raise FormalFailureAuditError("formal batch token 汇总漂移")

    report = {
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "issue_url": ISSUE_URL,
        "identity": {
            "release_revision": RELEASE_REVISION,
            "implementation_pr_url": IMPLEMENTATION_PR_URL,
            "manifest_path": protocol.DEFAULT_MANIFEST.relative_to(
                REPO_ROOT
            ).as_posix(),
            "manifest_canonical_sha256": MANIFEST_CANONICAL_SHA256,
            "manifest_file_sha256": MANIFEST_FILE_SHA256,
            "v2_runner_file_sha256": RUNNER_FILE_SHA256,
            "frozen_engine_file_sha256": FROZEN_ENGINE_FILE_SHA256,
            "source_evidence_root": ".compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent",
        },
        "source_integrity": {
            "file_count": len(references),
            "total_size_bytes": sum(item["size_bytes"] for item in references),
            "inventory_sha256": _inventory_sha256(references),
            "files": references,
            "source_evidence_modified": False,
        },
        "availability_receipt": {
            "status": "passed_consumed_read_only",
            "marker_sha256": AVAILABILITY_MARKER_SHA256,
            "request_attempt_count": 1,
            "recorded_total_tokens": 158,
            "rerun_allowed": False,
        },
        "batch_terminal": {
            "status": "failed",
            "error_class": "FormalFatalError",
            "scheduled_checkpoint_count": 12,
            "scheduled_arm_count": 36,
            "completed_checkpoint_count": EXPECTED_COMPLETED_CHECKPOINTS,
            "completed_arm_count": EXPECTED_COMPLETED_ARMS,
            "unstarted_checkpoint_count": 8,
            "unstarted_arm_count": 24,
            "last_completed_sequence": EXPECTED_COMPLETED_ARMS,
            "endpoint_censored_arm_count": 0,
            "tokens": aggregate_tokens,
            "batch_marker_sha256": file_sha256(batch_path),
            "started_at": batch["started_at"],
            "stopped_at": batch["stopped_at"],
        },
        "checkpoints": checkpoint_results,
        "arms": arm_results,
        "failure": _verify_failure_contract(manifest),
        "analysis": _build_descriptive_analysis(arm_results, manifest),
        "execution_boundary": {
            "identity_terminal_failed": True,
            "zero_managed_containers_observed_after_failure": True,
            "zero_capture_images_observed_after_failure": True,
            "symlinks_or_temporary_files_observed": False,
            "continuation_allowed": False,
            "rerun_allowed": False,
            "retry_allowed": False,
            "replacement_allowed": False,
            "backfill_allowed": False,
            "schedule_extension_allowed": False,
            "marker_repair_allowed": False,
            "provider_call_authorized_for_audit": False,
            "credential_read_authorized_for_audit": False,
            "formal_evidence_write_authorized_for_audit": False,
        },
        "interpretation": {
            "analysis_kind": "incomplete_formal_batch_infrastructure_failure_audit",
            "supported_claims": [
                "twelve_arms_and_four_matched_checkpoints_completed_before_the_infrastructure_failure",
                "delivery_target_was_one_for_all_three_arms_and_provenance_was_zero_for_all_three_arms_in_each_of_two_complete_projects",
                "all_observed_pairwise_project_scores_are_zero_and_the_incomplete_data_identification_interval_is_minus_two_thirds_to_plus_two_thirds",
                "the_batch_stopped_during_lz4_checkpoint_construction_before_sequence_13",
                "the_failure_is_a_single_target_checkpoint_builder_incompatibility_with_the_lz4_multi_target_contract",
                "cleanup_left_zero_managed_containers_and_capture_images",
            ],
            "unsupported_claims": [
                "c0_vs_t1_or_t1_vs_t2_treatment_effect",
                "statistical_significance_or_confirmatory_p_value",
                "absence_or_presence_of_a_practically_meaningful_effect",
                "population_success_rate_provider_reliability_or_model_ranking",
                "permission_to_continue_rerun_replace_backfill_or_repair_the_failed_identity",
            ],
            "model_ranking_performed": False,
        },
        "next_decision": "choose_between_engineering_repair_with_a_new_independent_identity_or_stopping_formal_collection",
    }
    _validate_report_sanitization(report)
    return report


def generate_schema(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://forge-autocompiler.local/schemas/forge-contract-driven-repair-mechanism-v2-formal-failure-audit.schema.json",
        "title": "Forge Contract Repair Mechanism v2 Formal Failure Audit",
        "const": report,
    }


def render_markdown(report: dict[str, Any]) -> str:
    batch = report["batch_terminal"]
    failure = report["failure"]
    analysis = report["analysis"]
    arm_rows = "\n".join(
        "| {sequence} | `{checkpoint_id}` | {condition} | {strict} | {requests} | "
        "{input_tokens:,} | {output_tokens:,} | {total_tokens:,} | {terminal} |".format(
            sequence=arm["sequence"],
            checkpoint_id=arm["checkpoint_id"],
            condition=arm["condition"].upper(),
            strict="1" if arm["strict_post_checkpoint_conversion"] else "0",
            requests=arm["tokens"]["request_attempts"],
            input_tokens=arm["tokens"]["input_tokens"],
            output_tokens=arm["tokens"]["output_tokens"],
            total_tokens=arm["tokens"]["total_tokens"],
            terminal=arm["model_behavior_terminal"] or "success",
        )
        for arm in report["arms"]
    )
    project_rows = "\n".join(
        "| {task} | {delivery} | {provenance} | {d01} | {d12} | {d02} |".format(
            task=project["task_id"],
            delivery="/".join(
                str(project["checkpoint_outcomes"]["delivery_target"][condition])
                for condition in ("c0", "t1", "t2")
            ),
            provenance="/".join(
                str(project["checkpoint_outcomes"]["provenance"][condition])
                for condition in ("c0", "t1", "t2")
            ),
            d01=project["project_scores"]["c0_vs_t1"],
            d12=project["project_scores"]["t1_vs_t2"],
            d02=project["project_scores"]["c0_vs_t2"],
        )
        for project in analysis["projects"]
    )
    interval = analysis["comparisons"]["c0_vs_t1"]["best_worst_identification_interval"]
    return f"""# 契约驱动修复 mechanism v2 formal checkpoint 构造失败审计

> 本报告从 {report["source_integrity"]["file_count"]} 个 create-once 文件只读复算；原始 evidence 未修改。当前是 12/36 arms 的不完整 batch，不构成 treatment effect 证据。

## 身份与完整性

- 执行 release：`{report["identity"]["release_revision"]}`。
- Manifest canonical SHA-256：`{report["identity"]["manifest_canonical_sha256"]}`。
- Evidence：{report["source_integrity"]["file_count"]} files / {report["source_integrity"]["total_size_bytes"]:,} bytes；inventory SHA-256 `{report["source_integrity"]["inventory_sha256"]}`。
- Batch：`failed`，完成 {batch["completed_checkpoint_count"]}/12 checkpoints、{batch["completed_arm_count"]}/36 arms，75 requests / {batch["tokens"]["total_tokens"]:,} total tokens。
- 失败后只读资源核验：0 managed containers / 0 capture images；无 symlink、`.tmp` 或 partial evidence。

## 已完成 Arms

| Seq | Checkpoint | Arm | Strict | Requests | Input | Output | Total | Terminal |
|---:|---|---|---:|---:|---:|---:|---:|---|
{arm_rows}

12 个 attempt marker 均为 `complete`，result 与末尾 `experiment.completed` ledger event 相互绑定；所有 arm 均完成 cleanup 且记录 0 managed orphan。严格成功的 6 个 arm 还闭合 candidate、functional oracle、provenance、external evaluator v3、clean replay 与 S0-S5；其余 6 个 arm 是预注册的模型行为 `budget_exhausted` 零 outcome。

## 不完整数据描述

下表 outcome 顺序均为 `C0/T1/T2`。`d01=T1-C0`、`d12=T2-T1`、`d02=T2-C0`，project score 是两个 stratum delta 的均值。

| Project | delivery/target | provenance | d01 | d12 | d02 |
|---|---|---|---:|---:|---:|
{project_rows}

两个完整项目的三个 observed-complete estimate 都是 `0`。余下 8/12 checkpoints 不填零；按预注册最不利/最有利赋值，三个比较的 identification interval 均为 `[{interval["lower"]}, +{interval["upper"]}]`。由于相关 arm 不完整，`primary_test=null`、`secondary_test=null`，支持性比较也不产生确认性检验或 p 值。

## 失败与终态

Batch 在 checkpoint {failure["checkpoint_sequence"]} `{failure["checkpoint_id"]}` 的 parent capture 阶段以 `{failure["exception_class"]}` 停止。冻结 engine 的 `_compiled_target_path` 要求恰有 1 个 target-mapped compiled artifact，而冻结 `lz4` 合同同时要求 executable `bin/lz4` 和 static library `lib/liblz4.a`，因此 checkpoint builder 与多 target 合同不兼容。

- 故障发生在 checkpoint marker/ledger 与 sequence 13 attempt 创建前；
- batch marker 已以 `failed` 封口，24 arms 保持未运行；
- 当前 identity 永久终止，不允许 continuation、rerun、retry、replacement、backfill、schedule extension 或 marker 修补。

## 解释边界与下一决策

本审计支持两个完整项目中 delivery/target 三臂全为 1、provenance 三臂全为 0，也支持所有 observed project score 为零。由于只完成 2/6 projects 且 identification interval 为 `[-2/3, +2/3]`，它不支持“存在或不存在有意义效应”、显著性、总体成功率、Provider 可靠性或模型排名。

下一项研究决策是在“先修复 checkpoint builder 并建立全新独立 identity”与“停止 formal collection”之间选择；任何后续方案都不得修改或导入本 batch 的冻结 evidence。
"""


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def generate() -> dict[str, Any]:
    report = build_report()
    _write_json(DEFAULT_JSON_REPORT, report)
    _write_json(DEFAULT_SCHEMA, generate_schema(report))
    DEFAULT_MARKDOWN_REPORT.write_text(
        render_markdown(report), encoding="utf-8", newline="\n"
    )
    return report


def validate() -> dict[str, Any]:
    expected = build_report()
    report = _load_json(DEFAULT_JSON_REPORT, "committed audit report")
    schema = _load_json(DEFAULT_SCHEMA, "committed audit schema")
    if report != expected:
        raise FormalFailureAuditError("committed audit report 与冻结 evidence 不一致")
    if schema != generate_schema(report):
        raise FormalFailureAuditError("committed audit schema 不是确定性 const Schema")
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(report)
    if DEFAULT_MARKDOWN_REPORT.read_text(encoding="utf-8") != render_markdown(report):
        raise FormalFailureAuditError("committed Markdown report 漂移")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "audit"))
    args = parser.parse_args(argv)
    report = generate() if args.command == "generate" else validate()
    print(
        json.dumps(
            {
                "status": "passed",
                "classification": report["failure"]["classification"],
                "file_count": report["source_integrity"]["file_count"],
                "inventory_sha256": report["source_integrity"]["inventory_sha256"],
                "completed_arm_results": report["batch_terminal"][
                    "completed_arm_count"
                ],
                "formal_provider_request_attempts": report["batch_terminal"]["tokens"][
                    "request_attempts"
                ],
                "formal_total_tokens": report["batch_terminal"]["tokens"][
                    "total_tokens"
                ],
                "primary_test": None,
                "secondary_test": None,
                "treatment_effect_estimated": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
