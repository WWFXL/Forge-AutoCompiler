#!/usr/bin/env python3
"""Validate and derive the frozen Forge C/C++ formal preregistration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREREGISTRATION = (
    REPO_ROOT / "benchmarks" / "preregistrations" / "cpp-formal-v1.json"
)

IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SECRET_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|authorization\s*:|api[_-]?key\s*[=:])",
    re.IGNORECASE,
)
BUILD_SYSTEMS = ("cmake", "make", "autotools")
SIZE_STRATA = ("small", "medium", "large")
LANGUAGES = ("C", "C++")
EXPECTED_CONDITIONS = {
    "richlab-gpt-5.5": {
        "endpoint": "https://richlab-api-x.choosefire.com/v1",
        "credential_env": "OpenAI_AK",
        "lead_model": "gpt-5.5",
        "compiler_model": "gpt-5.5",
        "fallback_policy": "forbidden",
        "provider_retries": 0,
    },
    "deepseek-v4-flash": {
        "endpoint": "https://api.deepseek.com",
        "credential_env": "DEEPSEEK_API_KEY",
        "lead_model": "deepseek-v4-flash",
        "compiler_model": "deepseek-v4-flash",
        "fallback_policy": "forbidden",
        "provider_retries": 0,
    },
}


class PreregistrationError(ValueError):
    """Raised when the formal preregistration is not internally consistent."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the protocol's stable JSON representation."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_preregistration(path: Path = DEFAULT_PREREGISTRATION) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreregistrationError(f"Cannot load preregistration: {path}") from exc
    if not isinstance(value, dict):
        raise PreregistrationError("Preregistration root must be an object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreregistrationError(message)


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _validate_repository_url(value: str) -> None:
    parsed = urlsplit(value)
    _require(parsed.scheme == "https", f"Repository URL must use HTTPS: {value}")
    _require(
        parsed.hostname == "github.com",
        f"Repository URL must use github.com: {value}",
    )
    _require(
        not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment,
        f"Repository URL contains forbidden components: {value}",
    )
    _require(
        len([part for part in parsed.path.split("/") if part]) == 2,
        f"Repository URL must identify owner/repository: {value}",
    )


def _size_stratum(size_kib: int) -> str:
    if 100 <= size_kib <= 5000:
        return "small"
    if 5001 <= size_kib <= 50000:
        return "medium"
    if 50001 <= size_kib <= 200000:
        return "large"
    raise PreregistrationError(f"Repository size is outside frozen bounds: {size_kib}")


def selection_hash(
    *,
    seed: str,
    repository_url: str,
    commit: str,
    build_system: str,
    size_stratum: str,
) -> str:
    parsed = urlsplit(repository_url)
    owner_repo = parsed.path.strip("/").lower()
    payload = f"{seed}|{owner_repo}|{commit}|{build_system}|{size_stratum}".encode()
    return hashlib.sha256(payload).hexdigest()


def build_schedule(preregistration: dict[str, Any]) -> list[dict[str, Any]]:
    design = preregistration["design"]
    seed = design["schedule_seed"]
    conditions = [condition["id"] for condition in preregistration["conditions"]]
    case_ids = [case["id"] for case in preregistration["cases"]]
    slots: list[dict[str, Any]] = []
    for repetition in range(1, design["rounds"] + 1):
        ordered_cases = sorted(
            case_ids,
            key=lambda case_id: hashlib.sha256(
                f"{seed}|{repetition}|{case_id}".encode()
            ).hexdigest(),
        )
        for case_id in ordered_cases:
            ordered_conditions = sorted(
                conditions,
                key=lambda condition_id: hashlib.sha256(
                    f"{seed}|{repetition}|{case_id}|{condition_id}".encode()
                ).hexdigest(),
            )
            for condition_id in ordered_conditions:
                slots.append(
                    {
                        "order": len(slots) + 1,
                        "case_id": case_id,
                        "condition_id": condition_id,
                        "repetition": repetition,
                    }
                )
    return slots


def exact_project_sign_flip(
    success_count_differences: list[int],
    *,
    repetitions: int = 3,
) -> dict[str, Any]:
    """Return the preregistered exact project-block effect and two-sided p-value."""
    _require(
        len(success_count_differences) == 30,
        "Exact analysis requires 30 project differences",
    )
    _require(repetitions == 3, "Exact analysis requires three repetitions")
    _require(
        all(
            isinstance(difference, int)
            and not isinstance(difference, bool)
            and -repetitions <= difference <= repetitions
            for difference in success_count_differences
        ),
        "Project success-count differences must be integers from -3 to 3",
    )
    distribution: Counter[int] = Counter({0: 1})
    for difference in success_count_differences:
        updated: Counter[int] = Counter()
        for total, assignments in distribution.items():
            updated[total + difference] += assignments
            updated[total - difference] += assignments
        distribution = updated
    observed_total = sum(success_count_differences)
    extreme_assignments = sum(
        assignments
        for total, assignments in distribution.items()
        if abs(total) >= abs(observed_total)
    )
    assignment_count = 2 ** len(success_count_differences)
    _require(
        sum(distribution.values()) == assignment_count,
        "Permutation distribution is incomplete",
    )
    return {
        "project_count": len(success_count_differences),
        "repetitions": repetitions,
        "deepseek_minus_richlab": observed_total
        / (len(success_count_differences) * repetitions),
        "observed_success_count_difference": observed_total,
        "exact_two_sided_p_value": extreme_assignments / assignment_count,
        "assignment_count": assignment_count,
    }


def validate_preregistration(value: dict[str, Any]) -> dict[str, Any]:
    _require(value.get("schema_version") == "1.0.0", "Unexpected schema_version")
    _require(
        value.get("document_type") == "preregistration",
        "Unexpected document_type",
    )
    registration = value["preregistration"]
    _require(
        registration["collection_authorized"] is False,
        "This asset must not authorize collection",
    )
    _require(
        registration["formal_comparison_enabled"] is True,
        "Formal comparison must be explicit",
    )
    _require(
        tuple(registration["supported_build_systems"]) == BUILD_SYSTEMS,
        "Supported build-system order drifted",
    )

    for text in _iter_strings(value):
        _require(not SECRET_RE.search(text), "Secret-like content is forbidden")

    conditions = value["conditions"]
    _require(len(conditions) == 2, "Exactly two conditions are required")
    condition_ids = [condition["id"] for condition in conditions]
    _require(len(set(condition_ids)) == 2, "Condition IDs must be unique")
    for condition in conditions:
        _require(
            IDENTIFIER_RE.fullmatch(condition["id"]) is not None, "Bad condition ID"
        )
        expected_condition = EXPECTED_CONDITIONS.get(condition["id"])
        _require(
            expected_condition is not None, f"Unexpected condition: {condition['id']}"
        )
        _require(
            ENV_RE.fullmatch(condition["credential_env"]) is not None,
            "Bad credential environment-variable name",
        )
        _require(
            condition["fallback_policy"] == "forbidden"
            and condition["provider_retries"] == 0,
            "Fallback and provider retry must remain disabled",
        )
        _require(
            condition == {"id": condition["id"], **expected_condition},
            f"Condition profile drifted: {condition['id']}",
        )
        endpoint = urlsplit(condition["endpoint"])
        _require(
            endpoint.scheme == "https"
            and not endpoint.username
            and not endpoint.password
            and not endpoint.query
            and not endpoint.fragment,
            "Unsafe model endpoint",
        )

    cases = value["cases"]
    _require(len(cases) == 30, "Exactly 30 projects are required")
    case_ids = [case["id"] for case in cases]
    urls = [case["repository_url"].lower() for case in cases]
    _require(len(set(case_ids)) == len(case_ids), "Case IDs must be unique")
    _require(len(set(urls)) == len(urls), "Repositories must be unique")

    strata: Counter[tuple[str, str]] = Counter()
    source = value["source_frame"]
    seed = source["selection_seed"]
    eligible_count = sum(
        count
        for build_strata in source["eligible_strata"].values()
        for count in build_strata.values()
    )
    _require(
        eligible_count == source["eligible_candidate_count"] == 182,
        "Eligible source-frame count drifted",
    )
    _require(
        source["project_yaml_count"]
        >= source["c_cpp_project_count"]
        >= source["github_repository_count"]
        >= source["deduplicated_static_candidate_count"]
        >= source["eligible_candidate_count"],
        "Source-frame counts are not monotonic",
    )
    for case in cases:
        _require(IDENTIFIER_RE.fullmatch(case["id"]) is not None, "Bad case ID")
        _validate_repository_url(case["repository_url"])
        _require(COMMIT_RE.fullmatch(case["commit"]) is not None, "Bad commit SHA")
        _require(case["language"] in LANGUAGES, "Unsupported language")
        _require(case["build_system"] in BUILD_SYSTEMS, "Unsupported build system")
        _require(case["size_stratum"] in SIZE_STRATA, "Unsupported size stratum")
        _require(
            _size_stratum(case["repository_size_kib"]) == case["size_stratum"],
            f"Size stratum mismatch: {case['id']}",
        )
        _require(bool(case["license_spdx"]), f"Missing license: {case['id']}")
        expected_hash = selection_hash(
            seed=seed,
            repository_url=case["repository_url"],
            commit=case["commit"],
            build_system=case["build_system"],
            size_stratum=case["size_stratum"],
        )
        _require(
            SHA256_RE.fullmatch(case["selection_hash"]) is not None
            and case["selection_hash"] == expected_hash,
            f"Selection hash mismatch: {case['id']}",
        )
        strata[(case["build_system"], case["size_stratum"])] += 1

    expected_strata = {
        (build_system, size): count
        for build_system in BUILD_SYSTEMS
        for size, count in source["target_per_build_system"].items()
    }
    _require(dict(strata) == expected_strata, f"Stratification drifted: {strata}")

    design = value["design"]
    expected_attempts = (
        len(cases) * len(conditions) * design["repetitions_per_project_condition"]
    )
    _require(design["rounds"] == 3, "Rounds must remain frozen at 3")
    _require(design["project_count"] == len(cases), "Project count drifted")
    _require(design["condition_count"] == len(conditions), "Condition count drifted")
    _require(
        design["planned_attempt_count"] == expected_attempts == 180,
        "Planned attempt count drifted",
    )
    _require(design["max_parallel_runs"] == 1, "Formal collection must be serial")

    schedule = build_schedule(value)
    tuples = {
        (slot["case_id"], slot["condition_id"], slot["repetition"]) for slot in schedule
    }
    _require(len(schedule) == len(tuples) == 180, "Schedule is not a bijection")
    schedule_digest = canonical_sha256(schedule)
    _require(
        design["schedule_sha256"] == schedule_digest,
        "Frozen schedule digest drifted",
    )

    exclusions = source["pre_collection_exclusions"]
    _require(len(exclusions) == 1, "Pre-collection exclusion audit drifted")
    exclusion = exclusions[0]
    _require(exclusion["source_project_id"] == "esp-v2", "Unexpected exclusion")
    _require(exclusion["replacement_case_id"] == "fio", "Unexpected replacement")
    _require("esp-v2" not in case_ids and "fio" in case_ids, "Replacement not applied")

    projection = value["resource_projection_from_v8"]
    scale = projection["planned_attempts"] / projection["reference_attempts"]
    _require(
        projection["linear_projected_tokens"]
        == round(projection["reference_total_tokens"] * scale),
        "Token projection drifted",
    )
    _require(
        abs(
            projection["linear_projected_wall_clock_seconds"]
            - projection["reference_total_wall_clock_seconds"] * scale
        )
        < 0.001,
        "Wall-clock projection drifted",
    )
    _require(
        projection["human_confirmation_required_before_collection"] is True,
        "Human confirmation gate is required",
    )

    return {
        "valid": True,
        "preregistration_id": registration["id"],
        "canonical_sha256": canonical_sha256(value),
        "projects": len(cases),
        "conditions": len(conditions),
        "planned_attempts": len(schedule),
        "schedule_sha256": schedule_digest,
        "strata": {
            f"{build_system}-{size}": strata[(build_system, size)]
            for build_system in BUILD_SYSTEMS
            for size in SIZE_STRATA
        },
        "collection_authorized": registration["collection_authorized"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate", "schedule"),
        nargs="?",
        default="validate",
    )
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=DEFAULT_PREREGISTRATION,
    )
    args = parser.parse_args(argv)
    try:
        preregistration = load_preregistration(args.preregistration)
        summary = validate_preregistration(preregistration)
    except PreregistrationError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    output: Any = (
        build_schedule(preregistration) if args.command == "schedule" else summary
    )
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
