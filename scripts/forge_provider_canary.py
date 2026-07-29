#!/usr/bin/env python3
"""Run one bounded, secret-safe provider canary outside the frozen pilots."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(
    os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[1])
).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(Path(__file__).resolve().parent)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

from deerflow.compile.evidence import (  # noqa: E402
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
)
from deerflow.compile.operations import (  # noqa: E402
    finalize_unfinished_thread_sessions_impl,
    get_compile_services,
)

import forge_benchmark_runner  # noqa: E402

PROTOCOL_VERSION = "forge-provider-canary-v1"
TARGET_REPOSITORY = "https://github.com/MattClarkson/CMakeHelloWorld.git"
TARGET_COMMIT = "6fda0b169299b1241ed883c8d4af8519da30ce52"
TARGET_BUILD_SYSTEM = "cmake"
COMPILE_IMAGE = "autocompiler:gcc13"
ALLOWED_MODELS = {
    "gpt-5.5": {
        "provider": "richlab",
        "endpoint": "https://richlab-api-x.choosefire.com/v1",
        "credential_env": "OpenAI_AK",
    },
    "deepseek-v4-flash": {
        "provider": "deepseek",
        "endpoint": "https://api.deepseek.com",
        "credential_env": "DEEPSEEK_API_KEY",
    },
}
_SAFE_MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_USAGE_KEYS = ("input_tokens", "output_tokens", "total_tokens")
_COMPILE_TOOL_NAMES = frozenset(
    {
        "prepare_compile_session",
        "clone_repository",
        "identify_build_system",
        "task",
        "run_container_bash",
        "submit_build_result",
        "finalize_session",
    }
)


class CanaryError(ValueError):
    """A bounded canary validation failure."""


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _protocol_payload(model_name: str, image_id: str) -> dict[str, Any]:
    model = ALLOWED_MODELS[model_name]
    return {
        "protocol_version": PROTOCOL_VERSION,
        "repository_url": TARGET_REPOSITORY,
        "commit_sha": TARGET_COMMIT,
        "build_system": TARGET_BUILD_SYSTEM,
        "compile_image": COMPILE_IMAGE,
        "image_id": image_id,
        "provider": model["provider"],
        "model_name": model_name,
        "endpoint": model["endpoint"],
        "credential_env": model["credential_env"],
        "request_timeout_seconds": 120,
        "model_max_retries": 0,
        "compiler_model_turn_limit": 36,
        "compiler_graph_recursion_limit": 96,
        "compiler_wall_clock_seconds": 900,
        "compiler_post_build_reserve_seconds": 120,
        "memory_enabled": False,
        "skills_enabled": False,
        "condition_attempt_limit": 1,
        "fallback_enabled": False,
    }


def _inspect_image_id() -> str:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", COMPILE_IMAGE],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CanaryError("compile_image_unavailable") from exc
    image_id = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise CanaryError("compile_image_unavailable")
    return image_id


def _build_policy(model_name: str, image_id: str) -> ExperimentPolicy:
    model = ALLOWED_MODELS[model_name]
    protocol = _protocol_payload(model_name, image_id)
    return ExperimentPolicy(
        benchmark_id=PROTOCOL_VERSION,
        manifest_sha256=_canonical_sha256(protocol),
        case_id="cmake-hello-world",
        condition=model["provider"],
        repetition=1,
        expected_repo_url=TARGET_REPOSITORY,
        expected_commit_sha=TARGET_COMMIT,
        expected_build_system=TARGET_BUILD_SYSTEM,
        compile_image=COMPILE_IMAGE,
        image_id=image_id,
        model_name=model_name,
        endpoint=model["endpoint"],
        credential_env=model["credential_env"],
        request_timeout_seconds=120,
        model_max_retries=0,
        compiler_max_turns=36,
        subagent_timeout_seconds=900,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=36,
        compiler_graph_recursion_limit=96,
        compiler_wall_clock_seconds=900,
        compiler_post_build_reserve_seconds=120,
    )


async def _consume_stream(
    client: Any, message: str, *, thread_id: str
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "stream_completed": False,
        "event_count": 0,
        "tool_call_count": 0,
        "compile_tool_call_count": 0,
        "usage": {key: 0 for key in _USAGE_KEYS},
    }
    async for event in client.astream(message, thread_id=thread_id):
        summary["event_count"] += 1
        if event.type == "end":
            summary["stream_completed"] = True
            usage = event.data.get("usage") if isinstance(event.data, dict) else None
            if isinstance(usage, dict):
                summary["usage"] = {
                    key: value if type(value) is int and value >= 0 else 0
                    for key in _USAGE_KEYS
                    for value in [usage.get(key)]
                }
            continue
        if event.type != "messages-tuple" or not isinstance(event.data, dict):
            continue
        if event.data.get("type") != "ai":
            continue
        tool_calls = event.data.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            tool_name = tool_call.get("name")
            if not isinstance(tool_name, str):
                continue
            summary["tool_call_count"] += 1
            if tool_name in _COMPILE_TOOL_NAMES:
                summary["compile_tool_call_count"] += 1
    return summary


def _thread_containers(thread_id: str) -> tuple[bool, list[str]]:
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=deerflow.compile.thread_id={thread_id}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, []
    if result.returncode != 0:
        return False, []
    return True, [
        value
        for value in result.stdout.splitlines()
        if re.fullmatch(r"[0-9a-f]{12,64}", value)
    ]


def _reconcile_thread_containers(thread_id: str) -> dict[str, Any]:
    initial_scan_succeeded, observed = _thread_containers(thread_id)
    removed = 0
    for identifier in observed:
        try:
            result = subprocess.run(
                ["docker", "rm", "-f", identifier],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            removed += 1
    final_scan_succeeded, remaining = _thread_containers(thread_id)
    scan_succeeded = initial_scan_succeeded and final_scan_succeeded
    return {
        "scan_succeeded": scan_succeeded,
        "observed_count": len(observed),
        "removed_count": removed,
        "remaining_count": len(remaining),
        "cleanup_succeeded": (
            scan_succeeded and not remaining and removed == len(observed)
        ),
    }


def _safe_session_summary(session: Any | None) -> dict[str, Any]:
    if session is None:
        return {
            "session_count": 0,
            "status": None,
            "repo_matches": False,
            "commit_matches": False,
            "build_system_matches": False,
            "artifact_count": 0,
            "artifact_types": [],
            "verification_status": None,
            "replay_status": None,
            "replay_cleanup_succeeded": False,
            "finalized": False,
        }
    verification = session.verification
    replay = session.replay_attempts[-1] if session.replay_attempts else None
    artifact_types = sorted(
        {
            artifact.artifact_type
            for artifact in session.artifacts
            if isinstance(artifact.artifact_type, str)
        }
    )
    build_system_matches = (
        TARGET_BUILD_SYSTEM in session.build_system_capabilities
        and session.selected_build_system == TARGET_BUILD_SYSTEM
        and session.executed_build_system == TARGET_BUILD_SYSTEM
    )
    return {
        "session_count": 1,
        "status": session.status,
        "repo_matches": session.repo_url.rstrip("/") == TARGET_REPOSITORY.rstrip("/"),
        "commit_matches": session.commit_sha == TARGET_COMMIT,
        "build_system_matches": build_system_matches,
        "artifact_count": len(session.artifacts),
        "artifact_types": artifact_types,
        "verification_status": verification.status
        if verification is not None
        else None,
        "replay_status": replay.status if replay is not None else None,
        "replay_cleanup_succeeded": replay.cleanup_succeeded is True
        if replay is not None
        else False,
        "finalized": session.finalized_at is not None,
    }


def _evidence_summary(events: list[dict[str, Any]]) -> dict[str, int]:
    model_started = [
        event for event in events if event.get("event") == "model.request_started"
    ]
    model_completed = [
        event for event in events if event.get("event") == "model.request_completed"
    ]
    compiler_terminal = [
        event
        for event in events
        if event.get("event") == "agent.subagent_terminated"
        and event.get("payload", {}).get("role") == "compiler"
    ]
    return {
        "model_request_started_count": len(model_started),
        "model_request_completed_count": len(model_completed),
        "compiler_task_terminal_count": len(compiler_terminal),
    }


def _accepted(
    *,
    stream_summary: dict[str, Any],
    session_summary: dict[str, Any],
    evidence_summary: dict[str, int],
    reconciliation: dict[str, Any],
) -> bool:
    return all(
        (
            stream_summary["stream_completed"] is True,
            stream_summary["compile_tool_call_count"] > 0,
            evidence_summary["model_request_started_count"] > 0,
            evidence_summary["model_request_completed_count"]
            == evidence_summary["model_request_started_count"],
            evidence_summary["compiler_task_terminal_count"] == 1,
            session_summary["session_count"] == 1,
            session_summary["status"] == "completed",
            session_summary["repo_matches"] is True,
            session_summary["commit_matches"] is True,
            session_summary["build_system_matches"] is True,
            session_summary["artifact_count"] > 0,
            session_summary["verification_status"] == "passed",
            session_summary["replay_status"] == "passed",
            session_summary["replay_cleanup_succeeded"] is True,
            session_summary["finalized"] is True,
            reconciliation["remaining_count"] == 0,
            reconciliation["cleanup_succeeded"] is True,
        )
    )


def _bounded_classification(exc: BaseException) -> str:
    name = type(exc).__name__
    return (
        name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "CanaryFailure"
    )


async def _run_agent(model_name: str, thread_id: str) -> dict[str, Any]:
    from deerflow.client import DeerFlowClient

    client = DeerFlowClient(
        model_name=model_name,
        thinking_enabled=False,
        subagent_enabled=True,
        plan_mode=False,
        available_skills=set(),
    )
    message = (
        f"Compile the C/C++ repository at {TARGET_REPOSITORY} using exact commit "
        f"{TARGET_COMMIT}. The required build system is CMake. Follow the full "
        "Compile Session workflow, delegate exactly one compiler task, submit "
        "deterministically verified artifacts, require clean replay, and finalize "
        "the session. Do not substitute another repository, commit, build system, "
        "model, or provider."
    )
    return await _consume_stream(client, message, thread_id=thread_id)


def run_canary(
    *,
    model_name: str,
    output_dir: Path,
    wall_clock_timeout_seconds: int,
) -> dict[str, Any]:
    if model_name not in ALLOWED_MODELS or not _SAFE_MODEL_RE.fullmatch(model_name):
        raise CanaryError("model_not_allowed")
    if not 1 <= wall_clock_timeout_seconds <= 1200:
        raise CanaryError("invalid_wall_clock_timeout")

    launch = forge_benchmark_runner.collect_runtime_launch_preflight(output_dir)
    if launch["ready"] is not True:
        return {
            "status": "rejected",
            "classification": "runtime_preflight_failed",
            "model_name": model_name,
            "provider": ALLOWED_MODELS[model_name]["provider"],
            "model_call_issued": False,
            "runtime_preflight": launch,
        }

    model = ALLOWED_MODELS[model_name]
    if not os.environ.get(model["credential_env"], "").strip():
        return {
            "status": "rejected",
            "classification": "credential_missing",
            "model_name": model_name,
            "provider": model["provider"],
            "model_call_issued": False,
            "runtime_preflight": launch,
        }

    image_id = _inspect_image_id()
    protocol = _protocol_payload(model_name, image_id)
    policy = _build_policy(model_name, image_id)
    experiment_id = new_evidence_id("canary")
    physical_attempt_id = new_evidence_id("attempt")
    thread_id = f"provider-canary-{model['provider']}-{uuid.uuid4().hex[:12]}"
    ledger_path = output_dir / f"{physical_attempt_id}.jsonl"
    ledger = ExperimentLedger.create(
        ledger_path,
        experiment_id=experiment_id,
        physical_attempt_id=physical_attempt_id,
        context={
            "protocol": protocol,
            "policy": policy.to_payload(),
            "preflight_ready": True,
            "formal_pilot": False,
        },
    )
    activate_experiment(
        thread_id=thread_id,
        experiment_id=experiment_id,
        physical_attempt_id=physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )

    stream_summary: dict[str, Any] = {
        "stream_completed": False,
        "event_count": 0,
        "tool_call_count": 0,
        "compile_tool_call_count": 0,
        "usage": {key: 0 for key in _USAGE_KEYS},
    }
    classification: str | None = None
    model_call_issued = False
    try:
        model_call_issued = True
        stream_summary = asyncio.run(
            asyncio.wait_for(
                _run_agent(model_name, thread_id),
                timeout=wall_clock_timeout_seconds,
            )
        )
    except Exception as exc:
        classification = _bounded_classification(exc)
        ledger.append(
            "run.failed",
            {"classification": classification},
        )
    finally:
        try:
            finalize_unfinished_thread_sessions_impl(
                thread_id=thread_id,
                interrupted_status="failed" if classification else None,
                error=(
                    "Provider canary ended before compile-session finalization."
                    if classification
                    else None
                ),
            )
        except Exception:
            classification = classification or "SessionFinalizationError"
        deactivate_experiment(thread_id)

    try:
        sessions = sorted(
            get_compile_services().manager.list_sessions(thread_id),
            key=lambda session: session.session_id,
        )
    except Exception:
        sessions = []
        classification = classification or "SessionInspectionError"
    session_summary = _safe_session_summary(sessions[0] if len(sessions) == 1 else None)
    session_summary["session_count"] = len(sessions)
    evidence_summary = _evidence_summary(ledger.read())
    reconciliation = _reconcile_thread_containers(thread_id)
    accepted = (
        len(sessions) == 1
        and classification is None
        and _accepted(
            stream_summary=stream_summary,
            session_summary=session_summary,
            evidence_summary=evidence_summary,
            reconciliation=reconciliation,
        )
    )
    status = "passed" if accepted else "failed"
    result = {
        "status": status,
        "classification": None
        if accepted
        else (classification or "acceptance_gate_failed"),
        "provider": model["provider"],
        "model_name": model_name,
        "model_call_issued": model_call_issued,
        "protocol_sha256": _canonical_sha256(protocol),
        "ledger_name": ledger_path.name,
        "thread_id": thread_id,
        "runtime_preflight": launch,
        "stream": stream_summary,
        "evidence": evidence_summary,
        "session": session_summary,
        "orphan_reconciliation": reconciliation,
    }
    ledger.append(
        "canary.completed",
        {
            "status": status,
            "classification": result["classification"],
            "stream_completed": stream_summary["stream_completed"],
            "compile_tool_call_count": stream_summary["compile_tool_call_count"],
            "model_request_started_count": evidence_summary[
                "model_request_started_count"
            ],
            "model_request_completed_count": evidence_summary[
                "model_request_completed_count"
            ],
            "compiler_task_terminal_count": evidence_summary[
                "compiler_task_terminal_count"
            ],
            "session_count": session_summary["session_count"],
            "commit_matches": session_summary["commit_matches"],
            "build_system_matches": session_summary["build_system_matches"],
            "verification_status": session_summary["verification_status"],
            "replay_status": session_summary["replay_status"],
            "replay_cleanup_succeeded": session_summary["replay_cleanup_succeeded"],
            "session_finalized": session_summary["finalized"],
            "remaining_orphan_count": reconciliation["remaining_count"],
        },
    )
    ledger.append("experiment.completed", {"status": status})
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(ALLOWED_MODELS), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--wall-clock-timeout", type=int, default=1000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = run_canary(
            model_name=args.model,
            output_dir=args.output_dir,
            wall_clock_timeout_seconds=args.wall_clock_timeout,
        )
    except (CanaryError, OSError, ValueError) as exc:
        result = {
            "status": "rejected",
            "classification": (
                str(exc)
                if isinstance(exc, CanaryError)
                else _bounded_classification(exc)
            ),
            "model_name": args.model,
            "model_call_issued": False,
        }
    _emit(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
