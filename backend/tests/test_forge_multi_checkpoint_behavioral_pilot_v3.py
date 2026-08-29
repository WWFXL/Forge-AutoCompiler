"""Issue #170 多 checkpoint behavioral pilot v3 的零请求协议门禁。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts/forge_multi_checkpoint_behavioral_pilot_v3_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts/forge_multi_checkpoint_behavioral_pilot_v3_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-verifier-multi-checkpoint-behavioral-pilot-v3.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-multi-checkpoint-behavioral-pilot-v3.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_multi_checkpoint_behavioral_pilot_v3_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_multi_checkpoint_behavioral_pilot_v3_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_generated_manifest_schema_and_frozen_components_are_current() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    protocol.verify_frozen_components(manifest, REPO_ROOT)


def test_schedule_has_three_cases_two_balanced_pairs_and_twelve_arms() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    schedule = manifest["schedule"]
    assert len(schedule) == 6
    assert sum(len(pair["arm_order"]) for pair in schedule) == 12
    for case_id in protocol.CASE_IDS:
        case_pairs = [pair for pair in schedule if pair["case_id"] == case_id]
        assert [pair["arm_order"] for pair in case_pairs] == [
            ["baseline", "treatment"],
            ["treatment", "baseline"],
        ]
    assert manifest["schedule_sha256"] == protocol.canonical_sha256(schedule)


def test_runner_maps_every_pair_to_the_frozen_case() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    plan = runner.build_pilot_plan(manifest, REPO_ROOT)
    assert plan["pair_count"] == 6
    assert plan["arm_count"] == 12
    assert plan["maximum_recorded_tokens"] == 1_440_000
    by_case = {pair["case"]["case_id"]: pair["case"] for pair in plan["pairs"]}
    assert {case_id: case["build_system"] for case_id, case in by_case.items()} == {
        "cppitertools": "cmake",
        "janet": "make",
        "libcheck": "autotools",
    }
    assert by_case["janet"]["artifact"]["staged_relative_path"] == "libjanet.a"
    assert by_case["libcheck"]["commands"][0]["role"] == "dependency_setup"
    assert all(pair["runner_mode"] == "protocol_plan_only" for pair in plan["pairs"])
    assert all(pair["provider_calls_authorized"] is False for pair in plan["pairs"])


def test_authorization_budget_and_analysis_contract_are_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["authorization"] == {
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/170",
        "protocol_freeze_authorized": True,
        "provider_calls_authorized": False,
        "formal_attempts_authorized": False,
        "model_tokens_authorized": 0,
        "pilot_collection_authorized": False,
    }
    assert manifest["budget"]["recorded_tokens_per_arm"] == 120_000
    assert manifest["budget"]["recorded_tokens_per_pair"] == 240_000
    assert manifest["budget"]["stage_maximum_recorded_tokens"] == 1_440_000
    assert manifest["analysis"]["per_case_outputs"] == [
        "paired_four_cell",
        "requests",
        "recorded_tokens",
        "failure_transitions",
    ]
    assert manifest["analysis"]["cross_case_summary"] == "equal_weight_macro_average"
    assert set(manifest["analysis"]["case_weights"].values()) == {"1/3"}
    assert manifest["analysis"]["p_value_computed"] is False
    assert manifest["analysis"]["providers_pooled"] is False
    assert manifest["analysis"]["model_ranking_performed"] is False


def test_schema_and_semantics_reject_authorization_or_schedule_drift() -> None:
    schema = _load(SCHEMA_PATH)
    manifest = _load(MANIFEST_PATH)
    authorized = copy.deepcopy(manifest)
    authorized["authorization"]["provider_calls_authorized"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(authorized)
    with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
        protocol.validate_manifest(authorized, REPO_ROOT)

    reordered = copy.deepcopy(manifest)
    reordered["schedule"][0]["arm_order"].reverse()
    with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
        protocol.validate_manifest(reordered, REPO_ROOT)


def test_runner_has_no_real_collection_path() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    with pytest.raises(runner.RunnerPlanError, match="does not authorize"):
        runner.execute_collection(manifest)
    source = RUNNER_PATH.read_text(encoding="utf-8")
    for forbidden in ("os.environ", "create_chat_model", "execute_real_pair", "DEEPSEEK_API_KEY"):
        assert forbidden not in source
