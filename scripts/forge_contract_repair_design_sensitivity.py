#!/usr/bin/env python3
"""复算契约驱动修复候选设计的 exact paired-test sensitivity。"""

from __future__ import annotations

import argparse
import json
from math import comb
from typing import Any

SCHEMA_VERSION = "forge-contract-repair-design-sensitivity-1.0.0"
ALPHA = 0.05
TARGET_POWER = 0.80


def exact_two_sided_binomial_p(beneficial: int, discordant: int) -> float:
    if discordant < 0 or beneficial < 0 or beneficial > discordant:
        raise ValueError("beneficial and discordant counts are invalid")
    if discordant == 0:
        return 1.0
    observed_weight = comb(discordant, beneficial)
    numerator = sum(comb(discordant, count) for count in range(discordant + 1) if comb(discordant, count) <= observed_weight)
    return min(1.0, numerator / (2**discordant))


def paired_exact_power(
    checkpoint_count: int,
    *,
    beneficial_probability: float,
    harmful_probability: float,
    alpha: float = ALPHA,
) -> float:
    if checkpoint_count <= 0:
        raise ValueError("checkpoint_count must be positive")
    if not 0 <= beneficial_probability <= 1 or not 0 <= harmful_probability <= 1:
        raise ValueError("discordance probabilities must be within [0, 1]")
    tied_probability = 1 - beneficial_probability - harmful_probability
    if tied_probability < -1e-12:
        raise ValueError("discordance probabilities must sum to at most 1")
    tied_probability = max(0.0, tied_probability)

    result = 0.0
    for beneficial in range(checkpoint_count + 1):
        for harmful in range(checkpoint_count - beneficial + 1):
            tied = checkpoint_count - beneficial - harmful
            probability = comb(checkpoint_count, beneficial) * comb(checkpoint_count - beneficial, harmful) * beneficial_probability**beneficial * harmful_probability**harmful * tied_probability**tied
            discordant = beneficial + harmful
            if exact_two_sided_binomial_p(beneficial, discordant) <= alpha:
                result += probability
    return result


def minimum_checkpoint_count(
    *,
    beneficial_probability: float,
    harmful_probability: float,
    target_power: float = TARGET_POWER,
    maximum: int = 200,
) -> int:
    for checkpoint_count in range(1, maximum + 1):
        if (
            paired_exact_power(
                checkpoint_count,
                beneficial_probability=beneficial_probability,
                harmful_probability=harmful_probability,
            )
            >= target_power
        ):
            return checkpoint_count
    raise ValueError("target power was not reached within the search bound")


def _probabilities(effect: float, discordance: float) -> tuple[float, float]:
    if effect < 0 or discordance < effect or discordance > 1:
        raise ValueError("effect and discordance are incompatible")
    return (discordance + effect) / 2, (discordance - effect) / 2


def build_report() -> dict[str, Any]:
    checkpoint_count = 12
    sensitivity: list[dict[str, Any]] = []
    for effect in (1 / 6, 1 / 3, 1 / 2):
        discordances = sorted({effect, 0.5, 0.75, 1.0})
        scenarios: list[dict[str, Any]] = []
        for discordance in discordances:
            if discordance < effect:
                continue
            beneficial, harmful = _probabilities(effect, discordance)
            scenarios.append(
                {
                    "discordance": discordance,
                    "beneficial_probability": beneficial,
                    "harmful_probability": harmful,
                    "power": paired_exact_power(
                        checkpoint_count,
                        beneficial_probability=beneficial,
                        harmful_probability=harmful,
                    ),
                }
            )
        sensitivity.append(
            {
                "absolute_effect": effect,
                "scenarios": scenarios,
            }
        )

    sample_size_scenarios: list[dict[str, Any]] = []
    effect = 1 / 3
    for discordance in (1 / 3, 0.5, 0.75):
        beneficial, harmful = _probabilities(effect, discordance)
        checkpoints = minimum_checkpoint_count(
            beneficial_probability=beneficial,
            harmful_probability=harmful,
        )
        sample_size_scenarios.append(
            {
                "absolute_effect": effect,
                "discordance": discordance,
                "beneficial_probability": beneficial,
                "harmful_probability": harmful,
                "target_power": TARGET_POWER,
                "minimum_checkpoints": checkpoints,
                "three_arm_count": checkpoints * 3,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "design_sensitivity_only",
        "test": "two_sided_exact_paired_binomial",
        "alpha": ALPHA,
        "candidate_checkpoint_count": checkpoint_count,
        "candidate_arm_count": checkpoint_count * 3,
        "sensitivity": sensitivity,
        "sample_size_sensitivity": sample_size_scenarios,
        "interpretation_boundary": (
            "Power depends on the joint discordance distribution. The calculation treats 12 checkpoints as independent and is optimistic relative to the planned six-project clustered analysis. It is not a formal outcome or authorization."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("report", "validate"))
    args = parser.parse_args()
    report = build_report()
    if args.command == "validate":
        expected = [23, 36, 56]
        actual = [item["minimum_checkpoints"] for item in report["sample_size_sensitivity"]]
        if actual != expected:
            raise RuntimeError(f"sample-size sensitivity drifted: {actual}")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
