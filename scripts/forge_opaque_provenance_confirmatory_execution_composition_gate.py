#!/usr/bin/env python3
"""Issue #235 确认性 execution candidate 的零 provider 组合门禁。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_provenance_confirmatory_execution_candidate_protocol as protocol  # noqa: E402
import forge_opaque_provenance_confirmatory_lifecycle_gate as lifecycle  # noqa: E402
import forge_opaque_provenance_r3_make_agent_construction_gate as construction  # noqa: E402
import forge_opaque_provenance_r3_make_candidate_runner as make_runtime  # noqa: E402
import forge_opaque_provenance_r3_make_execution_failure_gate as failure_gate  # noqa: E402
import forge_opaque_provenance_rejection_observability_gate as cmake_observability  # noqa: E402
import forge_opaque_provenance_runtime_parity_gate as cmake_runtime  # noqa: E402


class ConfirmatoryCompositionGateError(RuntimeError):
    """Case dispatch、agent construction 或批次停止规则不闭合。"""


@dataclass(frozen=True)
class CaseDispatch:
    case_id: str
    build_system: str
    policy_family: str
    build_action: str
    stage_action: str
    action_policy: dict[str, Any]
    repair_packet: dict[str, str]


def _action_policy(adapter: Any) -> tuple[Any, Any, Any, str]:
    if adapter.build_system == "cmake":
        policy = cmake_runtime.FrozenActionPolicy(
            workdir=lifecycle.WORKDIR,
            build_directory=lifecycle.BUILD_DIRECTORY,
            target=adapter.target,
            build_output=adapter.stage_source,
            staged_artifact=adapter.stage_destination,
        )
        return cmake_runtime, cmake_observability, policy, "cmake_runtime_parity_v1"
    if adapter.build_system == "make":
        policy = make_runtime.R3ActionPolicy(
            workdir=lifecycle.WORKDIR,
            build_directory=lifecycle.WORKDIR,
            target=adapter.target,
            build_output=adapter.stage_source,
            staged_artifact=adapter.stage_destination,
            maximum_jobs=2,
        )
        parity, observability = failure_gate.build_runtime_bindings()
        return parity, observability, policy, "r3_make_runtime_parity_v1"
    raise ConfirmatoryCompositionGateError(f"未知构建系统: {adapter.build_system}")


def build_case_dispatch(case_id: str, repo_root: Path = REPO_ROOT) -> CaseDispatch:
    manifest = protocol.generate_manifest(repo_root)
    adapter = lifecycle.build_case_adapter(case_id, repo_root)
    parity, observability, policy, family = _action_policy(adapter)
    classifier = cmake_runtime.classify_action if adapter.build_system == "cmake" else make_runtime.classify_action
    build_action = classifier(adapter.treatment_build_command, workdir=lifecycle.WORKDIR, command_role="build", policy=policy)
    stage_action = classifier(adapter.treatment_stage_command, workdir=lifecycle.WORKDIR, command_role="artifact_stage", policy=policy)
    if build_action != "repair_build" or stage_action != "artifact_stage":
        raise ConfirmatoryCompositionGateError(f"{case_id} action dispatch 未闭合")
    required = ((parity, "SerialToolCallMiddleware"), (observability, "RejectionObservationRegistry"), (observability, "ObservableRuntimeParityToolAdapter"))
    if not all(hasattr(namespace, name) for namespace, name in required):
        raise ConfirmatoryCompositionGateError(f"{case_id} runtime binding 不完整")
    packet = manifest["execution_candidate"]["repair_packets"][case_id]
    case = next(item for item in manifest["cases"] if item["case_id"] == case_id)
    if packet != protocol.build_repair_packet(case):
        raise ConfirmatoryCompositionGateError(f"{case_id} repair packet 发生漂移")
    return CaseDispatch(case_id, adapter.build_system, family, build_action, stage_action, asdict(policy), packet)


def build_all_dispatches(repo_root: Path = REPO_ROOT) -> tuple[CaseDispatch, ...]:
    return tuple(build_case_dispatch(case_id, repo_root) for case_id in protocol.CASE_ORDER)


@contextmanager
def _construction_bindings(adapter: Any) -> Iterator[None]:
    original = construction.failure_gate.build_runtime_bindings
    parity, observability, policy, _family = _action_policy(adapter)

    def bindings() -> tuple[SimpleNamespace, SimpleNamespace]:
        return (
            SimpleNamespace(FrozenActionPolicy=lambda: policy, SerialToolCallMiddleware=parity.SerialToolCallMiddleware),
            SimpleNamespace(OBSERVATION_EVENT=observability.OBSERVATION_EVENT, RejectionObservationRegistry=observability.RejectionObservationRegistry, ObservableRuntimeParityToolAdapter=observability.ObservableRuntimeParityToolAdapter),
        )

    construction.failure_gate.build_runtime_bindings = bindings
    try:
        yield
    finally:
        construction.failure_gate.build_runtime_bindings = original


async def validate_agent_construction_dispatch(repo_root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    parent_manifest = construction.protocol.load_manifest()
    for adapter in lifecycle.build_case_adapters(repo_root):
        with _construction_bindings(adapter):
            result = await construction.validate_gate(parent_manifest)
        success = result["success_probe"]
        if success["model_calls"] != 1 or success["bound_tool_count"] != 2 or success["parallel_tool_calls"] is not False:
            raise ConfirmatoryCompositionGateError(f"{adapter.case_id} agent construction 未闭合")
        reports.append(
            {
                "case_id": adapter.case_id,
                "build_system": adapter.build_system,
                "model_calls": 1,
                "bound_tool_count": 2,
                "parallel_tool_calls": False,
                "provider_calls": 0,
                "model_tokens": 0,
                "active_experiment_released": success["active_experiment_released"],
            }
        )
    return reports


def next_batch_state(manifest: dict[str, Any], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    schedule = manifest["schedule"]["pairs"]
    if len(outcomes) > len(schedule):
        raise ConfirmatoryCompositionGateError("outcome 数量超过冻结 schedule")
    expected_ids = [pair["pair_id"] for pair in schedule[: len(outcomes)]]
    if [outcome.get("pair_id") for outcome in outcomes] != expected_ids:
        raise ConfirmatoryCompositionGateError("outcome 顺序偏离冻结 schedule")
    ceiling = manifest["runtime_contract"]["batch_recorded_token_ceiling"]
    recorded_tokens = 0
    for outcome in outcomes:
        tokens = outcome.get("recorded_tokens")
        terminal = outcome.get("terminal")
        if not isinstance(tokens, int) or tokens < 0:
            raise ConfirmatoryCompositionGateError("pair token evidence 无效")
        recorded_tokens += tokens
        if recorded_tokens > ceiling:
            raise ConfirmatoryCompositionGateError("batch recorded-token ceiling 已越界")
        if terminal in manifest["execution_candidate"]["terminal_taxonomy"]["stop_batch"]:
            return {"status": "stopped", "reason": terminal, "recorded_tokens": recorded_tokens, "next_pair_id": None}
        if terminal not in manifest["execution_candidate"]["terminal_taxonomy"]["continue"]:
            raise ConfirmatoryCompositionGateError("未知 pair terminal taxonomy")
    if len(outcomes) == len(schedule):
        return {"status": "completed", "reason": None, "recorded_tokens": recorded_tokens, "next_pair_id": None}
    if recorded_tokens >= ceiling:
        return {"status": "stopped", "reason": "token_ceiling_reached", "recorded_tokens": recorded_tokens, "next_pair_id": None}
    return {"status": "ready", "reason": None, "recorded_tokens": recorded_tokens, "next_pair_id": schedule[len(outcomes)]["pair_id"]}


async def validate_composition_gate(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest = protocol.generate_manifest(repo_root)
    protocol.validate_manifest(manifest, repo_root)
    dispatches = build_all_dispatches(repo_root)
    construction_reports = await validate_agent_construction_dispatch(repo_root)
    pairs = manifest["schedule"]["pairs"]
    endpoint_probe = next_batch_state(manifest, [{"pair_id": pairs[0]["pair_id"], "terminal": "endpoint_censored", "recorded_tokens": 0}])
    if endpoint_probe["status"] != "ready" or endpoint_probe["next_pair_id"] != pairs[1]["pair_id"]:
        raise ConfirmatoryCompositionGateError("endpoint censoring 未继续下一 pair")
    return {
        "status": "passed",
        "issue_url": protocol.ISSUE_URL,
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "schedule_identity_sha256": manifest["schedule"]["identity_sha256"],
        "dispatches": [asdict(item) for item in dispatches],
        "agent_construction": construction_reports,
        "endpoint_censoring_continues": True,
        "real_pair_runner_implemented": False,
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "checkpoint_created": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "formal_evidence_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.parse_args(argv)
    print(json.dumps(asyncio.run(validate_composition_gate()), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
