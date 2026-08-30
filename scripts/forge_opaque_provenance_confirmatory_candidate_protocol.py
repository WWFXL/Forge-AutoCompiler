#!/usr/bin/env python3
"""Issue #230 六 case opaque provenance 确认性 pilot 的未授权静态协议。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/230"
SCHEMA_VERSION = "forge-opaque-provenance-confirmatory-candidate-1.0.0"
DOCUMENT_TYPE = "forge_opaque_provenance_confirmatory_candidate"

SOURCE_CASES_PATH = "benchmarks/preregistrations/cpp-formal-v1-cases.json"
SOURCE_CASES_SHA256 = "55fc4ea1cc634376b5016fa3421736a66c284b293b9b8f10185e837e12db3fee"
SOURCE_SELECTION_PATH = "benchmarks/preregistrations/cpp-formal-v1.json"
SOURCE_SELECTION_SHA256 = "3b7f1134637385f7236ea344c8b9816c04bc837143cb7ac4f8af1e007e7f08dc"
SOURCE_MANIFEST_PATH = "benchmarks/manifests/cpp-formal-v1.json"
SOURCE_MANIFEST_SHA256 = "cb9ad04c3d5452ab6ae3e12d1ef8658b8cf52876c6aecc3b251b2dd930e6944a"

PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-candidate.md"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-candidate.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-confirmatory-candidate.schema.json"

WORKDIR = "/workspace/repo"
ARTIFACTS_DIR = "/artifacts"
PAIR_COUNT = 12
ARM_COUNT = 24
PER_ARM_TOKEN_CEILING = 120_000
BATCH_TOKEN_CEILING = 2_940_000

CASE_ORDER = ("pupnp", "ada-url", "args", "gpac", "fio", "sql-parser-shared")
SOURCE_CASE_IDS = {
    "pupnp": "pupnp",
    "ada-url": "ada-url",
    "args": "args",
    "gpac": "gpac",
    "fio": "fio",
    "sql-parser-shared": "sql-parser",
}

EXPECTED_SOURCE_IDENTITIES = {
    "pupnp": {
        "repository_url": "https://github.com/pupnp/pupnp",
        "commit": "4c4285d6af69774b7ec6a9a93dc967dc9e9e6d8e",
        "build_system": "cmake",
        "language": "C",
    },
    "ada-url": {
        "repository_url": "https://github.com/ada-url/ada",
        "commit": "30f3f3020c5a979b62f90dc9c37fd45de3cc84d7",
        "build_system": "cmake",
        "language": "C++",
    },
    "args": {
        "repository_url": "https://github.com/Taywee/args",
        "commit": "fe4450bd9549e4e02bc2047b2a2800b09f1bb878",
        "build_system": "cmake",
        "language": "C++",
    },
    "gpac": {
        "repository_url": "https://github.com/gpac/gpac",
        "commit": "2aa431eaf732c1a7e9a966ea12049fc001d91e04",
        "build_system": "make",
        "language": "C",
    },
    "fio": {
        "repository_url": "https://github.com/axboe/fio",
        "commit": "c76c61b0fbe1b90a7886b8790805cf9903285074",
        "build_system": "make",
        "language": "C++",
    },
    "sql-parser": {
        "repository_url": "https://github.com/hyrise/sql-parser",
        "commit": "ccd3f68b50bb2b96ce69afa7b956b3bd826643cc",
        "build_system": "make",
        "language": "C++",
    },
}

CASE_ARTIFACTS = {
    "pupnp": ("upnp_static", "build/upnp/libupnp.a", "libupnp.a", "static_library"),
    "ada-url": ("ada", "build/src/libada.a", "libada.a", "static_library"),
    "args": ("gitlike", "build/gitlike", "gitlike", "executable"),
    "gpac": ("lib", "bin/gcc/libgpac_static.a", "libgpac_static.a", "static_library"),
    "fio": ("fio", "fio", "fio", "executable"),
    "sql-parser-shared": ("library", "libsqlparser.so", "libsqlparser.so", "shared_library"),
}

SOURCE_AUDIT = {
    "pupnp": {
        "submodules": [],
        "direct_target_verified": True,
        "external_fetch_on_frozen_path": False,
        "smoke": None,
    },
    "ada-url": {
        "submodules": [],
        "direct_target_verified": True,
        "external_fetch_on_frozen_path": False,
        "smoke": None,
    },
    "args": {
        "submodules": [],
        "direct_target_verified": True,
        "external_fetch_on_frozen_path": False,
        "smoke": {"flag": "--help", "expected_exit_code": 0},
    },
    "gpac": {
        "submodules": ["testsuite"],
        "submodules_on_target_dependency_path": [],
        "direct_target_verified": True,
        "external_fetch_on_frozen_path": False,
        "smoke": None,
    },
    "fio": {
        "submodules": [],
        "direct_target_verified": True,
        "external_fetch_on_frozen_path": False,
        "smoke": {"flag": "--help", "expected_exit_code": 0},
    },
    "sql-parser-shared": {
        "submodules": [],
        "generated_parser_sources_tracked": True,
        "direct_target_verified": True,
        "external_fetch_on_frozen_path": False,
        "smoke": None,
    },
}

EXCLUSIONS = {
    "mruby": "make all delegates to Rake and implicitly initializes the Prism submodule",
    "janet": "local model-result evidence already exists, so the case is not result-blind",
    "lodepng": "the unittest executable catches test failures and still returns exit code zero",
    "sql-parser-static": "the frozen static oracle contradicts the default make library output",
}


class ConfirmatoryCandidateError(RuntimeError):
    """候选身份、顺序、授权或分析合同发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_frozen_sources(repo_root: Path = REPO_ROOT) -> None:
    expected = {
        SOURCE_CASES_PATH: SOURCE_CASES_SHA256,
        SOURCE_SELECTION_PATH: SOURCE_SELECTION_SHA256,
        SOURCE_MANIFEST_PATH: SOURCE_MANIFEST_SHA256,
    }
    for relative_path, expected_sha256 in expected.items():
        if file_sha256(repo_root / relative_path) != expected_sha256:
            raise ConfirmatoryCandidateError(f"冻结来源发生漂移: {relative_path}")


def _load_source_documents(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    verify_frozen_sources(repo_root)
    cases = json.loads((repo_root / SOURCE_CASES_PATH).read_text(encoding="utf-8"))
    selection = json.loads((repo_root / SOURCE_SELECTION_PATH).read_text(encoding="utf-8"))
    return cases, selection


def _source_maps(repo_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    cases_document, selection_document = _load_source_documents(repo_root)
    cases = {item["id"]: item for item in cases_document["cases"]}
    selections = {item["id"]: item for item in selection_document["cases"]}
    required = set(SOURCE_CASE_IDS.values())
    if not required.issubset(cases) or not required.issubset(selections):
        raise ConfirmatoryCandidateError("冻结来源缺少候选 case")
    return cases, selections


def _validate_source_identity(source_id: str, case: dict[str, Any], selection: dict[str, Any]) -> None:
    expected = EXPECTED_SOURCE_IDENTITIES[source_id]
    actual = {
        "repository_url": case.get("repository_url"),
        "commit": case.get("commit"),
        "build_system": case.get("build_system"),
        "language": selection.get("language"),
    }
    if actual != expected or case.get("review_state") != "reviewed" or case.get("result_data_consulted") is not False:
        raise ConfirmatoryCandidateError(f"source identity 发生漂移: {source_id}")


def _build_case(case_id: str, source: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    source_id = SOURCE_CASE_IDS[case_id]
    _validate_source_identity(source_id, source, selection)
    target, output, staged, artifact_type = CASE_ARTIFACTS[case_id]
    source_target = source["recipe"]["build_targets"]
    if source_target != [target]:
        raise ConfirmatoryCandidateError(f"direct target 发生漂移: {case_id}")

    source_artifacts = source["artifact_oracle"]["required_artifacts"]
    correction: dict[str, Any] | None = None
    if case_id == "sql-parser-shared":
        expected_old = [
            {
                "staged_relative_path": "libsqlparser.a",
                "build_output_path": "libsqlparser.a",
                "artifact_type": "static_library",
                "producing_target": "library",
            }
        ]
        if source_artifacts != expected_old:
            raise ConfirmatoryCandidateError("sql-parser 旧 static oracle 发生漂移")
        correction = {
            "mode": "pre_result_exact_commit_source_correction",
            "old_artifact": copy.deepcopy(expected_old[0]),
            "reason": "Makefile defines static ?= no, so direct make library produces libsqlparser.so",
            "source_protocol_modified": False,
        }
    else:
        expected_artifact = [
            {
                "staged_relative_path": staged,
                "build_output_path": output,
                "artifact_type": artifact_type,
                "producing_target": target,
            }
        ]
        if source_artifacts != expected_artifact:
            raise ConfirmatoryCandidateError(f"artifact oracle 发生漂移: {case_id}")

    return {
        "case_id": case_id,
        "source_case_id": source_id,
        "repository_url": source["repository_url"],
        "commit_sha": source["commit"],
        "language": selection["language"],
        "build_system": source["build_system"],
        "size_stratum": selection["size_stratum"],
        "build_directory": WORKDIR,
        "bootstrap_commands": copy.deepcopy(source["recipe"]["bootstrap_commands"]),
        "configure_arguments": copy.deepcopy(source["recipe"]["configure_arguments"]),
        "required_system_packages": copy.deepcopy(source["recipe"]["required_system_packages"]),
        "direct_target": target,
        "artifact": {
            "build_output_path": output,
            "staged_relative_path": staged,
            "artifact_type": artifact_type,
            "stage_source": f"{WORKDIR}/{output}",
            "stage_destination": f"{ARTIFACTS_DIR}/{staged}",
        },
        "oracle_correction": correction,
        "source_audit": copy.deepcopy(SOURCE_AUDIT[case_id]),
        "historical_result_evidence_case_id_matches": 0,
    }


def _schedule() -> list[dict[str, Any]]:
    first_orders = {
        "pupnp": ("baseline", "treatment"),
        "ada-url": ("treatment", "baseline"),
        "args": ("baseline", "treatment"),
        "gpac": ("treatment", "baseline"),
        "fio": ("baseline", "treatment"),
        "sql-parser-shared": ("treatment", "baseline"),
    }
    pairs: list[dict[str, Any]] = []
    for case_id in CASE_ORDER:
        pairs.append({"pair_id": f"{case_id}-rep-01", "case_id": case_id, "replicate": 1, "arm_order": list(first_orders[case_id])})
    for case_id in reversed(CASE_ORDER):
        reverse_order = tuple(reversed(first_orders[case_id]))
        pairs.append({"pair_id": f"{case_id}-rep-02", "case_id": case_id, "replicate": 2, "arm_order": list(reverse_order)})
    return pairs


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    sources, selections = _source_maps(repo_root)
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise ConfirmatoryCandidateError("候选预注册不存在")
    cases = [_build_case(case_id, sources[SOURCE_CASE_IDS[case_id]], selections[SOURCE_CASE_IDS[case_id]]) for case_id in CASE_ORDER]
    pairs = _schedule()
    schedule_identity = canonical_sha256(pairs)
    return {
        "$schema": "../schemas/forge-opaque-provenance-confirmatory-candidate.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "authorization": {
            "provider_calls_authorized": False,
            "credential_read_authorized": False,
            "model_creation_authorized": False,
            "reachability_request_authorized": False,
            "checkpoint_creation_authorized": False,
            "pair_collection_authorized": False,
            "formal_attempts_authorized": False,
            "docker_execution_authorized": False,
            "evidence_write_authorized": False,
            "model_tokens_authorized": 0,
        },
        "selection": {
            "issue_url": ISSUE_URL,
            "mode": "result_blind_exact_commit_source_audit",
            "frozen_sources": {
                SOURCE_CASES_PATH: SOURCE_CASES_SHA256,
                SOURCE_SELECTION_PATH: SOURCE_SELECTION_SHA256,
                SOURCE_MANIFEST_PATH: SOURCE_MANIFEST_SHA256,
            },
            "case_count": len(cases),
            "build_system_counts": {"cmake": 3, "make": 3},
            "artifact_type_counts": {"executable": 2, "static_library": 3, "shared_library": 1},
            "exclusions": copy.deepcopy(EXCLUSIONS),
        },
        "cases": cases,
        "schedule": {
            "pair_count": PAIR_COUNT,
            "arm_count": ARM_COUNT,
            "replicates_per_case": 2,
            "project_internal_order_reversal_required": True,
            "baseline_first_pairs": 6,
            "treatment_first_pairs": 6,
            "pairs": pairs,
            "identity_sha256": schedule_identity,
        },
        "runtime_contract": {
            "provider_and_model_single_for_batch": True,
            "provider_identity_status": "pending_execution_amendment",
            "request_timeout_seconds": 300,
            "request_retries": 0,
            "fallback_forbidden": True,
            "parallel_tool_calls": False,
            "action_limits": {"inspection": 4, "repair_build": 2, "artifact_stage": 2, "submit": 2},
            "request_limit_per_arm": 8,
            "turn_limit_per_arm": 8,
            "graph_step_limit_per_arm": 24,
            "work_timeout_seconds_per_arm": 600,
            "cleanup_timeout_seconds_per_arm": 120,
            "per_arm_recorded_token_ceiling": PER_ARM_TOKEN_CEILING,
            "batch_recorded_token_ceiling": BATCH_TOKEN_CEILING,
            "shared_tool_contract_identical_between_arms": True,
            "treatment_exposure_only": "repair_packet",
        },
        "measurement_contract": {
            "parent_fault": "opaque_build_provenance",
            "parent_proof_status": "unproven/opaque_wrapper",
            "treatment_required_proof_modes": {"cmake": "direct_cmake", "make": "direct_make"},
            "r0_companion_required": True,
            "candidate_verification_required": True,
            "clean_replay_required": True,
            "cleanup_and_zero_orphan_required": True,
            "replacement_forbidden": True,
            "backfill_forbidden": True,
            "batch_protocol_mutation_after_start_forbidden": True,
        },
        "analysis": {
            "independent_unit": "project_block",
            "project_block_count": 6,
            "project_score": "mean of two replicate paired conversion differences",
            "primary_test": "two_sided_exact_sign_flip_over_six_project_scores",
            "primary_test_requires_all_project_blocks_estimable": True,
            "infrastructure_censoring_reported_separately": True,
            "mechanism_invalid_reported_separately": True,
            "intervention_delivery_invalid_reported_separately": True,
            "historical_exploratory_pairs_pooled": False,
            "model_ranking_performed": False,
        },
        "future_state": {
            "checkpoint_status": "not_created",
            "evidence_status": "not_created",
            "execution_runner_status": "not_implemented",
            "execution_requires_new_amendment": True,
        },
        "preregistration": {
            "path": PREREGISTRATION_PATH,
            "file_sha256": file_sha256(preregistration),
        },
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if not isinstance(value, dict) or value != expected:
        raise ConfirmatoryCandidateError("confirmatory candidate manifest 发生漂移")
    authorization = value["authorization"]
    if any(item for key, item in authorization.items() if key.endswith("_authorized")):
        raise ConfirmatoryCandidateError("candidate 意外授权了外部执行")
    if authorization["model_tokens_authorized"] != 0:
        raise ConfirmatoryCandidateError("candidate 意外授权了 model token")
    return value


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    frozen = manifest or generate_manifest()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-opaque-provenance-confirmatory-candidate.schema.json",
        "title": "Forge opaque provenance confirmatory candidate",
        "const": frozen,
    }


def validate_static_gate(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest = generate_manifest(repo_root)
    cases = manifest["cases"]
    pairs = manifest["schedule"]["pairs"]
    if len(cases) != 6 or len({case["case_id"] for case in cases}) != 6:
        raise ConfirmatoryCandidateError("case 数量或唯一性无效")
    if len(pairs) != PAIR_COUNT or len({pair["pair_id"] for pair in pairs}) != PAIR_COUNT:
        raise ConfirmatoryCandidateError("pair 数量或唯一性无效")
    for case_id in CASE_ORDER:
        project_pairs = [pair for pair in pairs if pair["case_id"] == case_id]
        if [pair["replicate"] for pair in sorted(project_pairs, key=lambda item: item["replicate"])] != [1, 2]:
            raise ConfirmatoryCandidateError(f"replicate identity 无效: {case_id}")
        orders = {tuple(pair["arm_order"]) for pair in project_pairs}
        if orders != {("baseline", "treatment"), ("treatment", "baseline")}:
            raise ConfirmatoryCandidateError(f"arm order 未在项目内对调: {case_id}")
    if manifest["schedule"]["identity_sha256"] != canonical_sha256(pairs):
        raise ConfirmatoryCandidateError("schedule identity 发生漂移")
    return {
        "status": "passed",
        "case_count": len(cases),
        "pair_count": len(pairs),
        "arm_count": sum(len(pair["arm_order"]) for pair in pairs),
        "schedule_identity_sha256": manifest["schedule"]["identity_sha256"],
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="确定性写入 manifest 与 const schema")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = generate_manifest()
    schema = schema_document(manifest)
    if args.write:
        _write_json(DEFAULT_MANIFEST, manifest)
        _write_json(DEFAULT_SCHEMA, schema)
    else:
        validate_manifest(json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8")))
        if json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8")) != schema:
            raise ConfirmatoryCandidateError("confirmatory candidate schema 发生漂移")
    print(json.dumps(validate_static_gate(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
