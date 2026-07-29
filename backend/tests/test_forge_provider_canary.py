from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_provider_canary.py"
SPEC = importlib.util.spec_from_file_location("forge_provider_canary", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
forge_provider_canary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = forge_provider_canary
SPEC.loader.exec_module(forge_provider_canary)


def _successful_session():
    return SimpleNamespace(
        status="completed",
        repo_url=forge_provider_canary.TARGET_REPOSITORY,
        commit_sha=forge_provider_canary.TARGET_COMMIT,
        build_system_capabilities=["cmake"],
        selected_build_system="cmake",
        executed_build_system="cmake",
        artifacts=[
            SimpleNamespace(artifact_type="executable"),
            SimpleNamespace(artifact_type="executable"),
        ],
        verification=SimpleNamespace(status="passed"),
        replay_attempts=[
            SimpleNamespace(status="passed", cleanup_succeeded=True),
        ],
        finalized_at="2026-07-29T00:00:00+00:00",
    )


def test_protocol_separates_provider_credentials_and_endpoints():
    richlab = forge_provider_canary._protocol_payload(
        "gpt-5.5",
        "sha256:" + "1" * 64,
    )
    deepseek = forge_provider_canary._protocol_payload(
        "deepseek-v4-flash",
        "sha256:" + "1" * 64,
    )

    assert richlab["provider"] == "richlab"
    assert richlab["credential_env"] == "OpenAI_AK"
    assert deepseek["provider"] == "deepseek"
    assert deepseek["credential_env"] == "DEEPSEEK_API_KEY"
    assert richlab["endpoint"] != deepseek["endpoint"]
    assert richlab["model_max_retries"] == 0
    assert deepseek["fallback_enabled"] is False


def test_policy_pins_exact_target_and_build_system():
    image_id = "sha256:" + "1" * 64
    policy = forge_provider_canary._build_policy("gpt-5.5", image_id)

    assert policy.expected_repo_url == forge_provider_canary.TARGET_REPOSITORY
    assert policy.expected_commit_sha == forge_provider_canary.TARGET_COMMIT
    assert policy.expected_build_system == "cmake"
    assert policy.image_id == image_id
    assert policy.model_name == "gpt-5.5"
    assert policy.memory_enabled is False
    assert policy.skills_enabled is False


def test_safe_session_summary_excludes_paths_commands_and_model_content():
    summary = forge_provider_canary._safe_session_summary(_successful_session())

    assert summary["commit_matches"] is True
    assert summary["build_system_matches"] is True
    assert summary["artifact_count"] == 2
    assert summary["artifact_types"] == ["executable"]
    assert set(summary) == {
        "session_count",
        "status",
        "repo_matches",
        "commit_matches",
        "build_system_matches",
        "artifact_count",
        "artifact_types",
        "verification_status",
        "replay_status",
        "replay_cleanup_succeeded",
        "finalized",
    }


def test_acceptance_requires_full_clean_replay_and_finalization():
    session = forge_provider_canary._safe_session_summary(_successful_session())
    stream = {
        "stream_completed": True,
        "compile_tool_call_count": 6,
    }
    reconciliation = {
        "remaining_count": 0,
        "cleanup_succeeded": True,
    }
    evidence = {
        "model_request_started_count": 3,
        "model_request_completed_count": 3,
        "compiler_task_terminal_count": 1,
    }

    assert forge_provider_canary._accepted(
        stream_summary=stream,
        session_summary=session,
        evidence_summary=evidence,
        reconciliation=reconciliation,
    )

    session["replay_cleanup_succeeded"] = False
    assert not forge_provider_canary._accepted(
        stream_summary=stream,
        session_summary=session,
        evidence_summary=evidence,
        reconciliation=reconciliation,
    )

    session["replay_cleanup_succeeded"] = True
    evidence["compiler_task_terminal_count"] = 2
    assert not forge_provider_canary._accepted(
        stream_summary=stream,
        session_summary=session,
        evidence_summary=evidence,
        reconciliation=reconciliation,
    )


def test_stream_consumer_counts_tools_without_returning_content_or_arguments():
    class Client:
        async def astream(self, _message: str, *, thread_id: str):
            assert thread_id == "thread-safe"
            yield SimpleNamespace(
                type="messages-tuple",
                data={
                    "type": "ai",
                    "content": "private model text",
                    "tool_calls": [
                        {
                            "name": "prepare_compile_session",
                            "args": {"credential": "must-not-be-returned"},
                        },
                        {
                            "name": "unrelated_tool",
                            "args": {"path": "private"},
                        },
                    ],
                },
            )
            yield SimpleNamespace(
                type="end",
                data={
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                        "provider_payload": "private",
                    }
                },
            )

    summary = asyncio.run(
        forge_provider_canary._consume_stream(
            Client(),
            "message",
            thread_id="thread-safe",
        )
    )

    assert summary == {
        "stream_completed": True,
        "event_count": 2,
        "tool_call_count": 2,
        "compile_tool_call_count": 1,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        },
    }


def test_runtime_preflight_failure_issues_no_model_call(tmp_path, monkeypatch):
    monkeypatch.setattr(
        forge_provider_canary.forge_benchmark_runner,
        "collect_runtime_launch_preflight",
        lambda _output_dir: {
            "ready": False,
            "checks": {"runtime_imports_available": False},
        },
    )

    result = forge_provider_canary.run_canary(
        model_name="gpt-5.5",
        output_dir=tmp_path,
        wall_clock_timeout_seconds=1000,
    )

    assert result["status"] == "rejected"
    assert result["classification"] == "runtime_preflight_failed"
    assert result["model_call_issued"] is False


def test_missing_credential_issues_no_model_call(tmp_path, monkeypatch):
    monkeypatch.setattr(
        forge_provider_canary.forge_benchmark_runner,
        "collect_runtime_launch_preflight",
        lambda _output_dir: {"ready": True, "checks": {}},
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    result = forge_provider_canary.run_canary(
        model_name="deepseek-v4-flash",
        output_dir=tmp_path,
        wall_clock_timeout_seconds=1000,
    )

    assert result["status"] == "rejected"
    assert result["classification"] == "credential_missing"
    assert result["model_call_issued"] is False


def test_unallowed_model_is_rejected_before_runtime_preflight(tmp_path):
    with pytest.raises(
        forge_provider_canary.CanaryError,
        match="model_not_allowed",
    ):
        forge_provider_canary.run_canary(
            model_name="deepseek-v4-pro",
            output_dir=tmp_path,
            wall_clock_timeout_seconds=1000,
        )


def test_thread_container_scan_uses_exact_label(monkeypatch):
    observed: list[list[str]] = []

    def fake_run(arguments, **_kwargs):
        observed.append(arguments)
        return SimpleNamespace(returncode=0, stdout="abc123def456\n")

    monkeypatch.setattr(forge_provider_canary.subprocess, "run", fake_run)

    assert forge_provider_canary._thread_containers("provider-canary-richlab-safe") == (True, ["abc123def456"])
    assert observed == [
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=deerflow.compile.thread_id=provider-canary-richlab-safe",
        ]
    ]


def test_mocked_canary_writes_separate_non_pilot_evidence(
    tmp_path,
    monkeypatch,
):
    session = _successful_session()
    session.session_id = "123456789abc"
    monkeypatch.setenv("OpenAI_AK", "present-only-in-process")
    monkeypatch.setattr(
        forge_provider_canary.forge_benchmark_runner,
        "collect_runtime_launch_preflight",
        lambda _output_dir: {"ready": True, "checks": {"fixture": True}},
    )
    monkeypatch.setattr(
        forge_provider_canary,
        "_inspect_image_id",
        lambda: "sha256:" + "1" * 64,
    )

    async def run_agent(_model_name, _thread_id):
        return {
            "stream_completed": True,
            "event_count": 10,
            "tool_call_count": 6,
            "compile_tool_call_count": 6,
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            },
        }

    monkeypatch.setattr(forge_provider_canary, "_run_agent", run_agent)
    monkeypatch.setattr(
        forge_provider_canary,
        "finalize_unfinished_thread_sessions_impl",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        forge_provider_canary,
        "get_compile_services",
        lambda: SimpleNamespace(manager=SimpleNamespace(list_sessions=lambda _thread_id: [session])),
    )
    monkeypatch.setattr(
        forge_provider_canary,
        "_reconcile_thread_containers",
        lambda _thread_id: {
            "scan_succeeded": True,
            "observed_count": 0,
            "removed_count": 0,
            "remaining_count": 0,
            "cleanup_succeeded": True,
        },
    )
    monkeypatch.setattr(
        forge_provider_canary,
        "_evidence_summary",
        lambda _events: {
            "model_request_started_count": 3,
            "model_request_completed_count": 3,
            "compiler_task_terminal_count": 1,
        },
    )

    result = forge_provider_canary.run_canary(
        model_name="gpt-5.5",
        output_dir=tmp_path,
        wall_clock_timeout_seconds=1000,
    )

    assert result["status"] == "passed"
    ledger_text = (tmp_path / result["ledger_name"]).read_text(encoding="utf-8")
    assert '"formal_pilot":false' in ledger_text
    assert '"event":"canary.completed"' in ledger_text
    assert '"event":"experiment.completed"' in ledger_text
    assert "present-only-in-process" not in ledger_text


def test_model_exception_text_is_not_emitted_or_persisted(
    tmp_path,
    monkeypatch,
):
    secret_marker = "private-credential-marker"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "present-only-in-process")
    monkeypatch.setattr(
        forge_provider_canary.forge_benchmark_runner,
        "collect_runtime_launch_preflight",
        lambda _output_dir: {"ready": True, "checks": {"fixture": True}},
    )
    monkeypatch.setattr(
        forge_provider_canary,
        "_inspect_image_id",
        lambda: "sha256:" + "1" * 64,
    )

    async def fail_agent(_model_name, _thread_id):
        raise RuntimeError(secret_marker)

    monkeypatch.setattr(forge_provider_canary, "_run_agent", fail_agent)
    monkeypatch.setattr(
        forge_provider_canary,
        "finalize_unfinished_thread_sessions_impl",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        forge_provider_canary,
        "get_compile_services",
        lambda: SimpleNamespace(manager=SimpleNamespace(list_sessions=lambda _thread_id: [])),
    )
    monkeypatch.setattr(
        forge_provider_canary,
        "_reconcile_thread_containers",
        lambda _thread_id: {
            "scan_succeeded": True,
            "observed_count": 0,
            "removed_count": 0,
            "remaining_count": 0,
            "cleanup_succeeded": True,
        },
    )

    result = forge_provider_canary.run_canary(
        model_name="deepseek-v4-flash",
        output_dir=tmp_path,
        wall_clock_timeout_seconds=1000,
    )

    assert result["status"] == "failed"
    assert result["classification"] == "RuntimeError"
    serialized = json.dumps(result)
    ledger_text = (tmp_path / result["ledger_name"]).read_text(encoding="utf-8")
    assert secret_marker not in serialized
    assert secret_marker not in ledger_text
