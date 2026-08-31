#!/usr/bin/env python3
"""执行 Issue #237 授权的六 case opaque provenance 确认性 pilot。"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import shlex
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from itertools import product
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_checkpoint_behavioral_pilot_v2_runner as batch_runtime  # noqa: E402
import forge_opaque_provenance_confirmatory_execution_authorized_protocol as protocol  # noqa: E402
import forge_opaque_provenance_confirmatory_execution_composition_gate as composition  # noqa: E402
import forge_opaque_provenance_confirmatory_lifecycle_gate as lifecycle  # noqa: E402
import forge_opaque_provenance_minimal_canary_execution_runner as cmake_pair_runtime  # noqa: E402
import forge_opaque_provenance_r1_execution_runner as agent_runtime  # noqa: E402
import forge_opaque_provenance_r3_make_execution_failure_gate as make_bindings  # noqa: E402
import forge_opaque_provenance_r3_make_execution_runner as make_pair_runtime  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path(protocol.EVIDENCE_DIRECTORY)
COMPILE_IMAGE = lifecycle.COMPILE_IMAGE
ARMS = ("baseline", "treatment")

primary = cmake_pair_runtime.primary
evidence_runtime = cmake_pair_runtime.v3_runner


class ConfirmatoryExecutionError(RuntimeError):
    """确认性执行的 identity、evidence、预算、P2 或 cleanup 无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfirmatoryExecutionError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ConfirmatoryExecutionError(f"JSON 根节点必须是对象: {path}")
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _write_once(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError as exc:
        raise ConfirmatoryExecutionError(f"不可覆盖已存在的 evidence: {path}") from exc


def _git(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo_root}", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ConfirmatoryExecutionError("无法验证授权 release Git identity")
    return result.stdout.strip()


def _execution(manifest: dict[str, Any]) -> dict[str, Any]:
    return manifest["authorized_execution"]


def _output_dir(manifest: dict[str, Any], output_dir: Path) -> Path:
    expected = Path(_execution(manifest)["evidence"]["directory"]).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise ConfirmatoryExecutionError("evidence 必须写入 Issue #237 冻结目录")
    return output_dir


def require_release_identity(
    manifest: dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    branch = _git(repo_root, "branch", "--show-current")
    revision = _git(repo_root, "rev-parse", "HEAD")
    origin_main = _git(repo_root, "rev-parse", "origin/main")
    dirty = _git(repo_root, "status", "--porcelain", "--untracked-files=normal")
    execution = _execution(manifest)
    if branch != execution["preflight"]["release_branch"]:
        raise ConfirmatoryExecutionError("真实执行只能位于 main")
    if revision != origin_main or dirty:
        raise ConfirmatoryExecutionError("真实执行要求干净且 main == origin/main")
    baseline = execution["authorization_baseline_commit"]
    if _git(repo_root, "merge-base", baseline, revision) != baseline:
        raise ConfirmatoryExecutionError("release 不是 Issue #237 授权基线的后代")
    return {"branch": branch, "revision": revision, "origin_main": origin_main}


def require_network_medium(manifest: dict[str, Any]) -> str:
    preflight = _execution(manifest)["preflight"]
    medium = os.environ.get(preflight["network_access_medium_env"])
    if medium not in preflight["allowed_network_media"]:
        raise ConfirmatoryExecutionError("必须通过 FORGE_NETWORK_ACCESS_MEDIUM 记录当前网络介质")
    return medium


def require_zero_managed_containers() -> None:
    try:
        evidence_runtime.require_zero_managed_containers()
    except evidence_runtime.AuthorizedPilotError as exc:
        raise ConfirmatoryExecutionError(str(exc)) from exc


def _provider_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {"provider": copy.deepcopy(_execution(manifest)["provider"])}


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _output_dir(manifest, output_dir)
    release = require_release_identity(manifest, repo_root)
    medium = require_network_medium(manifest)
    primary.require_compose_dood()
    require_zero_managed_containers()
    try:
        evidence_runtime._provider_config_preflight(_provider_manifest(manifest))
    except evidence_runtime.AuthorizedPilotError as exc:
        raise ConfirmatoryExecutionError(str(exc)) from exc
    entries = sorted(str(path.relative_to(output_dir)).replace("\\", "/") for path in output_dir.rglob("*") if path.is_file()) if output_dir.exists() else []
    if require_empty and entries:
        raise ConfirmatoryExecutionError("reachability 前要求授权 evidence 目录为空")
    return {
        "ready": True,
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release["revision"],
        "network_access_medium": medium,
        "credential_check": "environment_variable_presence_only",
        "credential_env": _execution(manifest)["provider"]["credential_env"],
        "evidence_files": entries,
        "zero_managed_containers": True,
        "docker_provider": _execution(manifest)["preflight"]["docker_provider"],
        "docker_endpoint": _execution(manifest)["preflight"]["docker_endpoint"],
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def _runtime_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    execution = _execution(manifest)
    evidence = execution["evidence"]
    return {
        "provider": copy.deepcopy(execution["provider"]),
        "budget": {"reachability_maximum_recorded_tokens": execution["budget"]["reachability_maximum_recorded_tokens"]},
        "evidence": {
            "directory": evidence["directory"],
            "reachability_marker": evidence["reachability_marker"],
        },
        "execution": {
            "release_branch": execution["preflight"]["release_branch"],
            "network_access_medium_env": execution["preflight"]["network_access_medium_env"],
            "reachability_prompt": execution["execution"]["reachability_prompt"],
            "reachability_expected_response": execution["execution"]["reachability_expected_response"],
            "reachability_report": evidence["reachability_report"],
        },
        "parent": {"authorization_baseline_commit": execution["authorization_baseline_commit"]},
        "preflight": copy.deepcopy(execution["preflight"]),
    }


@contextmanager
def _reachability_bindings(
    manifest: dict[str, Any],
    runtime_manifest: dict[str, Any],
    output_dir: Path,
    repo_root: Path,
) -> Iterator[None]:
    original_protocol = cmake_pair_runtime.protocol
    original_collect = cmake_pair_runtime.collect_preflight
    digest = protocol.canonical_sha256(manifest)
    cmake_pair_runtime.protocol = SimpleNamespace(canonical_sha256=lambda _value: digest)
    cmake_pair_runtime.collect_preflight = lambda *_args, **_kwargs: collect_preflight(
        manifest,
        output_dir=output_dir,
        repo_root=repo_root,
        require_empty=True,
    )
    try:
        yield
    finally:
        cmake_pair_runtime.protocol = original_protocol
        cmake_pair_runtime.collect_preflight = original_collect


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    runtime_manifest = _runtime_manifest(manifest)
    with _reachability_bindings(manifest, runtime_manifest, output_dir, repo_root):
        return cmake_pair_runtime.execute_reachability(
            runtime_manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            model_factory=model_factory,
        )


def require_passed_reachability(
    manifest: dict[str, Any],
    output_dir: Path,
    revision: str,
) -> dict[str, Any]:
    execution = _execution(manifest)
    evidence = execution["evidence"]
    marker = _load_json(output_dir / evidence["reachability_marker"])
    report = _load_json(output_dir / evidence["reachability_report"])
    digest = protocol.canonical_sha256(manifest)
    if (
        marker.get("status") != "passed"
        or marker.get("manifest_sha256") != digest
        or marker.get("release_revision") != revision
        or report.get("passed") is not True
        or report.get("manifest_sha256") != digest
        or report.get("release_revision") != revision
        or type(report.get("recorded_tokens")) is not int
        or report["recorded_tokens"] > execution["budget"]["reachability_maximum_recorded_tokens"]
    ):
        raise ConfirmatoryExecutionError("唯一 reachability 未形成同 revision 通过终态")
    return report


def _case(manifest: dict[str, Any], case_id: str) -> dict[str, Any]:
    matches = [item for item in manifest["cases"] if item["case_id"] == case_id]
    if len(matches) != 1:
        raise ConfirmatoryExecutionError(f"未知或重复 case: {case_id}")
    return matches[0]


def _pair_manifest(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_dir: Path,
) -> dict[str, Any]:
    case = _case(manifest, pair["case_id"])
    adapter = lifecycle.build_case_adapter(pair["case_id"], REPO_ROOT)
    execution = _execution(manifest)
    evidence = execution["evidence"]
    runtime = manifest["runtime_contract"]
    digest = protocol.canonical_sha256(manifest)
    return {
        "schema_version": "forge-opaque-provenance-confirmatory-pair-runtime-1.0.0",
        "document_type": "forge_opaque_provenance_confirmatory_pair_runtime",
        "parent_manifest_sha256": digest,
        "case": {
            "case_id": case["case_id"],
            "repository_url": case["repository_url"],
            "commit_sha": case["commit_sha"],
            "build_system": case["build_system"],
            "compile_image": COMPILE_IMAGE,
            "source_subdir": ".",
            "target": case["direct_target"],
            "staged_artifact": case["artifact"]["staged_relative_path"],
            "build_output": case["artifact"]["build_output_path"],
            "artifact_type": case["artifact"]["artifact_type"],
        },
        "provider": copy.deepcopy(execution["provider"]),
        "continuation": {
            "arm_order": copy.deepcopy(pair["arm_order"]),
            "maximum_requests_per_arm": runtime["request_limit_per_arm"],
            "maximum_model_turns_per_arm": runtime["turn_limit_per_arm"],
            "maximum_graph_steps_per_arm": runtime["graph_step_limit_per_arm"],
            "work_wall_clock_seconds_per_arm": runtime["work_timeout_seconds_per_arm"],
            "cleanup_reserve_seconds_per_arm": runtime["cleanup_timeout_seconds_per_arm"],
            "maximum_recorded_tokens_per_arm": runtime["per_arm_recorded_token_ceiling"],
        },
        "schedule": [copy.deepcopy(pair)],
        "budget": {
            "reachability_maximum_recorded_tokens": execution["budget"]["reachability_maximum_recorded_tokens"],
            "stage_maximum_recorded_tokens": execution["budget"]["recorded_tokens_per_pair"] + execution["budget"]["reachability_maximum_recorded_tokens"],
        },
        "evidence": {
            "directory": str(pair_dir),
            "identity_sha256": protocol.canonical_sha256(
                {
                    "batch_evidence_identity": evidence["identity_sha256"],
                    "pair": pair,
                }
            ),
            "reachability_marker": evidence["reachability_marker"],
            "pair_marker": evidence["pair_marker"],
            "canary_report": evidence["pair_report"],
        },
        "execution": {
            "release_branch": execution["preflight"]["release_branch"],
            "network_access_medium_env": execution["preflight"]["network_access_medium_env"],
            "pair_marker": evidence["pair_marker"],
            "parent_ledger": evidence["parent_ledger"],
            "arm_ledger_directory": evidence["arm_ledger_directory"],
            "report_schema_version": "forge-opaque-provenance-confirmatory-pair-report-1.0.0",
            "report_document_type": "forge_opaque_provenance_confirmatory_pair_report",
        },
        "parent": {"authorization_baseline_commit": execution["authorization_baseline_commit"]},
        "preflight": copy.deepcopy(execution["preflight"]),
        "repair_packet": copy.deepcopy(manifest["execution_candidate"]["repair_packets"][pair["case_id"]]),
        "runtime_parity": {
            "parallel_tool_calls": False,
            "action_limits": copy.deepcopy(runtime["action_limits"]),
            "policy_family": composition.build_case_dispatch(pair["case_id"], REPO_ROOT).policy_family,
            "action_surface": {
                "workdir": lifecycle.WORKDIR,
                "build_directory": (lifecycle.BUILD_DIRECTORY if adapter.build_system == "cmake" else lifecycle.WORKDIR),
                "target": adapter.target,
                "build_output": adapter.stage_source,
                "staged_artifact": adapter.stage_destination,
            },
        },
        "r0_observability": {"required": True},
    }


def _policy(
    manifest: dict[str, Any],
    adapter: lifecycle.LifecycleCaseAdapter,
    *,
    arm: str,
    image_id: str,
) -> Any:
    continuation = manifest["continuation"]
    provider = manifest["provider"]
    return primary.ExperimentPolicy(
        benchmark_id="forge-opaque-provenance-confirmatory",
        manifest_sha256=protocol.canonical_sha256(manifest),
        case_id=adapter.case_id,
        condition=arm,
        repetition=manifest["schedule"][0]["replicate"],
        expected_repo_url=adapter.repository_url,
        expected_commit_sha=adapter.commit_sha,
        expected_build_system=adapter.build_system,
        compile_image=COMPILE_IMAGE,
        image_id=image_id,
        model_name=provider["model"],
        endpoint=provider["endpoint"],
        credential_env=provider["credential_env"],
        request_timeout_seconds=provider["request_timeout_seconds"],
        model_max_retries=provider["max_retries"],
        compiler_max_turns=continuation["maximum_model_turns_per_arm"],
        subagent_timeout_seconds=continuation["work_wall_clock_seconds_per_arm"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        bootstrap_commands=adapter.bootstrap_commands,
        compiler_model_turn_limit=continuation["maximum_model_turns_per_arm"],
        compiler_graph_recursion_limit=continuation["maximum_graph_steps_per_arm"],
        compiler_wall_clock_seconds=continuation["work_wall_clock_seconds_per_arm"],
        compiler_post_build_reserve_seconds=continuation["cleanup_reserve_seconds_per_arm"],
        source_subdir=".",
        build_targets=(adapter.target,),
        artifact_instructions=(
            (
                adapter.staged_artifact,
                adapter.build_output,
                adapter.artifact_type,
            ),
        ),
    )


def _parent_policy(
    manifest: dict[str, Any],
    adapter: lifecycle.LifecycleCaseAdapter,
    *,
    image_id: str,
) -> Any:
    return replace(
        _policy(manifest, adapter, arm="controlled-parent", image_id=image_id),
        model_name="deterministic-no-provider",
        endpoint="https://example.invalid/v1",
        credential_env="UNUSED_PROVIDER_KEY",
        request_timeout_seconds=1,
        compiler_max_turns=1,
    )


def _case_proxy(
    pair_manifest: dict[str, Any],
    adapter: lifecycle.LifecycleCaseAdapter,
) -> Any:
    provenance = lifecycle.cmake_reference if adapter.build_system == "cmake" else lifecycle.make_reference

    def build_frozen_identity(**kwargs: Any) -> Any:
        return lifecycle.build_frozen_identity(adapter, **kwargs)

    def evaluate_parent(
        frozen: Any,
        *,
        parent_command_id: str,
    ) -> tuple[Any, tuple[Any, ...]]:
        return lifecycle.evaluate_parent(
            adapter,
            frozen,
            parent_command_id=parent_command_id,
        )

    return SimpleNamespace(
        CASE_ID=adapter.case_id,
        REPOSITORY_URL=adapter.repository_url,
        COMMIT_SHA=adapter.commit_sha,
        WORKDIR=lifecycle.WORKDIR,
        COMPILE_IMAGE=COMPILE_IMAGE,
        PARENT_COMMAND=adapter.parent_command,
        BUILD_OUTPUT=adapter.build_output,
        TARGET=adapter.target,
        STAGED_ARTIFACT=adapter.staged_artifact,
        provenance=provenance,
        build_frozen_identity=build_frozen_identity,
        evaluate_parent=evaluate_parent,
        build_repair_packet=lambda: copy.deepcopy(pair_manifest["repair_packet"]),
    )


def _command_tokens(command: str) -> tuple[str, tuple[str, ...]]:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ConfirmatoryExecutionError("trusted command 无法规范化") from exc
    if not tokens:
        raise ConfirmatoryExecutionError("trusted command 为空")
    return PurePosixPath(tokens[0]).name, tuple(tokens[1:])


def _evaluate_arm_p2(
    adapter: lifecycle.LifecycleCaseAdapter,
    session: Any,
    frozen: Any,
    parent_command_id: str,
) -> tuple[Any, tuple[Any, ...]]:
    artifact = Path(session.leadagent_repo_dir) / adapter.build_output
    if not artifact.is_file():
        raise ConfirmatoryExecutionError("arm 丢失冻结 workspace artifact")
    if artifact.stat().st_size != frozen.artifact_size or primary.lifecycle.sha256_file(artifact) != frozen.artifact_sha256:
        raise ConfirmatoryExecutionError("arm workspace artifact identity 漂移")
    if adapter.build_tree_relative_path is not None:
        tree = Path(session.leadagent_repo_dir) / adapter.build_tree_relative_path
        if not tree.is_file() or primary.lifecycle.sha256_file(tree) != frozen.build_tree_sha256:
            raise ConfirmatoryExecutionError("arm CMake build tree identity 漂移")

    parent = lifecycle._parent_invocation(adapter, frozen, parent_command_id)
    invocations = [parent]
    previous_hash = parent.ledger_hash
    producer_id = session.post_build_supporting_command_id or parent_command_id
    seen_parent = False
    for record in session.commands:
        if record.command_id == parent_command_id:
            seen_parent = True
            continue
        if not seen_parent or record.stage != "bash":
            continue
        executable, argv = _command_tokens(record.command)
        output_paths = (adapter.build_output,) if record.command_id == producer_id else ()
        invocation = lifecycle.cmake_reference.record_invocation(
            command_id=record.command_id,
            physical_attempt_id=frozen.physical_attempt_id,
            sequence=len(invocations) + 1,
            repository_url=frozen.repository_url,
            commit_sha=frozen.commit_sha,
            image_id=frozen.image_id,
            executable=executable,
            argv=argv,
            workdir=record.workdir or lifecycle.WORKDIR,
            previous_hash=previous_hash,
            exit_code=record.exit_code if record.exit_code is not None else 1,
            timed_out=record.timed_out,
            output_paths=output_paths,
            model_declared_role=record.role,
        )
        invocations.append(invocation)
        previous_hash = invocation.ledger_hash
    if producer_id not in {item.command_id for item in invocations}:
        producer_id = parent_command_id
    identity = lifecycle._artifact(
        frozen,
        producer_id,
        observed_after_sequence=len(invocations) + 1,
    )
    if adapter.build_system == "cmake":
        decision = lifecycle.cmake_reference.evaluate_p2(
            frozen,
            tuple(invocations),
            identity,
        )
    else:
        decision = lifecycle.make_reference.evaluate_make_p2(
            frozen,
            tuple(invocations),
            identity,
        )
    return decision, tuple(invocations)


async def _run_arm_continuation(
    pair_manifest: dict[str, Any],
    adapter: lifecycle.LifecycleCaseAdapter,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    original = {
        "policy": agent_runtime._policy,
        "parity": agent_runtime.parity,
        "checkpoint": agent_runtime.checkpoint_gate,
        "observability": agent_runtime.observability,
    }
    if adapter.build_system == "cmake":
        parity = composition.cmake_runtime
        observability = composition.cmake_observability
    else:
        parity, observability = make_bindings.build_runtime_bindings()
    agent_runtime._policy = lambda _value, *, arm, image_id: _policy(
        pair_manifest,
        adapter,
        arm=arm,
        image_id=image_id,
    )
    agent_runtime.parity = parity
    agent_runtime.checkpoint_gate = SimpleNamespace(
        WORKDIR=lifecycle.WORKDIR,
        BUILD_DIRECTORY=(lifecycle.BUILD_DIRECTORY if adapter.build_system == "cmake" else lifecycle.WORKDIR),
        TARGET=adapter.target,
        BUILD_OUTPUT=adapter.build_output,
        STAGED_ARTIFACT=adapter.staged_artifact,
    )
    agent_runtime.observability = observability
    try:
        return await agent_runtime.run_arm_continuation(
            pair_manifest,
            *args,
            **kwargs,
            budget_sink={},
        )
    finally:
        agent_runtime._policy = original["policy"]
        agent_runtime.parity = original["parity"]
        agent_runtime.checkpoint_gate = original["checkpoint"]
        agent_runtime.observability = original["observability"]


class _SharedRunnerContext:
    def __init__(self, runner: asyncio.Runner):
        self.runner = runner

    def __enter__(self) -> asyncio.Runner:
        return self.runner

    def __exit__(self, *_args: Any) -> None:
        return None


class _AsyncioProxy:
    def __init__(self, runner: asyncio.Runner):
        self.runner = runner

    def Runner(self) -> _SharedRunnerContext:  # noqa: N802
        return _SharedRunnerContext(self.runner)

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)


@contextmanager
def _pair_bindings(
    manifest: dict[str, Any],
    pair_manifest: dict[str, Any],
    adapter: lifecycle.LifecycleCaseAdapter,
    output_dir: Path,
    release: dict[str, str],
    reachability: dict[str, Any],
    async_runner: asyncio.Runner,
) -> Iterator[Any]:
    from deerflow.compile import operations
    from deerflow.tools import bound_compile_tools

    base = cmake_pair_runtime if adapter.build_system == "cmake" else make_pair_runtime
    case_proxy = _case_proxy(pair_manifest, adapter)
    digest = protocol.canonical_sha256(pair_manifest)
    protocol_proxy = SimpleNamespace(canonical_sha256=lambda _value: digest)
    originals = {
        "protocol": base.protocol,
        "collect_preflight": base.collect_preflight,
        "policy": base._policy,
        "parent_policy": base._parent_policy,
        "evaluate": base._evaluate_arm_p2,
        "continuation": getattr(base, "run_arm_continuation", None),
        "asyncio": base.asyncio,
        "passed_reachability": base.legacy._passed_reachability if adapter.build_system == "make" else base._passed_reachability,
        "primary_continuation": primary.run_arm_continuation,
        "submit_impl": operations.submit_build_result_impl,
    }
    if adapter.build_system == "cmake":
        originals["case_proxy"] = base.opaque
    else:
        originals["case_proxy"] = base.make_lifecycle

    def local_preflight(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "ready": True,
            "release_revision": release["revision"],
            "network_access_medium": require_network_medium(manifest),
            "provider_calls": 0,
            "formal_attempts": 0,
            "model_tokens": 0,
        }

    def continuation(_runtime_manifest: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        return _run_arm_continuation(pair_manifest, adapter, *args, **kwargs)

    def parent_submit(
        *,
        session: Any,
        supporting_command_id: str | None = None,
    ) -> str:
        return bound_compile_tools._submit_with_post_build_phase(
            session,
            supporting_command_id=supporting_command_id,
        )

    base.protocol = protocol_proxy
    base.collect_preflight = local_preflight
    base._policy = lambda _value, *, arm, image_id: _policy(
        pair_manifest,
        adapter,
        arm=arm,
        image_id=image_id,
    )
    base._parent_policy = lambda _value, *, image_id: _parent_policy(
        pair_manifest,
        adapter,
        image_id=image_id,
    )
    base._evaluate_arm_p2 = lambda session, frozen, parent_id: _evaluate_arm_p2(
        adapter,
        session,
        frozen,
        parent_id,
    )
    if adapter.build_system == "make":
        base.run_arm_continuation = continuation
    base.asyncio = _AsyncioProxy(async_runner)
    primary.run_arm_continuation = continuation
    operations.submit_build_result_impl = parent_submit
    if adapter.build_system == "cmake":
        base.opaque = case_proxy
        base._passed_reachability = lambda *_args, **_kwargs: reachability
    else:
        base.make_lifecycle = case_proxy
        base.legacy._passed_reachability = lambda *_args, **_kwargs: reachability
    try:
        yield base
    finally:
        base.protocol = originals["protocol"]
        base.collect_preflight = originals["collect_preflight"]
        base._policy = originals["policy"]
        base._parent_policy = originals["parent_policy"]
        base._evaluate_arm_p2 = originals["evaluate"]
        if adapter.build_system == "make":
            base.run_arm_continuation = originals["continuation"]
        base.asyncio = originals["asyncio"]
        primary.run_arm_continuation = originals["primary_continuation"]
        operations.submit_build_result_impl = originals["submit_impl"]
        if adapter.build_system == "cmake":
            base.opaque = originals["case_proxy"]
            base._passed_reachability = originals["passed_reachability"]
        else:
            base.make_lifecycle = originals["case_proxy"]
            base.legacy._passed_reachability = originals["passed_reachability"]


def _pair_terminal(arms: Sequence[dict[str, Any]]) -> str:
    if any(arm.get("infrastructure", {}).get("status") == "endpoint_censored" for arm in arms):
        return "endpoint_censored"
    if any(arm.get("model_behavior", {}).get("status") != "completed" for arm in arms):
        return "model_behavior_outcome"
    return "valid"


def _pair_outcome(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_manifest: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    arms = report.get("arms")
    if report.get("complete_pair") is not True or report.get("cleanup_succeeded") is not True or report.get("arm_order") != pair["arm_order"] or not isinstance(arms, list) or {item.get("arm") for item in arms} != set(ARMS):
        raise ConfirmatoryExecutionError("pair 未形成双臂与 cleanup 终态")
    arm_map = {item["arm"]: item for item in arms}
    eligible = all(item.get("infrastructure", {}).get("status") == "valid" for item in arm_map.values())
    conversion = {arm: item.get("p2", {}).get("status") == "proven" for arm, item in arm_map.items()}
    tokens = sum(item.get("recorded_tokens", 0) for item in arm_map.values())
    if any(type(item.get("recorded_tokens")) is not int for item in arm_map.values()) or tokens > _execution(manifest)["budget"]["recorded_tokens_per_pair"]:
        raise ConfirmatoryExecutionError("pair recorded-token evidence 无效")
    return {
        "schema_version": "forge-opaque-provenance-confirmatory-pair-outcome-1.0.0",
        "document_type": "forge_opaque_provenance_confirmatory_pair_outcome",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "pair_manifest_sha256": protocol.canonical_sha256(pair_manifest),
        "pair_id": pair["pair_id"],
        "case_id": pair["case_id"],
        "replicate": pair["replicate"],
        "arm_order": copy.deepcopy(pair["arm_order"]),
        "terminal": _pair_terminal(arms),
        "arms": arm_map,
        "recorded_tokens": tokens,
        "primary_mechanism_eligible": eligible,
        "provenance_conversion": conversion,
        "paired_conversion_delta": (int(conversion["treatment"]) - int(conversion["baseline"]) if eligible else None),
        "cleanup_succeeded": True,
        "completed_at": datetime.now(UTC).isoformat(),
    }


def execute_real_pair(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_dir: Path,
    async_runner: asyncio.Runner,
    reachability: dict[str, Any],
    release: dict[str, str],
    model_factory: Callable[[dict[str, Any], str], Any] | None = None,
) -> dict[str, Any]:
    adapter = lifecycle.build_case_adapter(pair["case_id"], REPO_ROOT)
    pair_manifest = _pair_manifest(manifest, pair, pair_dir)
    with _pair_bindings(
        manifest,
        pair_manifest,
        adapter,
        pair_dir,
        release,
        reachability,
        async_runner,
    ) as base:
        report = base._run_pair(
            pair_manifest,
            output_dir=pair_dir,
            repo_root=REPO_ROOT,
            model_factory=model_factory,
        )
    return _pair_outcome(manifest, pair, pair_manifest, report)


def next_batch_state(
    manifest: dict[str, Any],
    outcomes: list[dict[str, Any]],
    *,
    reachability_tokens: int = 0,
) -> dict[str, Any]:
    schedule = manifest["schedule"]["pairs"]
    if len(outcomes) > len(schedule):
        raise ConfirmatoryExecutionError("outcome 数量超过冻结 schedule")
    if [item.get("pair_id") for item in outcomes] != [item["pair_id"] for item in schedule[: len(outcomes)]]:
        raise ConfirmatoryExecutionError("outcome 顺序偏离冻结 schedule")
    execution = _execution(manifest)
    if type(reachability_tokens) is not int or reachability_tokens < 0:
        raise ConfirmatoryExecutionError("reachability token evidence 无效")
    recorded_tokens = 0
    for outcome in outcomes:
        tokens = outcome.get("recorded_tokens")
        if type(tokens) is not int or tokens < 0:
            raise ConfirmatoryExecutionError("pair token evidence 无效")
        recorded_tokens += tokens
        terminal = outcome.get("terminal")
        if terminal in execution["terminal_taxonomy"]["stop_batch"]:
            return {
                "status": "stopped",
                "reason": terminal,
                "recorded_tokens": recorded_tokens,
                "next_pair_id": None,
            }
        if terminal not in execution["terminal_taxonomy"]["continue"]:
            raise ConfirmatoryExecutionError("未知 pair terminal taxonomy")
    ceiling = execution["budget"]["batch_maximum_recorded_tokens"]
    if recorded_tokens + reachability_tokens > ceiling:
        raise ConfirmatoryExecutionError("batch recorded-token ceiling 已越界")
    if len(outcomes) == len(schedule):
        return {
            "status": "completed",
            "reason": None,
            "recorded_tokens": recorded_tokens,
            "next_pair_id": None,
        }
    if recorded_tokens + execution["budget"]["recorded_tokens_per_pair"] > ceiling:
        return {
            "status": "stopped",
            "reason": "token_ceiling_reached",
            "recorded_tokens": recorded_tokens,
            "next_pair_id": None,
        }
    return {
        "status": "ready",
        "reason": None,
        "recorded_tokens": recorded_tokens,
        "next_pair_id": schedule[len(outcomes)]["pair_id"],
    }


def _exact_sign_flip(project_scores: list[float]) -> dict[str, Any]:
    observed = abs(sum(project_scores))
    statistics = [abs(sum(sign * score for sign, score in zip(signs, project_scores))) for signs in product((-1, 1), repeat=len(project_scores))]
    extreme = sum(value >= observed - 1e-12 for value in statistics)
    return {
        "method": "two_sided_exact_sign_flip",
        "statistic": sum(project_scores),
        "permutations": len(statistics),
        "p_value": extreme / len(statistics),
    }


def summarize(
    manifest: dict[str, Any],
    release: dict[str, str],
    reachability: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome["case_id"]].append(outcome)
    project_blocks: list[dict[str, Any]] = []
    for case_id in [item["case_id"] for item in manifest["cases"]]:
        case_outcomes = grouped[case_id]
        estimable = len(case_outcomes) == 2 and all(item["primary_mechanism_eligible"] for item in case_outcomes)
        deltas = [item["paired_conversion_delta"] for item in case_outcomes] if estimable else []
        project_blocks.append(
            {
                "case_id": case_id,
                "pair_ids": [item["pair_id"] for item in case_outcomes],
                "estimable": estimable,
                "replicate_deltas": deltas,
                "project_score": sum(deltas) / 2 if estimable else None,
            }
        )
    all_estimable = all(item["estimable"] for item in project_blocks)
    project_scores = [item["project_score"] for item in project_blocks]
    primary_test = _exact_sign_flip(project_scores) if all_estimable else None
    pair_tokens = sum(item["recorded_tokens"] for item in outcomes)
    total_tokens = reachability["recorded_tokens"] + pair_tokens
    ceiling = _execution(manifest)["budget"]["batch_maximum_recorded_tokens"]
    if total_tokens > ceiling:
        raise ConfirmatoryExecutionError("pilot 超过授权 batch token ceiling")
    return {
        "schema_version": "forge-opaque-provenance-confirmatory-batch-report-1.0.0",
        "document_type": "forge_opaque_provenance_confirmatory_batch_report",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "evidence_identity_sha256": _execution(manifest)["evidence"]["identity_sha256"],
        "release_revision": release["revision"],
        "network_access_medium": require_network_medium(manifest),
        "status": "completed" if all_estimable else "completed_with_attrition",
        "scheduled_pairs": manifest["schedule"]["pair_count"],
        "observed_pairs": len(outcomes),
        "endpoint_censored_pair_ids": [item["pair_id"] for item in outcomes if item["terminal"] == "endpoint_censored"],
        "project_blocks": project_blocks,
        "all_project_blocks_estimable": all_estimable,
        "primary_test": primary_test,
        "reachability_recorded_tokens": reachability["recorded_tokens"],
        "pair_recorded_tokens": pair_tokens,
        "recorded_tokens": total_tokens,
        "maximum_recorded_tokens": ceiling,
        "historical_exploratory_pairs_pooled": False,
        "model_ranking_performed": False,
        "pairs": outcomes,
        "completed_at": datetime.now(UTC).isoformat(),
    }


PairExecutor = Callable[
    [
        dict[str, Any],
        dict[str, Any],
        Path,
        asyncio.Runner,
        dict[str, Any],
        dict[str, str],
    ],
    dict[str, Any],
]


def run_batch(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    pair_executor: PairExecutor | None = None,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _output_dir(manifest, output_dir)
    release = require_release_identity(manifest, repo_root)
    require_network_medium(manifest)
    primary.require_compose_dood()
    require_zero_managed_containers()
    reachability = require_passed_reachability(
        manifest,
        output_dir,
        release["revision"],
    )
    digest = protocol.canonical_sha256(manifest)
    evidence = _execution(manifest)["evidence"]
    marker_path = output_dir / evidence["batch_marker"]
    marker = batch_runtime._claim_batch_marker(
        marker_path,
        digest,
        release["revision"],
    )
    report_path = output_dir / evidence["batch_report"]
    if marker["status"] == "passed":
        report = _load_json(report_path)
        if report.get("manifest_sha256") != digest:
            raise ConfirmatoryExecutionError("已有 batch report identity 漂移")
        return report

    outcomes: list[dict[str, Any]] = []
    try:
        with asyncio.Runner() as async_runner:
            for pair in manifest["schedule"]["pairs"]:
                pair_dir = output_dir / "pairs" / pair["pair_id"]
                outcome_path = pair_dir / evidence["pair_outcome"]
                if outcome_path.exists():
                    outcome = _load_json(outcome_path)
                    if outcome.get("manifest_sha256") != digest or outcome.get("pair_id") != pair["pair_id"]:
                        raise ConfirmatoryExecutionError("已有 pair outcome identity 漂移")
                else:
                    if pair_dir.exists() and any(pair_dir.iterdir()):
                        raise ConfirmatoryExecutionError(f"pair 已开始但没有冻结 outcome，禁止自动补跑: {pair['pair_id']}")
                    state = next_batch_state(
                        manifest,
                        outcomes,
                        reachability_tokens=reachability["recorded_tokens"],
                    )
                    if state["status"] != "ready" or state["next_pair_id"] != pair["pair_id"]:
                        raise ConfirmatoryExecutionError(f"batch 已停止，禁止启动 {pair['pair_id']}: {state['reason']}")
                    require_zero_managed_containers()
                    executor = pair_executor or execute_real_pair
                    outcome = executor(
                        manifest,
                        pair,
                        pair_dir,
                        async_runner,
                        reachability,
                        release,
                    )
                    _write_once(outcome_path, outcome)
                outcomes.append(outcome)
                require_zero_managed_containers()
        if len(outcomes) != manifest["schedule"]["pair_count"]:
            raise ConfirmatoryExecutionError("未形成全部 12 个预注册 pair 终态")
        report = summarize(manifest, release, reachability, outcomes)
        _write_once(report_path, report)
        marker.update(
            status="passed",
            error_class=None,
            updated_at=datetime.now(UTC).isoformat(),
        )
        _atomic_write(marker_path, marker)
        return report
    except BaseException as exc:
        marker.update(
            status="failed",
            error_class=type(exc).__name__,
            updated_at=datetime.now(UTC).isoformat(),
        )
        _atomic_write(marker_path, marker)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate", "preflight", "reachability", "batch", "report"),
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        protocol.verify_frozen_components(manifest)
        result: Any = {
            "status": "valid",
            "manifest_sha256": protocol.canonical_sha256(manifest),
            "provider_calls": 0,
            "formal_attempts": 0,
            "model_tokens": 0,
        }
    elif args.command == "preflight":
        result = collect_preflight(
            manifest,
            output_dir=args.output_dir,
            require_empty=True,
        )
    elif args.command == "reachability":
        result = execute_reachability(manifest, output_dir=args.output_dir)
    elif args.command == "batch":
        result = run_batch(manifest, output_dir=args.output_dir)
    else:
        result = _load_json(args.output_dir / _execution(manifest)["evidence"]["batch_report"])
        if result.get("manifest_sha256") != protocol.canonical_sha256(manifest):
            raise ConfirmatoryExecutionError("batch report identity 漂移")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
