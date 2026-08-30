#!/usr/bin/env python3
"""Issue #194 runtime-parity 拒绝原因零 provider 可观测性门禁。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_provenance_runtime_parity_gate as parity  # noqa: E402

from deerflow.compile.evidence import (  # noqa: E402
    EvidenceError,
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    get_active_experiment,
    new_evidence_id,
    record_agent_tool_failure,
    record_experiment_event,
    request_thread_id,
)

SCHEMA_VERSION = "forge-opaque-provenance-rejection-observability-gate-1.0.0"
OBSERVATION_EVENT = "agent.tool_rejection_observed"

_BOUNDED_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MODEL_REQUEST_ID_RE = re.compile(r"^model_request_[0-9a-f]{32}$")
_ALLOWED_REJECTION_CLASSIFICATIONS = {
    "action_claim_empty",
    "action_role_invalid",
    "action_unknown",
    "artifact_stage_budget_exhausted",
    "artifact_stage_identity_drift",
    "artifact_stage_shape_invalid",
    "compound_build_stage_forbidden",
    "compound_shell_forbidden",
    "container_path_invalid",
    "forbidden_action_role",
    "inspection_budget_exhausted",
    "invalid_command_role",
    "repair_build_arguments_invalid",
    "repair_build_budget_exhausted",
    "repair_build_directory_drift",
    "repair_build_invocation_invalid",
    "repair_build_target_drift",
    "runtime_parity_policy_drift",
    "shell_token_invalid",
    "submit_budget_exhausted",
}
_ALLOWED_ACTION_KINDS = {
    "artifact_stage",
    "command",
    "inspection",
    "repair_build",
    "submit",
    "unknown",
}
_LEGACY_FAILURE_FIELDS = {
    "failure_id",
    "role",
    "tool_name",
    "tool_call_id",
    "exception_class",
    "execution_mode",
    "terminal",
}

_GATE_REJECTIONS = {
    "action limits drifted from the preregistered gate": ("runtime_parity_policy_drift", "unknown"),
    "at least one action must be claimed": ("action_claim_empty", "unknown"),
    "command uses a forbidden post-checkpoint role": ("forbidden_action_role", "command"),
    "repair build and artifact stage must be separate actions": ("compound_build_stage_forbidden", "command"),
    "command role is outside the runtime-parity action set": ("action_role_invalid", "command"),
    "repair build must be a direct cmake --build invocation": ("repair_build_invocation_invalid", "repair_build"),
    "repair build directory drifted from the frozen identity": ("repair_build_directory_drift", "repair_build"),
    "repair build target drifted from the frozen identity": ("repair_build_target_drift", "repair_build"),
    "repair build contains non-preregistered arguments": ("repair_build_arguments_invalid", "repair_build"),
    "artifact stage must copy exactly one frozen output": ("artifact_stage_shape_invalid", "artifact_stage"),
    "artifact stage identity drifted from the frozen output": ("artifact_stage_identity_drift", "artifact_stage"),
}


class ObservableRuntimeParityGateError(RuntimeError):
    """为冻结 gate 的拒绝增加有界、非敏感的稳定元数据。"""

    def __init__(self, message: str, *, classification: str, action_kind: str) -> None:
        super().__init__(message)
        self.evidence_rejection_classification = classification
        self.evidence_action_kind = action_kind


def _action_hint(command_role: str) -> str:
    return {
        "build": "repair_build",
        "artifact_stage": "artifact_stage",
    }.get(command_role, "inspection")


def _observable_gate_error(exc: parity.RuntimeParityGateError, *, action_hint: str) -> ObservableRuntimeParityGateError:
    message = str(exc)
    metadata = _GATE_REJECTIONS.get(message)
    if metadata is None and message in {"command is not valid shell token input", "compound shell commands are forbidden", "container path must be absolute"}:
        classification = {
            "command is not valid shell token input": "shell_token_invalid",
            "compound shell commands are forbidden": "compound_shell_forbidden",
            "container path must be absolute": "container_path_invalid",
        }[message]
        metadata = (classification, action_hint)
    if metadata is None:
        for action in parity.ACTION_LIMITS:
            if message == f"{action} budget exhausted":
                metadata = (f"{action}_budget_exhausted", action)
                break
    if metadata is None and message.startswith("unknown action: "):
        metadata = ("action_unknown", "unknown")
    if metadata is None:
        metadata = ("runtime_parity_policy_drift", "unknown")
    return ObservableRuntimeParityGateError(
        message,
        classification=metadata[0],
        action_kind=metadata[1],
    )


class ObservableRuntimeParityToolAdapter(parity.RuntimeParityToolAdapter):
    """保持 #186 gate 字节冻结，在独立版本层翻译其拒绝。"""

    def run(
        self,
        command: str,
        *,
        timeout_seconds: int = 300,
        workdir: str | None = None,
        command_role: str = "other",
    ) -> Any:
        try:
            return super().run(
                command,
                timeout_seconds=timeout_seconds,
                workdir=workdir,
                command_role=command_role,
            )
        except parity.RuntimeParityGateError as exc:
            raise _observable_gate_error(exc, action_hint=_action_hint(command_role)) from exc
        except EvidenceError as exc:
            if str(exc).startswith("Unsupported compile command role:"):
                raise ObservableRuntimeParityGateError(
                    "unsupported compile command role",
                    classification="invalid_command_role",
                    action_kind="command",
                ) from exc
            raise

    def submit(self, supporting_command_id: str | None = None) -> Any:
        try:
            return super().submit(supporting_command_id)
        except parity.RuntimeParityGateError as exc:
            raise _observable_gate_error(exc, action_hint="submit") from exc


@dataclass
class RejectionObservationRegistry:
    """为单次实验关联 model response 与后续 recoverable tool failure。"""

    origins: dict[tuple[str, str], tuple[str, int]] = field(default_factory=dict)
    ambiguous: set[tuple[str, str]] = field(default_factory=set)

    def register_model_tool_calls(
        self,
        thread_id: str | None,
        response: Any,
        *,
        model_request_id: str,
    ) -> int:
        if get_active_experiment(thread_id) is None:
            return 0
        if not _MODEL_REQUEST_ID_RE.fullmatch(model_request_id):
            raise ValueError("model_request_id is invalid")
        candidates: list[Any] = []
        result = getattr(response, "result", None)
        if isinstance(result, (list, tuple)):
            candidates.extend(result[:8])
        elif result is not None:
            candidates.append(result)
        candidates.append(response)
        tool_calls: list[dict[str, Any]] = []
        for candidate in candidates:
            value = getattr(candidate, "tool_calls", None)
            if isinstance(value, list):
                tool_calls.extend(item for item in value if isinstance(item, dict))
        registered = 0
        seen: set[tuple[str, str]] = set()
        for ordinal, tool_call in enumerate(tool_calls, start=1):
            tool_call_id = tool_call.get("id")
            if not isinstance(tool_call_id, str) or not _BOUNDED_IDENTIFIER_RE.fullmatch(tool_call_id):
                continue
            key = (thread_id or "", tool_call_id)
            duplicate = key in seen or key in self.origins or key in self.ambiguous
            seen.add(key)
            if duplicate:
                removed = self.origins.pop(key, None)
                if removed is not None and removed[0] == model_request_id:
                    registered -= 1
                self.ambiguous.add(key)
                continue
            self.origins[key] = (model_request_id, ordinal)
            registered += 1
        return registered

    def _consume_origin(self, thread_id: str | None, tool_call_id: str) -> tuple[str, int] | None:
        key = (thread_id or "", tool_call_id)
        if key in self.ambiguous:
            return None
        return self.origins.pop(key, None)

    def record_tool_failure(
        self,
        request: Any,
        exc: Exception,
        *,
        execution_mode: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        failure_event = record_agent_tool_failure(
            request,
            exc,
            execution_mode=execution_mode,
        )
        if failure_event is None:
            return None, None
        classification = getattr(exc, "evidence_rejection_classification", None)
        action_kind = getattr(exc, "evidence_action_kind", None)
        if classification not in _ALLOWED_REJECTION_CLASSIFICATIONS or action_kind not in _ALLOWED_ACTION_KINDS:
            return failure_event, None
        tool_call = getattr(request, "tool_call", None)
        if not isinstance(tool_call, dict):
            return failure_event, None
        tool_call_id = tool_call.get("id")
        if not isinstance(tool_call_id, str) or not _BOUNDED_IDENTIFIER_RE.fullmatch(tool_call_id):
            return failure_event, None
        thread_id = request_thread_id(request)
        origin = self._consume_origin(thread_id, tool_call_id)
        if origin is None:
            return failure_event, None
        arguments = tool_call.get("args")
        command = arguments.get("command") if isinstance(arguments, dict) else None
        command_sha256 = hashlib.sha256(command.encode("utf-8")).hexdigest() if isinstance(command, str) else None
        observation = record_experiment_event(
            thread_id,
            OBSERVATION_EVENT,
            failure_id=failure_event["payload"]["failure_id"],
            rejection_classification=classification,
            action_kind=action_kind,
            model_request_id=origin[0],
            tool_ordinal=origin[1],
            command_sha256=command_sha256,
        )
        return failure_event, observation


class _FakeTool:
    def invoke(self, _payload: dict[str, Any]) -> str:
        return "ok"


def _policy() -> ExperimentPolicy:
    return ExperimentPolicy(
        benchmark_id="forge-opaque-provenance-observability-r0",
        manifest_sha256="1" * 64,
        case_id="cppitertools-opaque-provenance-real-docker",
        condition="observability_gate",
        repetition=1,
        expected_repo_url="https://github.com/ryanhaining/cppitertools.git",
        expected_commit_sha="2" * 40,
        expected_build_system="cmake",
        compile_image="autocompiler:gcc13",
        image_id=f"sha256:{'3' * 64}",
        model_name="zero-provider",
        endpoint="https://example.invalid/v1",
        credential_env="UNUSED_ZERO_PROVIDER_CREDENTIAL",
        request_timeout_seconds=300,
        model_max_retries=0,
        compiler_max_turns=1,
        subagent_timeout_seconds=1,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
    )


def _request(thread_id: str, tool_call: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        tool_call=tool_call,
        runtime=SimpleNamespace(context={"thread_id": thread_id, "agent_name": "compiler"}),
    )


def _capture_rejection(adapter: ObservableRuntimeParityToolAdapter, tool_call: dict[str, Any]) -> Exception:
    arguments = tool_call["args"]
    try:
        adapter.run(
            arguments["command"],
            workdir=arguments.get("workdir"),
            command_role=arguments.get("command_role", "other"),
        )
    except ObservableRuntimeParityGateError as exc:
        return exc
    raise RuntimeError("observability fixture did not trigger a rejection")


def validate_gate() -> dict[str, Any]:
    thread_id = new_evidence_id("thread")
    model_request_id = new_evidence_id("model_request")
    tool_calls = [
        {
            "name": "run_container_bash",
            "id": "call-compound-shell",
            "args": {"command": "ls -la && pwd", "command_role": "other"},
        },
        {
            "name": "run_container_bash",
            "id": "call-invalid-role",
            "args": {"command": "ls -la", "command_role": "evidence"},
        },
        {
            "name": "run_container_bash",
            "id": "call-build-drift",
            "args": {
                "command": "cmake --build /workspace/repo/other --target accumulate_examples",
                "command_role": "build",
            },
        },
        {
            "name": "run_container_bash",
            "id": "call-stage-drift",
            "args": {
                "command": "cp build/accumulate_examples /artifacts/other",
                "command_role": "artifact_stage",
            },
        },
        {
            "name": "run_container_bash",
            "id": "call-inspection-budget",
            "args": {"command": "pwd", "command_role": "other"},
        },
    ]
    expected = [
        ("compound_shell_forbidden", "inspection"),
        ("invalid_command_role", "command"),
        ("repair_build_directory_drift", "repair_build"),
        ("artifact_stage_identity_drift", "artifact_stage"),
        ("inspection_budget_exhausted", "inspection"),
    ]

    with tempfile.TemporaryDirectory(prefix="forge-observability-r0-") as temporary:
        ledger = ExperimentLedger.create(
            Path(temporary) / "gate.jsonl",
            experiment_id=new_evidence_id("experiment"),
            physical_attempt_id=new_evidence_id("physical_attempt"),
            context={"scope": "opaque-provenance-rejection-observability-r0"},
        )
        activate_experiment(
            thread_id=thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_policy(),
        )
        try:
            response = SimpleNamespace(result=[SimpleNamespace(tool_calls=tool_calls)])
            registry = RejectionObservationRegistry()
            registered = registry.register_model_tool_calls(
                thread_id,
                response,
                model_request_id=model_request_id,
            )
            if registered != len(tool_calls):
                raise RuntimeError("tool-call origin registration was incomplete")
            adapter = ObservableRuntimeParityToolAdapter(run_tool=_FakeTool(), submit_tool=_FakeTool())
            for _ in range(parity.ACTION_LIMITS["inspection"]):
                adapter.run("pwd", command_role="other")
            for tool_call in tool_calls:
                registry.record_tool_failure(
                    _request(thread_id, tool_call),
                    _capture_rejection(adapter, tool_call),
                    execution_mode="sync",
                )
        finally:
            deactivate_experiment(thread_id)

        events = ledger.read()
        failures = [event["payload"] for event in events if event["event"] == "agent.tool_failed"]
        observations = [event["payload"] for event in events if event["event"] == OBSERVATION_EVENT]
        if len(failures) != len(expected) or any(set(payload) != _LEGACY_FAILURE_FIELDS for payload in failures):
            raise RuntimeError("historical agent.tool_failed schema drifted")
        if [item["failure_id"] for item in observations] != [item["failure_id"] for item in failures]:
            raise RuntimeError("companion observation linkage drifted")
        observed = [(payload["rejection_classification"], payload["action_kind"]) for payload in observations]
        if observed != expected:
            raise RuntimeError("bounded rejection classifications drifted")
        if [payload["tool_ordinal"] for payload in observations] != list(range(1, len(tool_calls) + 1)):
            raise RuntimeError("tool ordinals drifted")
        if any(payload["model_request_id"] != model_request_id for payload in observations):
            raise RuntimeError("model request correlation drifted")
        for payload, tool_call in zip(observations, tool_calls, strict=True):
            expected_sha256 = hashlib.sha256(tool_call["args"]["command"].encode("utf-8")).hexdigest()
            if payload["command_sha256"] != expected_sha256:
                raise RuntimeError("command digest drifted")
        persisted = ledger.path.read_text(encoding="utf-8")
        if any(tool_call["args"]["command"] in persisted for tool_call in tool_calls):
            raise RuntimeError("raw command leaked into observability evidence")

    return {
        "schema_version": SCHEMA_VERSION,
        "issue": 194,
        "observation_event": OBSERVATION_EVENT,
        "legacy_tool_failed_schema_preserved": True,
        "classifications": [
            {
                "rejection_classification": classification,
                "action_kind": action_kind,
                "tool_ordinal": ordinal,
            }
            for ordinal, (classification, action_kind) in enumerate(expected, start=1)
        ],
        "atomic_observability_fields": [
            "rejection_classification",
            "action_kind",
            "model_request_id",
            "tool_ordinal",
            "command_sha256",
        ],
        "raw_command_persisted": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "docker_executed": False,
        "credential_read": False,
        "frozen_evidence_modified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.parse_args(argv)
    print(json.dumps(validate_gate(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
