from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_PATH = REPO_ROOT / "scripts" / "forge_failure_checkpoint_prototype.py"
FIXTURE_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-failure-checkpoint-fixture-v1.schema.json"
PACKET_SCHEMA_PATH = REPO_ROOT / "benchmarks" / "schemas" / "forge-verifier-repair-packet-v1.schema.json"
FIXTURE_DIR = REPO_ROOT / "benchmarks" / "fixtures" / "failure-checkpoints"
FIXTURE_DIGESTS = {
    "slot-007-openthread.json": "9a4a73173cf41d7cfd457133e23184f1685dcb9b2efe9ca64883e73e085bef27",
    "slot-010-mupdf.json": "b7dc968fa484320250a985ee094fdc4660b7778ca1320281100b3a334a3d7fa1",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_failure_checkpoint_prototype_test", PROTOTYPE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prototype = _load_module()


def _fixture_paths() -> list[Path]:
    return [FIXTURE_DIR / name for name in sorted(FIXTURE_DIGESTS)]


def _assert_sanitized(value) -> None:
    forbidden_keys = {
        "api_key",
        "credential_env",
        "endpoint",
        "physical_attempt_id",
        "thread_id",
        "session_id",
    }
    if isinstance(value, dict):
        assert forbidden_keys.isdisjoint(value)
        for child in value.values():
            _assert_sanitized(child)
    elif isinstance(value, list):
        for child in value:
            _assert_sanitized(child)
    elif isinstance(value, str):
        assert not value.startswith(("sk-", "thread_", "physical_attempt_"))


def test_fixtures_have_frozen_schema_hash_and_no_runtime_identity() -> None:
    fixture_schema = json.loads(FIXTURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    packet_schema = json.loads(PACKET_SCHEMA_PATH.read_text(encoding="utf-8"))

    for path in _fixture_paths():
        fixture = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.validate(fixture, fixture_schema)
        jsonschema.validate(fixture["repair_packet"], packet_schema)
        assert prototype.load_fixture(path)["fixture_sha256"] == FIXTURE_DIGESTS[path.name]
        assert prototype.fixture_payload_sha256(fixture) == FIXTURE_DIGESTS[path.name]
        _assert_sanitized(fixture)


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda path: path.stem)
def test_sqlite_checkpoint_branches_and_resumes_without_repeating_submit(
    fixture_path: Path,
    tmp_path: Path,
) -> None:
    fixture_bytes_before = fixture_path.read_bytes()
    fixture = prototype.load_fixture(fixture_path)
    counters = prototype.PrototypeCounters()
    database = tmp_path / "failure-checkpoint.sqlite"
    source_thread = f"{fixture['fixture_id']}-neutral"
    baseline_thread = f"{fixture['fixture_id']}-baseline"
    treatment_thread = f"{fixture['fixture_id']}-treatment"

    with SqliteSaver.from_conn_string(str(database)) as saver:
        saver.setup()
        runtime = prototype.FailureCheckpointPrototype(fixture, saver, counters)
        source_config = runtime.capture(source_thread)
        source = runtime.graph.get_state(source_config)

        assert tuple(source.next) == (prototype.CONTINUATION_NODE,)
        assert source.config["configurable"]["checkpoint_id"]
        assert [type(message) for message in source.values["messages"]] == [
            HumanMessage,
            AIMessage,
            ToolMessage,
        ]
        request = source.values["messages"][1]
        feedback = source.values["messages"][2]
        assert request.tool_calls[0] == {
            "name": "submit_build_result",
            "args": {},
            "id": "fixture-submit-call",
            "type": "tool_call",
        }
        assert feedback.tool_call_id == "fixture-submit-call"

        baseline_config = runtime.derive_arm(
            source_config,
            arm=prototype.BASELINE_ARM,
            session_id="fixture-baseline-session",
            thread_id=baseline_thread,
        )
        treatment_config = runtime.derive_arm(
            source_config,
            arm=prototype.TREATMENT_ARM,
            session_id="fixture-treatment-session",
            thread_id=treatment_thread,
        )
        baseline = runtime.graph.get_state(baseline_config)
        treatment = runtime.graph.get_state(treatment_config)

        assert tuple(baseline.next) == tuple(treatment.next) == (prototype.CONTINUATION_NODE,)
        assert prototype.state_difference_paths(baseline.values, treatment.values) == {
            "arm",
            "messages[2].data.content",
            "session_id",
        }
        assert prototype.canonical_state_for_pairing(baseline.values) == prototype.canonical_state_for_pairing(treatment.values)
        assert counters.submit_calls == 1
        assert counters.fake_model_calls == 0

    # 重新打开 SQLite 模拟进程级冷恢复，不能依赖前一个 graph 对象的内存状态。
    with SqliteSaver.from_conn_string(str(database)) as saver:
        saver.setup()
        recovered = prototype.FailureCheckpointPrototype(fixture, saver, counters)
        baseline_result = recovered.resume(recovered.config(baseline_thread))
        treatment_result = recovered.resume(recovered.config(treatment_thread))

        assert recovered.graph.get_state(recovered.config(baseline_thread)).next == ()
        assert recovered.graph.get_state(recovered.config(treatment_thread)).next == ()
        assert len(baseline_result["messages"]) == len(treatment_result["messages"]) == 4
        assert counters.submit_calls == 1
        assert counters.fake_model_calls == 2
        assert counters.provider_calls == counters.docker_calls == counters.physical_attempts == 0

    assert fixture_path.read_bytes() == fixture_bytes_before
    assert hashlib.sha256(fixture_path.read_bytes()).hexdigest() == hashlib.sha256(fixture_bytes_before).hexdigest()


def test_prototype_has_no_provider_docker_or_attempt_imports() -> None:
    source = PROTOTYPE_PATH.read_text(encoding="utf-8")
    assert "deerflow.models" not in source
    assert "deerflow.compile.docker_runtime" not in source
    assert "forge_benchmark_runner" not in source
