"""Issue #222 R3 Make agent construction gate 的零 provider 测试。"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_opaque_provenance_r3_make_agent_construction_gate.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r3-make-execution.json"


def _load_module():
    scripts = str(SCRIPT_PATH.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(
        "forge_opaque_provenance_r3_make_agent_construction_gate_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_module()


def _manifest() -> dict:
    return gate.protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)


def test_checkpoint_message_shape_matches_interrupted_continuation() -> None:
    messages = gate.checkpoint_messages()
    assert [type(message).__name__ for message in messages] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
    ]
    assert messages[1].tool_calls[0]["name"] == "submit_build_result"
    assert messages[1].tool_calls[0]["id"] == messages[2].tool_call_id


def test_full_agent_construction_reaches_exactly_one_fake_request(
    tmp_path: Path,
) -> None:
    result = asyncio.run(
        gate.run_success_probe(
            _manifest(),
            ledger_path=tmp_path / "success.jsonl",
        )
    )
    assert result["status"] == "passed"
    assert result["restored_message_count"] == 3
    assert result["final_message_count"] == 4
    assert result["model_calls"] == 1
    assert result["bound_tool_count"] == 2
    assert result["parallel_tool_calls"] is False
    assert result["request_evidence"] == {
        "model.request_started": 1,
        "model.request_completed": 1,
        "model.request_failed": 0,
        "model.request_cancelled": 0,
    }
    assert all(value == 0 for value in result["action_budget_consumed"].values())
    assert result["active_experiment_released"] is True


def test_injected_pre_model_failure_is_invalid_and_releases_context(
    tmp_path: Path,
) -> None:
    result = gate.run_failure_probe(ledger_path=tmp_path / "failure.jsonl")
    assert result == {
        "status": "passed",
        "classification": "pre_model_execution_error",
        "terminal_error_class": "AttributeError",
        "model_requests": 0,
        "active_experiment_released": True,
    }


def test_cleanup_probe_deactivates_before_cleanup() -> None:
    result = gate.run_cleanup_probe()
    assert result["status"] == "passed"
    assert result["calls"][-1].startswith("cleanup:")
    assert all(call.startswith("deactivate:") for call in result["calls"][:-1])


def test_validate_gate_is_zero_external_effect() -> None:
    result = asyncio.run(gate.validate_gate(_manifest()))
    assert result["manifest_sha256"] == gate.EXPECTED_MANIFEST_SHA256
    assert result["success_probe"]["status"] == "passed"
    assert result["failure_probe"]["status"] == "passed"
    assert result["cleanup_probe"]["status"] == "passed"
    assert result["temporary_ledger_deleted"] is True
    assert (
        result["provider_calls"],
        result["credential_read"],
        result["docker_executed"],
        result["formal_evidence_writes"],
        result["model_tokens"],
        result["checkpoint_created"],
        result["pair_executed"],
    ) == (0, False, False, 0, 0, False, False)


def test_source_contains_no_provider_credential_or_docker_path() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "create_agent(" in source
    assert "build_subagent_runtime_middlewares" in source
    assert "model.request_started" in source
    for forbidden in (
        "create_chat_model",
        "DEEPSEEK_API_KEY",
        "os.environ",
        "docker.from_env",
        "subprocess.run",
        "requests.",
        "httpx.",
    ):
        assert forbidden not in source
