from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

from deerflow.tools.builtins.task_tool import _with_benchmark_constraints

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "forge_formal_runtime_protocol.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_benchmark_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-formal-v1.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-formal-v1.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


formal = _load_module("forge_formal_runtime_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_benchmark_runner_formal_test", RUNNER_PATH)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_generated_manifest_is_committed_and_schema_valid() -> None:
    manifest = load_manifest()
    assert formal.generate_manifest() == manifest
    assert formal.validate_manifest(manifest) == manifest
    assert len(manifest["cases"]) == 30
    assert len(manifest["collection_plan"]) == 180
    assert manifest["scope"]["collection_authorized"] is False
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_formal_manifest_binds_source_protocols_budget_and_prompts() -> None:
    manifest = load_manifest()
    assert set(manifest["prompt_sha256"]) == formal.PROMPT_PATHS
    assert manifest["budget"]["budget_sha256"] == formal.canonical_sha256(manifest["budget"]["policy"])
    assert manifest["schedule_sha256"] == ("9cfca53bb8c7ab8f07eb5c9a852383eb1877dc377cf56bb834b8eee3587fa469")
    assert manifest["source_protocols"]["case_protocol"]["sha256"] == ("ce9cc50f9ade201d20a65f057ba6763732c4190259d71980edf155c92a5b8210")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["scope"].update(collection_authorized=True),
        lambda value: value["cases"][0]["protocol"].update(source_subdir="../escape"),
        lambda value: value["collection_plan"].reverse(),
        lambda value: value["budget"].update(budget_sha256="0" * 64),
    ],
)
def test_formal_manifest_rejects_protocol_drift(mutation) -> None:
    manifest = copy.deepcopy(load_manifest())
    mutation(manifest)
    with pytest.raises(formal.BenchmarkError):
        formal.validate_manifest(manifest)


def test_runner_loads_formal_policy_and_injects_case_protocol() -> None:
    manifest = runner._load_manifest(MANIFEST_PATH)
    case = manifest["cases"][0]
    policy = runner.build_policy(
        manifest,
        case_id=case["id"],
        condition_id="richlab-gpt-5.5",
        repetition=1,
    )
    prompt = _with_benchmark_constraints("compile", policy)
    assert policy.source_subdir == case["protocol"]["source_subdir"]
    assert list(policy.bootstrap_commands) == case["protocol"]["bootstrap_commands"]
    assert list(policy.build_targets) == case["protocol"]["build_targets"]
    assert case["oracle"]["required_artifacts"][0]["build_output_path"] in prompt
    assert case["oracle"]["required_artifacts"][0]["relative_path"] in prompt


def test_unauthorized_formal_protocol_cannot_create_ledger_or_run(
    tmp_path: Path,
) -> None:
    manifest = load_manifest()
    with pytest.raises(runner.RunnerError, match="not authorized"):
        runner.create_attempt(
            manifest,
            case_id=manifest["cases"][0]["id"],
            condition_id=manifest["conditions"][0]["id"],
            repetition=1,
            output_dir=tmp_path,
            check_endpoint=False,
        )
    assert list(tmp_path.rglob("*.jsonl")) == []
    with pytest.raises(runner.RunnerError, match="not authorized"):
        runner.run_attempt(manifest, tmp_path / "missing.jsonl")


def test_existing_pilot_manifest_remains_supported() -> None:
    manifest = runner._load_manifest(REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v8.json")
    policy = runner.build_policy(
        manifest,
        case_id="fmt",
        condition_id="richlab-gpt-5.5",
        repetition=1,
    )
    assert policy.source_subdir == "."
    assert policy.bootstrap_commands == ()
    assert policy.build_targets == ()
    assert policy.artifact_instructions == ()
    assert "source_subdir" not in policy.to_payload()
