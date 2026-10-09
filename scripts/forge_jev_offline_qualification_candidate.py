#!/usr/bin/env python3
"""Issue #393 Jev 离线资格实验的零 Provider candidate。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Any

import forge_typed_action_benchmark_qualification as v1
import httpx2
import jsonschema
from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-jev-offline-qualification-candidate-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/393"
SCHEMA_VERSION = "forge-jev-offline-qualification-candidate-1.0.0"

SDK_DISTRIBUTION = "typesafe-sdk"
SDK_VERSION = "0.7.3"
MODEL_ID = "jev-1.13.0"
API_BASE_URL = "https://api.typesafe.ai"
API_ENDPOINT = "/v1/systemone"
CREDENTIAL_ENV = "TYPESAFE_API_KEY"
INPUT_PRICE_USD_PER_MILLION_TOKENS = 0.042

V1_SOURCE_POOL = REPO_ROOT / "benchmarks/fixtures/cpp-typed-action-benchmark-source-pool-v1.json"
V2_REPORT = REPO_ROOT / "benchmarks/reports/cpp-typed-semantic-routing-pilot-v2.json"
V2_REPORT_SHA256 = "ea2e126e81cfca374900436fa670015b28b3cc3f9d8c83e746ae2c92d2badfed"
DEFAULT_SOURCE_POOL = REPO_ROOT / "benchmarks/fixtures/cpp-jev-offline-qualification-source-pool-v1.json"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-jev-offline-qualification-candidate-v1.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-jev-offline-qualification-candidate-v1.schema.json"
PREREGISTRATION = REPO_ROOT / "benchmarks/preregistrations/cpp-jev-offline-qualification-candidate-v1.md"
API_AUDIT = REPO_ROOT / "docs/research/2026-10-09-jev-api-contract-audit.md"

BUILD_SYSTEMS = ("cmake", "make", "autotools")
QUALIFICATION_SPLITS = ("design", "calibration")
FAULT_TYPES = ("missing_compile_input", "invalid_build_state", "wrong_build_target")
ACTION_FAMILIES = ("dependency", "configure", "build", "escalate_agent")
ACTION_COSTS = {"build": 1, "configure": 2, "dependency": 3, "escalate_agent": 4}
PRIMARY_ACTION_ORDER = ACTION_FAMILIES
SENSITIVITY_ACTION_ORDER = tuple(reversed(ACTION_FAMILIES))
QUESTION_IDS = ("next_action_primary", "next_action_order_sensitivity")

ACTION_DESCRIPTIONS = {
    "dependency": ("Run the already-bound recovery action that restores a missing source or dependency input, then continue the strict build verification workflow."),
    "configure": ("Run the already-bound configure recovery action that regenerates damaged or stale build-system state, then continue the strict build verification workflow."),
    "build": ("Run the already-bound normal build action without changing dependencies or generated configuration, then continue the strict build verification workflow."),
    "escalate_agent": ("Do not execute a direct recovery action. Escalate the state to the full compilation Agent because the evidence does not safely support one direct action."),
}
ACTION_INSTRUCTIONS = (
    "Choose the single next action that is best supported by the observed build failure and is "
    "most likely to reach the strict build endpoint at the lowest listed action cost. Use only "
    "the supplied state. Choose escalate_agent when the evidence is insufficient for a direct "
    "action. Do not invent commands or actions."
)

TASK_SELECTION = (
    {
        "task_id": "libsoundio",
        "qualification_split": "design",
        "fault_file": "src/soundio.c",
        "build_state_file": "build/Makefile",
    },
    {
        "task_id": "cjson",
        "qualification_split": "design",
        "fault_file": "cJSON.c",
        "build_state_file": "build/Makefile",
    },
    {
        "task_id": "stockfish-11",
        "qualification_split": "design",
        "fault_file": "src/position.cpp",
        "build_state_file": "src/Makefile",
    },
    {
        "task_id": "xxhash",
        "qualification_split": "design",
        "fault_file": "xxhash.c",
        "build_state_file": "Makefile",
    },
    {
        "task_id": "rnnoise-0.1.1",
        "qualification_split": "design",
        "fault_file": "src/denoise.c",
        "build_state_file": "Makefile",
    },
    {
        "task_id": "libogg",
        "qualification_split": "design",
        "fault_file": "src/bitwise.c",
        "build_state_file": "Makefile",
    },
    {
        "task_id": "leveldb",
        "qualification_split": "calibration",
        "fault_file": "db/db_impl.cc",
        "build_state_file": "build/Makefile",
    },
    {
        "task_id": "fmt",
        "qualification_split": "calibration",
        "fault_file": "src/format.cc",
        "build_state_file": "build/Makefile",
    },
    {
        "task_id": "8cc",
        "qualification_split": "calibration",
        "fault_file": "main.c",
        "build_state_file": "Makefile",
    },
    {
        "task_id": "zstd",
        "qualification_split": "calibration",
        "fault_file": "lib/common/entropy_common.c",
        "build_state_file": "lib/Makefile",
    },
    {
        "task_id": "jansson",
        "qualification_split": "calibration",
        "fault_file": "src/value.c",
        "build_state_file": "Makefile",
    },
    {
        "task_id": "libyaml",
        "qualification_split": "calibration",
        "fault_file": "src/api.c",
        "build_state_file": "Makefile",
    },
)


class CandidateError(RuntimeError):
    """Candidate 合同、SDK 或模拟响应发生漂移。"""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise CandidateError(f"不安全的相对路径: {value}")


def _configure_contract(task: dict[str, Any], build_state_file: str) -> tuple[list[str], list[str]]:
    configure_commands = list(task["configure_commands"])
    if task["selected_build_system"] == "make":
        configure_commands = [f"test -f {build_state_file}"]
        return configure_commands, [
            f"git checkout HEAD -- {build_state_file}",
            *configure_commands,
        ]
    if task["selected_build_system"] == "cmake":
        return configure_commands, ["rm -rf build", *configure_commands]
    return configure_commands, list(configure_commands)


def generate_source_pool() -> dict[str, Any]:
    source = v1.load_json(V1_SOURCE_POOL)
    by_id = {task["task_id"]: task for task in source["tasks"]}
    tasks: list[dict[str, Any]] = []
    for selection in TASK_SELECTION:
        task = copy.deepcopy(by_id[selection["task_id"]])
        task["prior_v1_split"] = task.pop("split")
        task["qualification_split"] = selection["qualification_split"]
        task["fault_file"] = selection["fault_file"]
        task["build_state_file"] = selection["build_state_file"]
        configure, repair = _configure_contract(task, task["build_state_file"])
        task["configure_commands"] = configure
        task["configure_repair_commands"] = repair
        tasks.append(task)
    return {
        "schema_version": "forge-jev-offline-qualification-source-pool-1.0.0",
        "identity": IDENTITY,
        "status": "candidate_frozen_before_new_outcomes",
        "source": {
            "path": V1_SOURCE_POOL.relative_to(REPO_ROOT).as_posix(),
            "canonical_sha256": v1.canonical_sha256(source),
            "reuse_scope": "source_build_oracle_contract_only",
            "prior_outcomes_are_not_labels": True,
        },
        "quotas": {
            "project_count": 12,
            "projects_per_split": 6,
            "projects_per_build_system_per_split": 2,
            "faults_per_project": 3,
        },
        "tasks": tasks,
    }


def _evaluation_contract() -> dict[str, Any]:
    report = v1.load_json(V2_REPORT)
    states = report["states"]
    return {
        "identity": report["identity"],
        "path": V2_REPORT.relative_to(REPO_ROOT).as_posix(),
        "file_sha256": V2_REPORT_SHA256,
        "project_families": sorted({state["project_family"] for state in states}),
        "state_ids": sorted(state["state_id"] for state in states),
        "project_count": len({state["project_family"] for state in states}),
        "state_count": len(states),
        "read_only": True,
        "single_analysis_only": True,
        "prompt_or_threshold_tuning_allowed": False,
    }


def _choice_contract(order: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": ACTION_INSTRUCTIONS,
        "criteria": {family: ACTION_DESCRIPTIONS[family] for family in order},
    }


def generate_manifest(source_pool: dict[str, Any] | None = None) -> dict[str, Any]:
    pool = source_pool or generate_source_pool()
    return {
        "$schema": "../schemas/forge-jev-offline-qualification-candidate-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_jev_offline_qualification_candidate",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "status": "candidate_zero_provider",
        "authorization": {
            "credential_read_authorized": False,
            "provider_calls_authorized": False,
            "model_calls_authorized": False,
            "model_tokens_authorized": 0,
            "provider_evidence_write_authorized": False,
            "docker_outcome_collection_authorized": False,
            "controller_implementation_authorized": False,
            "historical_evidence_write_authorized": False,
        },
        "provider_contract": {
            "provider": "TypeSafe AI",
            "api_base_url": API_BASE_URL,
            "endpoint": API_ENDPOINT,
            "credential_env": CREDENTIAL_ENV,
            "sdk_distribution": SDK_DISTRIBUTION,
            "sdk_version": SDK_VERSION,
            "sdk_default_max_retries": 2,
            "model": MODEL_ID,
            "aliases_forbidden": ["jev-latest", "jev-preview"],
            "response_model_must_equal_request_model": True,
            "timeout_seconds": 30.0,
            "max_retries": 0,
            "input_price_usd_per_million_tokens": INPUT_PRICE_USD_PER_MILLION_TOKENS,
            "output_tokens_free": True,
            "sdk_log_level": "off",
            "documentation_audit_path": API_AUDIT.relative_to(REPO_ROOT).as_posix(),
        },
        "data_contract": {
            "source_pool": {
                "path": DEFAULT_SOURCE_POOL.relative_to(REPO_ROOT).as_posix(),
                "canonical_sha256": v1.canonical_sha256(pool),
            },
            "design": {
                "project_count": 6,
                "state_count": 18,
                "maximum_provider_rounds": 2,
            },
            "calibration": {"project_count": 6, "state_count": 18},
            "evaluation": _evaluation_contract(),
            "project_family_overlap_allowed": False,
            "global_commit_time_isolation": False,
            "temporal_generalization_claim_allowed": False,
            "new_labels_from_executed_candidate_outcomes": True,
            "fault_name_is_not_model_input": True,
        },
        "request_contract": {
            "state_fields": [
                "build_system",
                "phase_facts",
                "remaining_budget",
                "semantic_failure_log",
                "candidate_action_costs",
            ],
            "question_ids": list(QUESTION_IDS),
            "primary": _choice_contract(PRIMARY_ACTION_ORDER),
            "order_sensitivity": _choice_contract(SENSITIVITY_ACTION_ORDER),
            "one_request_per_state_per_round": True,
            "shell_generation_by_model": False,
        },
        "response_contract": {
            "required_fields": [
                "model",
                "answers",
                "usage.input_tokens",
                "usage.output_tokens",
                "x-typesafe-request-id",
            ],
            "required_answer_fields": [
                "type",
                "choice",
                "probabilities",
                "confidence",
            ],
            "probability_keys": list(ACTION_FAMILIES),
            "probability_sum_absolute_tolerance": 0.000001,
            "choice_confidence_formula": "(p_max - 1/n) / (1 - 1/n)",
            "confidence_formula_absolute_tolerance": 0.02,
            "store_authorization_header": False,
            "store_raw_credential": False,
        },
        "budget": {
            "maximum_model_requests": 72,
            "maximum_input_tokens": 1_000_000,
            "maximum_model_cost_usd": 0.042,
            "design_maximum_requests": 36,
            "calibration_maximum_requests": 18,
            "evaluation_maximum_requests": 18,
        },
        "candidate_thresholds": {
            "minimum_evaluation_top1_correct": 15,
            "minimum_direct_execution_coverage_count": 6,
            "maximum_erroneous_direct_actions": 0,
            "minimum_order_agreement_count": 16,
            "require_correct_direct_action_in_every_build_system": True,
            "threshold_selected_on_calibration_only": True,
        },
        "stopping_rules": {
            "stop_batch_on_first_request_failure": True,
            "stop_on_model_version_drift": True,
            "stop_on_response_contract_drift": True,
            "retry_failed_evaluation_request": False,
            "replace_failed_evaluation_state": False,
            "backfill_failed_evaluation_state": False,
            "adjust_after_evaluation": False,
        },
        "preregistration": {
            "path": PREREGISTRATION.relative_to(REPO_ROOT).as_posix(),
            "must_be_committed_and_pushed_before_credential_read": True,
            "requires_separate_authorized_amendment": True,
        },
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-offline-qualification-candidate-v1.schema.json",
        "title": "Forge Jev offline qualification candidate v1",
        "const": manifest,
    }


def validate_source_pool(pool: dict[str, Any]) -> dict[str, Any]:
    if pool != generate_source_pool():
        raise CandidateError("source pool 无法确定重建")
    tasks = pool["tasks"]
    if len(tasks) != 12 or len({task["project_family"] for task in tasks}) != 12:
        raise CandidateError("design/calibration project family 不完整")
    evaluation_families = set(_evaluation_contract()["project_families"])
    if evaluation_families & {task["project_family"] for task in tasks}:
        raise CandidateError("design/calibration 与 evaluation project family 重叠")
    for split in QUALIFICATION_SPLITS:
        selected = [task for task in tasks if task["qualification_split"] == split]
        if len(selected) != 6:
            raise CandidateError(f"{split} 项目数漂移")
        if Counter(task["selected_build_system"] for task in selected) != {system: 2 for system in BUILD_SYSTEMS}:
            raise CandidateError(f"{split} 构建系统配额漂移")
    for task in tasks:
        for path in (
            task["license_path"],
            task["fault_file"],
            task["build_state_file"],
            *task["target"]["required_artifacts"],
        ):
            _safe_relative(path)
        commands = [
            *task["configure_commands"],
            *task["configure_repair_commands"],
            *task["build_commands"],
            *task["artifact_stage_commands"],
        ]
        forbidden = ("curl ", "wget ", "git clone", "git fetch", "apt-get", "sudo ")
        if any(token in command for command in commands for token in forbidden):
            raise CandidateError(f"{task['task_id']} 动作包含网络或提权命令")
    return pool


def validate_manifest(manifest: dict[str, Any], pool: dict[str, Any], *, check_schema: bool = True) -> dict[str, Any]:
    validate_source_pool(pool)
    if manifest != generate_manifest(pool):
        raise CandidateError("manifest 无法确定重建")
    authorization = manifest["authorization"]
    if any(value is not False and key != "model_tokens_authorized" for key, value in authorization.items()):
        raise CandidateError("candidate 意外授权真实执行")
    if authorization["model_tokens_authorized"] != 0:
        raise CandidateError("candidate model token 必须为 0")
    provider = manifest["provider_contract"]
    if provider["model"] != MODEL_ID or provider["sdk_version"] != SDK_VERSION:
        raise CandidateError("Provider 版本合同漂移")
    if provider["max_retries"] != 0 or provider["timeout_seconds"] != 30.0:
        raise CandidateError("Provider timeout/retry 合同漂移")
    evaluation = manifest["data_contract"]["evaluation"]
    if _file_sha256(V2_REPORT) != evaluation["file_sha256"]:
        raise CandidateError("v2 evaluation 报告 hash 漂移")
    if check_schema:
        schema = v1.load_json(DEFAULT_SCHEMA)
        if schema != generate_schema(manifest):
            raise CandidateError("const Schema 漂移")
        jsonschema.validate(manifest, schema)
    return manifest


def generate_contract_files() -> None:
    pool = generate_source_pool()
    manifest = generate_manifest(pool)
    schema = generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    v1.write_json(DEFAULT_SOURCE_POOL, pool)
    v1.write_json(DEFAULT_MANIFEST, manifest)
    v1.write_json(DEFAULT_SCHEMA, schema)


def load_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    pool = validate_source_pool(v1.load_json(DEFAULT_SOURCE_POOL))
    manifest = validate_manifest(v1.load_json(DEFAULT_MANIFEST), pool)
    return manifest, pool


def provider_state(model_input: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "build_system",
        "candidate_action_families",
        "phase_facts",
        "remaining_budget",
        "semantic_failure_log",
        "state_id",
    }
    if set(model_input) != expected:
        raise CandidateError("model_input 字段漂移")
    if tuple(model_input["candidate_action_families"]) != ACTION_FAMILIES:
        raise CandidateError("候选动作目录漂移")
    return {
        "build_system": model_input["build_system"],
        "phase_facts": model_input["phase_facts"],
        "remaining_budget": model_input["remaining_budget"],
        "semantic_failure_log": model_input["semantic_failure_log"],
        "candidate_action_costs": ACTION_COSTS,
    }


def provider_questions() -> dict[str, Choice]:
    return {
        "next_action_primary": Choice(
            instructions=ACTION_INSTRUCTIONS,
            criteria={family: ACTION_DESCRIPTIONS[family] for family in PRIMARY_ACTION_ORDER},
        ),
        "next_action_order_sensitivity": Choice(
            instructions=ACTION_INSTRUCTIONS,
            criteria={family: ACTION_DESCRIPTIONS[family] for family in SENSITIVITY_ACTION_ORDER},
        ),
    }


def request_fingerprint(state: dict[str, Any], questions: dict[str, Choice]) -> str:
    payload = {
        "model": MODEL_ID,
        "state": state,
        "questions": {key: value.model_dump(mode="json", exclude_none=True) for key, value in questions.items()},
    }
    return v1.canonical_sha256(payload)


def _validate_choice_answer(answer: Any) -> dict[str, Any]:
    if getattr(answer, "type", None) != "choice":
        raise CandidateError("Jev answer type 不是 choice")
    probabilities = dict(answer.probabilities)
    if set(probabilities) != set(ACTION_FAMILIES):
        raise CandidateError("Jev probability key 漂移")
    if any(not 0.0 <= value <= 1.0 for value in probabilities.values()):
        raise CandidateError("Jev probability 越界")
    if abs(sum(probabilities.values()) - 1.0) > 0.000001:
        raise CandidateError("Jev probability 总和不为 1")
    maximum = max(probabilities.values())
    if answer.choice not in ACTION_FAMILIES or abs(probabilities[answer.choice] - maximum) > 0.000001:
        raise CandidateError("Jev choice 与最高概率不一致")
    expected_confidence = (maximum - 0.25) / 0.75
    if abs(answer.confidence - expected_confidence) > 0.02:
        raise CandidateError("Jev confidence 与官方公式不一致")
    return {
        "choice": answer.choice,
        "probabilities": probabilities,
        "confidence": answer.confidence,
        "recomputed_confidence": expected_confidence,
    }


def normalize_response(response: Any, *, latency_ms: float) -> dict[str, Any]:
    if response.model != MODEL_ID:
        raise CandidateError(f"Jev 响应模型漂移: {response.model}")
    if set(response.answers) != set(QUESTION_IDS):
        raise CandidateError("Jev answer 集合漂移")
    if not response.request_id:
        raise CandidateError("Jev 响应缺少 request id")
    usage = response.usage
    if usage.input_tokens is None or usage.output_tokens is None:
        raise CandidateError("Jev 响应缺少 token usage")
    if usage.input_tokens < 0 or usage.output_tokens < 0:
        raise CandidateError("Jev token usage 非法")
    return {
        "model": response.model,
        "request_id": response.request_id,
        "answers": {key: _validate_choice_answer(response.answers[key]) for key in QUESTION_IDS},
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
        "cost_usd": usage.input_tokens * INPUT_PRICE_USD_PER_MILLION_TOKENS / 1_000_000,
        "latency_ms": latency_ms,
        "order_agreement": (response.answers["next_action_primary"].choice == response.answers["next_action_order_sensitivity"].choice),
    }


def mock_sdk_roundtrip() -> dict[str, Any]:
    report = v1.load_json(V2_REPORT)
    state = provider_state(report["states"][0]["model_input"])
    questions = provider_questions()
    observed: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        observed["method"] = request.method
        observed["url"] = str(request.url)
        observed["authorized"] = request.headers.get("authorization") == "Bearer mock-key"
        observed["body"] = json.loads(request.content)
        answer = {
            "type": "choice",
            "choice": "build",
            "confidence": 0.6,
            "probabilities": {
                "dependency": 0.1,
                "configure": 0.1,
                "build": 0.7,
                "escalate_agent": 0.1,
            },
        }
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req-zero-provider-mock"},
            json={
                "model": MODEL_ID,
                "answers": {key: answer for key in QUESTION_IDS},
                "usage": {"input_tokens": 123, "output_tokens": 18},
            },
        )

    with TypeSafeClient(
        api_key="mock-key",
        model=MODEL_ID,
        retry=RetryPolicy(max_retries=0, timeout=30.0),
        transport=httpx2.MockTransport(handler),
        base_url=API_BASE_URL,
    ) as client:
        response = client.system_one(state=state, questions=questions)
    normalized = normalize_response(response, latency_ms=1.0)
    body = observed["body"]
    primary_order = tuple(body["questions"]["next_action_primary"]["criteria"])
    sensitivity_order = tuple(body["questions"]["next_action_order_sensitivity"]["criteria"])
    if (
        observed["method"] != "POST"
        or observed["url"] != f"{API_BASE_URL}{API_ENDPOINT}"
        or observed["authorized"] is not True
        or body["model"] != MODEL_ID
        or tuple(body["questions"]) != QUESTION_IDS
        or primary_order != PRIMARY_ACTION_ORDER
        or sensitivity_order != SENSITIVITY_ACTION_ORDER
    ):
        raise CandidateError("TypeSafe SDK 模拟请求合同漂移")
    return {
        "provider_calls": 0,
        "credential_reads": 0,
        "transport": "httpx2.MockTransport",
        "request_fingerprint": request_fingerprint(state, questions),
        "normalized_response": normalized,
    }


def preflight() -> dict[str, Any]:
    manifest, pool = load_contract()
    installed_version = version(SDK_DISTRIBUTION)
    if installed_version != SDK_VERSION:
        raise CandidateError(f"TypeSafe SDK 版本漂移: {installed_version} != {SDK_VERSION}")
    if not PREREGISTRATION.is_file():
        raise CandidateError("缺少 candidate 预注册")
    if not API_AUDIT.is_file():
        raise CandidateError("缺少 Jev API 合同审计")
    mock = mock_sdk_roundtrip()
    return {
        "ready": True,
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "project_count": len(pool["tasks"]),
        "evaluation_state_count": manifest["data_contract"]["evaluation"]["state_count"],
        "sdk_version": installed_version,
        "model": MODEL_ID,
        "provider_calls": mock["provider_calls"],
        "credential_reads": mock["credential_reads"],
        "model_tokens": 0,
        "provider_evidence_writes": 0,
        "mock_request_fingerprint": mock["request_fingerprint"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "validate", "show-plan", "mock-check", "preflight"):
        subparsers.add_parser(command)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "generate":
        generate_contract_files()
        print(v1.canonical_sha256(v1.load_json(DEFAULT_MANIFEST)))
        return 0
    if args.command == "validate":
        manifest, _pool = load_contract()
        print(v1.canonical_sha256(manifest))
        return 0
    if args.command == "show-plan":
        manifest, _pool = load_contract()
        print(
            json.dumps(
                {
                    "identity": manifest["identity"],
                    "status": manifest["status"],
                    "provider_contract": manifest["provider_contract"],
                    "budget": manifest["budget"],
                    "candidate_thresholds": manifest["candidate_thresholds"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "mock-check":
        print(json.dumps(mock_sdk_roundtrip(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(json.dumps(preflight(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
