#!/usr/bin/env python3
"""对 verifier-driven repair pilot attempt summaries 做配对描述性分析。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_verifier_repair_pilot_protocol as protocol  # noqa: E402
import forge_verifier_repair_runtime as repair_runtime  # noqa: E402

REQUIRED_ATTEMPT_FIELDS = {
    "order",
    "pair_id",
    "case_id",
    "provider_condition",
    "treatment",
    "repetition",
    "oracle_passed",
    "terminal_passed",
    "fidelity_status",
    "recorded_tokens",
    "model_requests",
    "wall_clock_seconds",
    "actionable_verifier_failures",
    "repair_conversions",
    "submit_attempts",
    "clean_replay_attempts",
    "failure_transitions",
}


class AnalyzerError(ValueError):
    pass


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalyzerError(f"cannot read JSON: {path}") from exc


def _validate_attempt(attempt: Any, slot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(attempt, dict) or set(attempt) != REQUIRED_ATTEMPT_FIELDS:
        raise AnalyzerError(
            "attempt summary fields do not match the frozen analyzer contract"
        )
    for field in (
        "order",
        "pair_id",
        "case_id",
        "provider_condition",
        "treatment",
        "repetition",
    ):
        if attempt[field] != slot[field]:
            raise AnalyzerError(f"attempt summary identity drifted: {field}")
    if (
        type(attempt["oracle_passed"]) is not bool
        or type(attempt["terminal_passed"]) is not bool
    ):
        raise AnalyzerError("attempt outcomes must be boolean")
    if attempt["fidelity_status"] not in {"passed", "not_exposed", "failed"}:
        raise AnalyzerError("attempt fidelity status is invalid")
    for field in (
        "recorded_tokens",
        "model_requests",
        "actionable_verifier_failures",
        "repair_conversions",
        "submit_attempts",
        "clean_replay_attempts",
    ):
        if type(attempt[field]) is not int or attempt[field] < 0:
            raise AnalyzerError(f"attempt {field} must be a non-negative integer")
    if attempt["repair_conversions"] > attempt["actionable_verifier_failures"]:
        raise AnalyzerError(
            "repair conversions cannot exceed actionable verifier failures"
        )
    transitions = attempt["failure_transitions"]
    if not isinstance(transitions, list) or len(transitions) > 64:
        raise AnalyzerError("attempt failure transitions are invalid")
    for transition in transitions:
        if not isinstance(transition, dict) or set(transition) != {"from", "to"}:
            raise AnalyzerError("attempt failure transition fields are invalid")
        for field in ("from", "to"):
            value = transition[field]
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 160
                or any(
                    character
                    not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
                    for character in value
                )
            ):
                raise AnalyzerError("attempt failure transition value is invalid")
    wall_clock = attempt["wall_clock_seconds"]
    if (
        not isinstance(wall_clock, (int, float))
        or isinstance(wall_clock, bool)
        or wall_clock < 0
    ):
        raise AnalyzerError("attempt wall_clock_seconds must be non-negative")
    return attempt


def _outcome_label(baseline: bool, treatment: bool) -> str:
    if baseline and treatment:
        return "both_passed"
    if baseline:
        return "baseline_only_passed"
    if treatment:
        return "treatment_only_passed"
    return "neither_passed"


def _count_metric(
    baseline: dict[str, Any], treatment: dict[str, Any], field: str
) -> dict[str, int]:
    return {
        "baseline": baseline[field],
        "treatment": treatment[field],
        "delta": treatment[field] - baseline[field],
    }


def _transition_counts(attempts: list[dict[str, Any]], arm: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for attempt in attempts:
        if attempt["treatment"] != arm:
            continue
        for transition in attempt["failure_transitions"]:
            label = f"{transition['from']}->{transition['to']}"
            counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _conversion_summary(attempts: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    selected = [attempt for attempt in attempts if attempt["treatment"] == arm]
    actionable = sum(attempt["actionable_verifier_failures"] for attempt in selected)
    conversions = sum(attempt["repair_conversions"] for attempt in selected)
    return {
        "actionable_failures": actionable,
        "conversions": conversions,
        "rate": round(conversions / actionable, 6) if actionable else None,
    }


def build_report(
    manifest: dict[str, Any], attempts: list[dict[str, Any]]
) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    slots_by_order = {slot["order"]: slot for slot in manifest["pilot_schedule"]}
    observed: dict[int, dict[str, Any]] = {}
    for raw_attempt in attempts:
        order = raw_attempt.get("order") if isinstance(raw_attempt, dict) else None
        if order not in slots_by_order or order in observed:
            raise AnalyzerError("attempt summary has an unknown or duplicate order")
        observed[order] = _validate_attempt(raw_attempt, slots_by_order[order])

    pairs: list[dict[str, Any]] = []
    incomplete_pairs: list[str] = []
    for pair_id in sorted({slot["pair_id"] for slot in manifest["pilot_schedule"]}):
        pair_slots = sorted(
            (slot for slot in manifest["pilot_schedule"] if slot["pair_id"] == pair_id),
            key=lambda slot: slot["order"],
        )
        pair_attempts = [observed.get(slot["order"]) for slot in pair_slots]
        if any(attempt is None for attempt in pair_attempts):
            incomplete_pairs.append(pair_id)
            continue
        by_arm = {
            attempt["treatment"]: attempt
            for attempt in pair_attempts
            if attempt is not None
        }
        if set(by_arm) != {repair_runtime.BASELINE_ARM, repair_runtime.TREATMENT_ARM}:
            raise AnalyzerError(
                "complete pair does not contain exactly one attempt per arm"
            )
        baseline = by_arm[repair_runtime.BASELINE_ARM]
        treatment = by_arm[repair_runtime.TREATMENT_ARM]
        pairs.append(
            {
                "pair_id": pair_id,
                "case_id": baseline["case_id"],
                "provider_condition": baseline["provider_condition"],
                "oracle_outcome": _outcome_label(
                    baseline["oracle_passed"], treatment["oracle_passed"]
                ),
                "terminal_outcome": _outcome_label(
                    baseline["terminal_passed"], treatment["terminal_passed"]
                ),
                "fidelity_eligible": baseline["fidelity_status"] != "failed"
                and treatment["fidelity_status"] != "failed",
                "actionable_verifier_failures": _count_metric(
                    baseline, treatment, "actionable_verifier_failures"
                ),
                "repair_conversions": _count_metric(
                    baseline, treatment, "repair_conversions"
                ),
                "false_acceptance": {
                    "baseline": baseline["terminal_passed"]
                    and not baseline["oracle_passed"],
                    "treatment": treatment["terminal_passed"]
                    and not treatment["oracle_passed"],
                },
                "submit_attempts": _count_metric(
                    baseline, treatment, "submit_attempts"
                ),
                "clean_replay_attempts": _count_metric(
                    baseline, treatment, "clean_replay_attempts"
                ),
                "failure_transitions": {
                    "baseline": baseline["failure_transitions"],
                    "treatment": treatment["failure_transitions"],
                },
                "recorded_tokens_delta": treatment["recorded_tokens"]
                - baseline["recorded_tokens"],
                "model_requests_delta": treatment["model_requests"]
                - baseline["model_requests"],
                "wall_clock_seconds_delta": round(
                    treatment["wall_clock_seconds"] - baseline["wall_clock_seconds"], 6
                ),
            }
        )

    oracle_counts = {
        label: sum(pair["oracle_outcome"] == label for pair in pairs)
        for label in (
            "both_passed",
            "baseline_only_passed",
            "treatment_only_passed",
            "neither_passed",
        )
    }
    complete_attempts = [
        observed[slot["order"]]
        for pair in pairs
        for slot in manifest["pilot_schedule"]
        if slot["pair_id"] == pair["pair_id"]
    ]
    baseline_attempts = [
        attempt
        for attempt in complete_attempts
        if attempt["treatment"] == repair_runtime.BASELINE_ARM
    ]
    treatment_attempts = [
        attempt
        for attempt in complete_attempts
        if attempt["treatment"] == repair_runtime.TREATMENT_ARM
    ]
    return {
        "report_version": "verifier-driven-repair-pilot-descriptive-1.0.0",
        "manifest_sha256": protocol.manifest_sha256(manifest),
        "scope": {
            "descriptive_only": True,
            "p_value_computed": False,
            "model_ranking_performed": False,
            "paired_primary_eligible": len(pairs) == 6
            and not incomplete_pairs
            and all(pair["fidelity_eligible"] for pair in pairs),
        },
        "collection": {
            "planned_slots": 12,
            "observed_slots": len(observed),
            "complete_pairs": len(pairs),
            "incomplete_pairs": incomplete_pairs,
        },
        "oracle_discordance": oracle_counts,
        "secondary_outcomes": {
            "repair_conversion": {
                "baseline": _conversion_summary(
                    complete_attempts, repair_runtime.BASELINE_ARM
                ),
                "treatment": _conversion_summary(
                    complete_attempts, repair_runtime.TREATMENT_ARM
                ),
            },
            "false_acceptance_count": {
                "baseline": sum(
                    attempt["terminal_passed"] and not attempt["oracle_passed"]
                    for attempt in baseline_attempts
                ),
                "treatment": sum(
                    attempt["terminal_passed"] and not attempt["oracle_passed"]
                    for attempt in treatment_attempts
                ),
            },
            "submit_attempts": {
                "baseline": sum(
                    attempt["submit_attempts"] for attempt in baseline_attempts
                ),
                "treatment": sum(
                    attempt["submit_attempts"] for attempt in treatment_attempts
                ),
            },
            "clean_replay_attempts": {
                "baseline": sum(
                    attempt["clean_replay_attempts"] for attempt in baseline_attempts
                ),
                "treatment": sum(
                    attempt["clean_replay_attempts"] for attempt in treatment_attempts
                ),
            },
            "failure_transitions": {
                "baseline": _transition_counts(
                    complete_attempts, repair_runtime.BASELINE_ARM
                ),
                "treatment": _transition_counts(
                    complete_attempts, repair_runtime.TREATMENT_ARM
                ),
            },
        },
        "pairs": pairs,
        "limitations": [
            "The pilot has one repetition per case-provider pair and does not estimate a population effect.",
            "Endpoint and infrastructure failures remain descriptive and are not attributed to verifier feedback.",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=protocol.DEFAULT_MANIFEST)
    parser.add_argument("--attempts", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = protocol.validate_manifest(_load_json(args.manifest))
        attempts = _load_json(args.attempts)
        if not isinstance(attempts, list):
            raise AnalyzerError("attempts document must be an array")
        report = build_report(manifest, attempts)
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
    except (AnalyzerError, OSError, protocol.ProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
