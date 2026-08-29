#!/usr/bin/env python3
"""执行 Issue #172 授权的多 checkpoint behavioral pilot v3。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_checkpoint_behavioral_pilot_v2_runner as v2_runner  # noqa: E402
import forge_multi_checkpoint_behavioral_pilot_v3_authorized_protocol as protocol  # noqa: E402

primary = v2_runner.primary
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = protocol.DEFAULT_OUTPUT_DIR
COMPILE_IMAGE = primary.COMPILE_IMAGE
ARMS = ("baseline", "treatment")
PAIR_OUTCOME = "reports/pair-outcome.json"
PILOT_REPORT = "reports/pilot.json"


class AuthorizedPilotError(RuntimeError):
    """授权 identity、canary、预算、evidence 或 cleanup 无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizedPilotError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AuthorizedPilotError(f"JSON 根节点必须是对象: {path}")
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
        raise AuthorizedPilotError(f"不可覆盖已存在的 evidence: {path}") from exc


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
        raise AuthorizedPilotError(f"git {' '.join(arguments)} 失败")
    return result.stdout.strip()


def require_release_identity(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    branch = _git(repo_root, "branch", "--show-current")
    revision = _git(repo_root, "rev-parse", "HEAD")
    origin_main = _git(repo_root, "rev-parse", "origin/main")
    if branch != manifest["execution"]["release_branch"] or revision != origin_main:
        raise AuthorizedPilotError("真实采集要求干净 main == origin/main")
    if _git(repo_root, "status", "--porcelain"):
        raise AuthorizedPilotError("真实采集要求干净工作树")
    baseline = manifest["execution"]["authorization_baseline_commit"]
    try:
        _git(repo_root, "merge-base", "--is-ancestor", baseline, revision)
    except AuthorizedPilotError as exc:
        raise AuthorizedPilotError("release revision 不是授权基线的后代") from exc
    return {"branch": branch, "revision": revision, "origin_main": origin_main}


def require_network_medium(manifest: dict[str, Any]) -> str:
    execution = manifest["execution"]
    if os.environ.get(execution["network_access_medium_env"]) != execution["network_access_medium"]:
        raise AuthorizedPilotError("必须通过 FORGE_NETWORK_ACCESS_MEDIUM=wifi 确认当前网络介质")
    return execution["network_access_medium"]


def require_zero_managed_containers() -> None:
    try:
        v2_runner.require_zero_managed_containers()
    except v2_runner.BehavioralPilotError as exc:
        raise AuthorizedPilotError(str(exc)) from exc


def _require_output_dir(manifest: dict[str, Any], output_dir: Path) -> None:
    expected = Path(manifest["execution"]["evidence_directory"]).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise AuthorizedPilotError("evidence 必须写入冻结授权目录")


def _provider_config_preflight(manifest: dict[str, Any]) -> None:
    from deerflow.config import get_app_config

    provider = manifest["provider"]
    configured = get_app_config().get_model_config(provider["id"])
    if configured is None or configured.model != provider["model"]:
        raise AuthorizedPilotError("config.yaml 缺少冻结 provider model")
    settings = configured.model_dump(exclude_none=True)
    endpoint = settings.get("base_url", settings.get("openai_api_base"))
    if endpoint is None or str(endpoint).rstrip("/") != provider["endpoint"].rstrip("/"):
        raise AuthorizedPilotError("config.yaml provider endpoint 漂移")
    if not os.environ.get(provider["credential_env"]):
        raise AuthorizedPilotError("provider credential env 未注入")


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool = True,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _require_output_dir(manifest, output_dir)
    release = require_release_identity(manifest, repo_root)
    medium = require_network_medium(manifest)
    primary.require_compose_dood()
    require_zero_managed_containers()
    _provider_config_preflight(manifest)
    if require_empty and output_dir.exists() and any(output_dir.iterdir()):
        raise AuthorizedPilotError("首次 preflight 要求授权 evidence 目录为空")
    return {
        "ready": True,
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release["revision"],
        "network_access_medium": medium,
        "provider": manifest["provider"]["id"],
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "zero_managed_containers": True,
    }


def _claim_marker(path: Path, *, kind: str, manifest_sha256: str, revision: str) -> None:
    _write_once(
        path,
        {
            "schema_version": "forge-multi-checkpoint-authorized-attempt-1.0.0",
            "document_type": kind,
            "manifest_sha256": manifest_sha256,
            "release_revision": revision,
            "status": "started",
            "error_class": None,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def _finish_marker(path: Path, *, status: str, error_class: str | None = None) -> None:
    marker = _load_json(path)
    marker.update(status=status, error_class=error_class, updated_at=datetime.now(UTC).isoformat())
    _atomic_write(path, marker)


def collect_provider_canary(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    preflight = collect_preflight(manifest, output_dir=output_dir, repo_root=repo_root, require_empty=True)
    digest = protocol.canonical_sha256(manifest)
    marker = output_dir / manifest["execution"]["canary_marker"]
    _claim_marker(
        marker,
        kind="forge_multi_checkpoint_provider_canary_attempt",
        manifest_sha256=digest,
        revision=preflight["release_revision"],
    )
    started = time.perf_counter()
    try:
        provider = manifest["provider"]
        model = (model_factory or primary._create_provider_model)(provider)
        response = model.invoke(manifest["canary"]["prompt"])
        text = primary._response_text(response).strip()
        actual_model, usage = primary.model_response_metadata(response)
        recorded_tokens = usage.get("total_tokens")
        passed = text == manifest["canary"]["expected_response"] and actual_model == provider["model"] and type(recorded_tokens) is int and 0 <= recorded_tokens <= manifest["canary"]["maximum_recorded_tokens"]
        report = {
            "schema_version": "forge-multi-checkpoint-provider-canary-1.0.0",
            "document_type": "forge_multi_checkpoint_provider_canary",
            "manifest_sha256": digest,
            "release_revision": preflight["release_revision"],
            "provider": provider["id"],
            "endpoint": provider["endpoint"],
            "credential_env": provider["credential_env"],
            "network_access_medium": preflight["network_access_medium"],
            "request_count": 1,
            "request_timeout_seconds": provider["request_timeout_seconds"],
            "max_retries": provider["max_retries"],
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "actual_model": actual_model,
            "recorded_tokens": recorded_tokens,
            "passed": passed,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _write_once(output_dir / "reports/provider-canary.json", report)
        if not passed:
            raise AuthorizedPilotError("provider canary 响应、模型 identity 或 token evidence 无效")
    except BaseException as exc:
        _finish_marker(marker, status="failed", error_class=type(exc).__name__)
        raise
    _finish_marker(marker, status="passed")
    return report


def _passed_canary(manifest: dict[str, Any], output_dir: Path, revision: str) -> dict[str, Any]:
    marker = _load_json(output_dir / manifest["execution"]["canary_marker"])
    report = _load_json(output_dir / "reports/provider-canary.json")
    digest = protocol.canonical_sha256(manifest)
    if (
        marker.get("status") != "passed"
        or marker.get("manifest_sha256") != digest
        or marker.get("release_revision") != revision
        or report.get("passed") is not True
        or report.get("manifest_sha256") != digest
        or report.get("release_revision") != revision
    ):
        raise AuthorizedPilotError("唯一 provider canary 未形成通过终态")
    return report


def _pair_manifest(manifest: dict[str, Any], pair: dict[str, Any], case: Any, pair_dir: Path) -> dict[str, Any]:
    value = v2_runner._pair_manifest(manifest, pair)
    value["execution"]["evidence_directory"] = str(pair_dir)
    value["pilot"].update(
        {
            "case_id": case.case_id,
            "build_system": case.build_system,
            "case_pair_index": pair["case_pair_index"],
            "parent_manifest_sha256": protocol.canonical_sha256(manifest),
        }
    )
    return value


def _case_policy(manifest: dict[str, Any], case: Any, *, arm: str, image_id: str) -> Any:
    continuation = manifest["continuation"]
    provider = manifest["provider"]
    return primary.ExperimentPolicy(
        benchmark_id="forge-multi-checkpoint-behavioral-pilot-v3",
        manifest_sha256=protocol.canonical_sha256(manifest),
        case_id=case.case_id,
        condition=arm,
        repetition=1,
        expected_repo_url=case.repository_url,
        expected_commit_sha=case.commit_sha,
        expected_build_system=case.build_system,
        compile_image=COMPILE_IMAGE,
        image_id=image_id,
        model_name=provider["model"],
        endpoint=provider["endpoint"],
        credential_env=provider["credential_env"],
        request_timeout_seconds=provider["request_timeout_seconds"],
        model_max_retries=0,
        compiler_max_turns=continuation["maximum_model_turns_per_arm"],
        subagent_timeout_seconds=continuation["work_wall_clock_seconds_per_arm"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=case.required_system_packages,
        cmake_arguments=case.cmake_arguments,
        configure_arguments=case.configure_arguments,
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=continuation["maximum_model_turns_per_arm"],
        compiler_graph_recursion_limit=continuation["maximum_graph_steps_per_arm"],
        compiler_wall_clock_seconds=continuation["work_wall_clock_seconds_per_arm"],
        compiler_post_build_reserve_seconds=continuation["cleanup_reserve_seconds_per_arm"],
        source_subdir=case.source_subdir,
        build_targets=case.build_targets,
        artifact_instructions=((case.staged_relative_path, case.build_output_relative_path, case.artifact_type),),
    )


class _AsyncioProxy:
    def __init__(self, runner: asyncio.Runner):
        self._runner = runner

    def run(self, coroutine: Any) -> Any:
        return self._runner.run(coroutine)

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)


@contextmanager
def _adapt_primary_runner(
    manifest: dict[str, Any],
    pair_manifest: dict[str, Any],
    case: Any,
    async_runner: asyncio.Runner,
):
    original = {
        "validate_manifest": primary.validate_manifest,
        "verify_frozen_artifacts": primary.verify_frozen_artifacts,
        "require_release_identity": primary.require_release_identity,
        "require_passed_reachability": primary.require_passed_reachability,
        "PAIR_MARKER": primary.PAIR_MARKER,
        "asyncio": primary.asyncio,
        "run_arm_continuation": primary.run_arm_continuation,
        "_policy": primary._policy,
    }

    def validate(value: Any) -> dict[str, Any]:
        if value != pair_manifest:
            raise AuthorizedPilotError("authorized pair runtime manifest 漂移")
        return value

    def verify(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
        validate(value)
        protocol.verify_frozen_components(manifest, repo_root)

    async def capture_arm(*args: Any, **kwargs: Any) -> dict[str, Any]:
        ledger = kwargs["ledger"]
        arm = kwargs["arm"]
        try:
            result = await original["run_arm_continuation"](*args, **kwargs)
        except Exception as exc:
            return v2_runner.classify_arm_terminal(manifest, arm=arm, ledger=ledger, error=exc)
        return v2_runner._passed_arm(result, ledger)

    primary.validate_manifest = validate
    primary.verify_frozen_artifacts = verify
    primary.require_release_identity = lambda value, repo_root=REPO_ROOT: require_release_identity(manifest, repo_root)
    primary.require_passed_reachability = lambda *_args, **_kwargs: {"recorded_tokens": 0, "inherited_reachability": True}
    primary.PAIR_MARKER = manifest["execution"]["pair_marker"].split("/")[-1]
    primary.asyncio = _AsyncioProxy(async_runner)
    primary.run_arm_continuation = capture_arm
    primary._policy = lambda _value, *, arm, image_id: _case_policy(manifest, case, arm=arm, image_id=image_id)
    try:
        yield
    finally:
        for name, value in original.items():
            setattr(primary, name, value)


def _parent_policy(manifest: dict[str, Any], case: Any, *, image_id: str) -> Any:
    return primary.ExperimentPolicy(
        benchmark_id="forge-multi-checkpoint-behavioral-pilot-v3",
        manifest_sha256=protocol.canonical_sha256(manifest),
        case_id=case.case_id,
        condition="controlled-parent",
        repetition=1,
        expected_repo_url=case.repository_url,
        expected_commit_sha=case.commit_sha,
        expected_build_system=case.build_system,
        compile_image=COMPILE_IMAGE,
        image_id=image_id,
        model_name="deterministic-no-provider",
        endpoint="https://example.invalid/v1",
        credential_env="UNUSED_PROVIDER_KEY",
        request_timeout_seconds=1,
        model_max_retries=0,
        compiler_max_turns=1,
        subagent_timeout_seconds=600,
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=case.required_system_packages,
        cmake_arguments=case.cmake_arguments,
        configure_arguments=case.configure_arguments,
        environment=(),
        minimum_replay_delay_seconds=0,
        source_subdir=case.source_subdir,
        build_targets=case.build_targets,
        artifact_instructions=((case.staged_relative_path, case.build_output_relative_path, case.artifact_type),),
    )


def _run_case_controlled_pair(
    manifest: dict[str, Any],
    case: Any,
    *,
    output_dir: Path,
    repo_root: Path,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    from langgraph.checkpoint.sqlite import SqliteSaver

    from deerflow.compile import operations
    from deerflow.compile.paths import get_host_artifacts_dir, get_host_logs_dir, get_host_repro_dir, get_host_workspace_dir
    from deerflow.compile.schemas import utc_now_iso

    primary.validate_manifest(manifest)
    primary.require_authorized_output_dir(manifest, output_dir)
    release = primary.require_release_identity(manifest, repo_root)
    medium = primary._network_medium(manifest)
    primary.require_compose_dood()
    reachability = primary.require_passed_reachability(manifest, output_dir, release["revision"])
    marker = output_dir / "markers" / primary.PAIR_MARKER
    manifest_digest = protocol.canonical_sha256(manifest)
    primary._claim_marker(
        marker,
        kind="forge_multi_checkpoint_controlled_pair_attempt",
        manifest_sha256=manifest_digest,
        revision=release["revision"],
    )

    capture_id = f"v3-{case.case_id}-{uuid.uuid4().hex[:12]}"
    services = operations.get_compile_services()
    manager = services.manager
    runtime = services.runtime
    docker = primary.lifecycle.environment_checkpoint.DockerCLI()
    snapshot = output_dir / "checkpoint" / capture_id
    parent = manager.create_session(
        thread_id=f"parent-{uuid.uuid4().hex[:12]}",
        session_id=f"parent-{uuid.uuid4().hex[:12]}",
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        repo_url=case.repository_url,
        image=COMPILE_IMAGE,
    )
    parent_ledger = primary.ExperimentLedger.create(
        output_dir / "ledgers/parent.jsonl",
        experiment_id=primary.new_evidence_id("experiment"),
        physical_attempt_id=primary.new_evidence_id("mechanism_attempt"),
        context={"scope": "multi-checkpoint-controlled-parent", "manifest_sha256": manifest_digest, "case_id": case.case_id},
    )
    gate = None
    parent_active = False
    repair_packet: dict[str, Any] | None = None
    arm_results: list[dict[str, Any]] = []
    cleanup_succeeded = False
    try:
        Path(parent.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)
        runtime.create_container(parent)
        manager.save_session(parent)
        clone = runtime.exec(
            parent,
            f"git config --global --add safe.directory /workspace/repo && git init . && git remote add origin {case.repository_url} && git fetch --depth 1 origin {case.commit_sha} && git checkout --detach FETCH_HEAD",
            workdir="/workspace/repo",
            timeout_seconds=180,
        )
        if clone.exit_code != 0:
            raise AuthorizedPilotError(f"{case.case_id} parent 无法检出冻结 commit")
        parent.commit_sha = case.commit_sha
        parent.build_system = case.build_system
        parent.build_system_capabilities = [case.build_system]
        parent.selected_build_system = case.build_system
        parent.status = "inspected"
        manager.save_session(parent)
        supporting = None
        for role, command in case.commands:
            record = primary._record_command(manager=manager, runtime=runtime, session=parent, command=command, role=role)
            if role == "build":
                supporting = record
        if supporting is None:
            raise AuthorizedPilotError(f"{case.case_id} 缺少 supporting build command")
        parent.post_build_supporting_command_id = supporting.command_id
        parent.post_build_started_at = utc_now_iso()
        parent.post_build_commands_remaining = 2
        manager.save_session(parent)

        primary.activate_experiment(
            thread_id=parent.thread_id,
            experiment_id=parent_ledger.experiment_id,
            physical_attempt_id=parent_ledger.physical_attempt_id,
            ledger=parent_ledger,
            policy=_parent_policy(manifest, case, image_id=parent.image_id),
        )
        parent_active = True
        fault = primary.controlled_fault.ControlledFaultV1(
            primary.controlled_fault.ControlledFaultSpec(
                case_id=case.case_id,
                build_output_relative_path=case.build_output_relative_path,
                staged_relative_path=case.staged_relative_path,
                artifact_type=case.artifact_type,
            )
        )
        fault_manifest = fault.inject(session=parent, ledger=parent_ledger, fault_id=primary.new_evidence_id("fault"))
        submit_result: str | None = None

        def submit() -> str:
            nonlocal submit_result, repair_packet
            if submit_result is not None:
                raise AuthorizedPilotError("neutral submit 不得重复执行")
            submit_result = operations.submit_build_result_impl(session=parent, supporting_command_id=supporting.command_id)
            repair_packet = primary.repair_runtime.build_repair_packet(
                json.loads(submit_result),
                parent_ledger.read(),
                expected_artifacts=((case.staged_relative_path, case.artifact_type),),
            )
            if repair_packet is None:
                raise AuthorizedPilotError("controlled failure 未生成 schema-valid repair packet")
            return submit_result

        def evidence() -> dict[str, Any]:
            result = primary.controlled_fault.validate_actionable_failure(ledger=parent_ledger, session=parent)
            result["session_sha256"] = primary.lifecycle.sha256_file(Path(parent.metadata_path))
            result["fault_state_sha256"] = fault_manifest["fault_state_sha256"]
            return result

        coordinator = primary.lifecycle.CaptureCoordinator(output_dir / "checkpoint/coordinator.sqlite")
        with SqliteSaver.from_conn_string(str(output_dir / "checkpoint/messages.sqlite")) as saver:
            saver.setup()
            message_runtime = primary.lifecycle.LifecycleMessageRuntime(saver, submit)
            environment = primary.lifecycle.LifecycleEnvironmentAdapter(
                docker,
                local_snapshot_root=snapshot,
                host_snapshot_root=primary.host_snapshot_root(snapshot),
            )
            gate = primary.lifecycle.RealLifecycleCheckpointGate(
                coordinator=coordinator,
                message_runtime=message_runtime,
                environment=environment,
                budget_capture=primary._budget_manifest,
                manager=manager,
                compile_runtime=runtime,
                owner="multi-checkpoint-behavioral-pilot-v3",
            )
            gate.capture(
                capture_id=capture_id,
                session=parent,
                instruction="Repair this controlled artifact staging failure and submit the build.",
                arm_plan=primary._arm_plan(capture_id),
                bind_sources={
                    "workspace": get_host_workspace_dir(parent.session_id, parent.thread_id, manager.paths),
                    "artifacts": get_host_artifacts_dir(parent.session_id, parent.thread_id, manager.paths),
                    "logs": get_host_logs_dir(parent.session_id, parent.thread_id, manager.paths),
                    "repro": get_host_repro_dir(parent.session_id, parent.thread_id, manager.paths),
                },
                evidence=evidence,
            )
            if repair_packet is None:
                raise AuthorizedPilotError("repair packet 在 checkpoint capture 后缺失")
            message_runtime.repair_packet = repair_packet
            primary.deactivate_experiment(parent.thread_id)
            parent_active = False
            parent_ledger.append("experiment.completed", {"status": "passed"})
            provisioned = {arm: gate.provision_arm(capture_id, arm, parent_session=parent) for arm in ARMS}
            if gate.canonical_arm_environment("baseline") != gate.canonical_arm_environment("treatment"):
                raise AuthorizedPilotError("baseline/treatment 初始环境不同源")
            for arm in manifest["continuation"]["arm_order"]:
                current = provisioned[arm]
                message_state = primary._message_state(gate, current)
                ledger = primary.ExperimentLedger.create(
                    output_dir / "ledgers" / f"{arm}.jsonl",
                    experiment_id=primary.new_evidence_id("experiment"),
                    physical_attempt_id=primary.new_evidence_id("mechanism_attempt"),
                    context={
                        "scope": "multi-checkpoint-controlled-arm",
                        "manifest_sha256": manifest_digest,
                        "case_id": case.case_id,
                        "thread_id": current.session.thread_id,
                        "arm": arm,
                        "capture_id": capture_id,
                    },
                )
                result = primary.asyncio.run(
                    primary.run_arm_continuation(
                        manifest,
                        arm=arm,
                        lifecycle_arm=current,
                        message_state=message_state,
                        ledger=ledger,
                        model_factory=model_factory,
                    )
                )
                arm_results.append(result)
            cleaned = gate.cleanup(capture_id, parent_session=parent)
            cleanup_succeeded = cleaned.phase == "cleaned"
            if not cleanup_succeeded:
                raise AuthorizedPilotError("controlled pair cleanup 未闭合")
        report = {
            "schema_version": "forge-multi-checkpoint-controlled-pair-1.0.0",
            "document_type": "forge_multi_checkpoint_controlled_pair",
            "manifest_sha256": manifest_digest,
            "release_revision": release["revision"],
            "capture_id": capture_id,
            "case_id": case.case_id,
            "build_system": case.build_system,
            "provider": manifest["provider"]["id"],
            "network_access_medium": medium,
            "reachability_recorded_tokens": reachability["recorded_tokens"],
            "arm_order": manifest["continuation"]["arm_order"],
            "arms": arm_results,
            "complete_pair": len(arm_results) == 2,
            "cleanup_succeeded": cleanup_succeeded,
            "passed": len(arm_results) == 2 and cleanup_succeeded,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _atomic_write(output_dir / "reports/controlled-pair.json", report)
    except BaseException as exc:
        if parent_active:
            primary.deactivate_experiment(parent.thread_id)
        if gate is not None and not cleanup_succeeded:
            try:
                record = gate.coordinator.get(capture_id)
                if record.phase not in {"committed", "aborted", "cleanup_pending", "cleaned"}:
                    record = gate.reconcile(capture_id)
                if record.phase == "cleaned":
                    cleanup_succeeded = True
                else:
                    cleanup_succeeded = gate.cleanup(capture_id, parent_session=parent).phase == "cleaned"
            except Exception:
                cleanup_succeeded = False
        else:
            runtime.stop_and_remove_container(parent)
        primary._finish_marker(marker, status="failed", error_class=type(exc).__name__)
        raise
    primary._finish_marker(marker, status="passed")
    return report


def execute_real_pair(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_dir: Path,
    async_runner: asyncio.Runner,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    case = protocol.case_definitions(manifest, REPO_ROOT)[pair["case_id"]]
    pair_manifest = _pair_manifest(manifest, pair, case, pair_dir)
    with _adapt_primary_runner(manifest, pair_manifest, case, async_runner):
        report = _run_case_controlled_pair(
            pair_manifest,
            case,
            output_dir=pair_dir,
            repo_root=REPO_ROOT,
            model_factory=model_factory,
        )
    outcome = v2_runner._pair_outcome(manifest, pair, pair_manifest, pair_dir, report)
    outcome.update(
        schema_version="forge-multi-checkpoint-behavioral-pair-outcome-3.1.0",
        document_type="forge_multi_checkpoint_behavioral_pair_outcome",
        case_id=case.case_id,
        build_system=case.build_system,
        case_pair_index=pair["case_pair_index"],
    )
    return outcome


def _case_summary(case_id: str, outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [item for item in outcomes if item["primary_mechanism_eligible"]]
    four_cell = Counter()
    for item in eligible:
        baseline = item["repair_success"]["baseline"]
        treatment = item["repair_success"]["treatment"]
        label = "both" if baseline and treatment else "baseline_only" if baseline else "treatment_only" if treatment else "neither"
        four_cell[label] += 1
    requests = {arm: sum(item["arms"][arm]["metrics"]["model_requests"] for item in outcomes) for arm in ARMS}
    tokens = {arm: sum(item["arms"][arm]["recorded_tokens"] for item in outcomes) for arm in ARMS}
    transitions = Counter(f"{item['arms']['baseline']['model_behavior']['status']}->{item['arms']['treatment']['model_behavior']['status']}" for item in outcomes)
    scheduled = len(outcomes)
    baseline_success = sum(item["repair_success"]["baseline"] for item in outcomes)
    treatment_success = sum(item["repair_success"]["treatment"] for item in outcomes)
    return {
        "case_id": case_id,
        "scheduled_pairs": scheduled,
        "eligible_pairs": len(eligible),
        "paired_four_cell": {name: four_cell[name] for name in ("both", "baseline_only", "treatment_only", "neither")},
        "requests": requests,
        "recorded_tokens": tokens,
        "failure_transitions": dict(sorted(transitions.items())),
        "itt_repair_success_rate": {
            "baseline": baseline_success / scheduled,
            "treatment": treatment_success / scheduled,
        },
        "itt_paired_delta": (treatment_success - baseline_success) / scheduled,
        "pair_ids": [item["pair_id"] for item in outcomes],
    }


def summarize(
    manifest: dict[str, Any],
    release: dict[str, str],
    canary: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    by_case = {case_id: _case_summary(case_id, [item for item in outcomes if item["case_id"] == case_id]) for case_id in manifest["case_source"]["case_ids"]}
    if any(item["scheduled_pairs"] != 2 for item in by_case.values()):
        raise AuthorizedPilotError("逐 case 报告缺少两个冻结 pair")
    macro = {arm: sum(item["itt_repair_success_rate"][arm] for item in by_case.values()) / len(by_case) for arm in ARMS}
    return {
        "schema_version": "forge-multi-checkpoint-behavioral-pilot-report-3.1.0",
        "document_type": "forge_multi_checkpoint_behavioral_pilot_report",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release["revision"],
        "network_access_medium": manifest["execution"]["network_access_medium"],
        "status": "completed",
        "canary": canary,
        "scheduled_pairs": len(manifest["schedule"]),
        "observed_pairs": len(outcomes),
        "per_case": by_case,
        "equal_weight_macro_average": {
            "case_weights": manifest["analysis"]["case_weights"],
            "baseline_itt_repair_success_rate": macro["baseline"],
            "treatment_itt_repair_success_rate": macro["treatment"],
            "itt_paired_delta": macro["treatment"] - macro["baseline"],
        },
        "recorded_tokens": canary["recorded_tokens"] + sum(item["recorded_tokens"] for item in outcomes),
        "maximum_recorded_tokens": manifest["authorization"]["model_tokens_authorized"],
        "descriptive_only": True,
        "p_value_computed": False,
        "providers_pooled": False,
        "model_ranking_performed": False,
        "historical_pairs_pooled": False,
        "pairs": outcomes,
        "completed_at": datetime.now(UTC).isoformat(),
    }


def run_pilot(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    pair_executor: Any | None = None,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _require_output_dir(manifest, output_dir)
    release = require_release_identity(manifest, repo_root)
    require_network_medium(manifest)
    primary.require_compose_dood()
    require_zero_managed_containers()
    canary = _passed_canary(manifest, output_dir, release["revision"])
    digest = protocol.canonical_sha256(manifest)
    marker = output_dir / manifest["execution"]["batch_marker"]
    _claim_marker(marker, kind="forge_multi_checkpoint_pilot_attempt", manifest_sha256=digest, revision=release["revision"])
    outcomes: list[dict[str, Any]] = []
    try:
        with asyncio.Runner() as async_runner:
            for pair in manifest["schedule"]:
                pair_dir = output_dir / "pairs" / pair["pair_id"]
                outcome_path = pair_dir / PAIR_OUTCOME
                if pair_dir.exists():
                    raise AuthorizedPilotError(f"pair evidence 已存在，禁止自动补跑: {pair['pair_id']}")
                used = canary["recorded_tokens"] + sum(item["recorded_tokens"] for item in outcomes)
                if used + manifest["budget"]["recorded_tokens_per_pair"] > manifest["authorization"]["model_tokens_authorized"]:
                    raise AuthorizedPilotError("剩余总预算不足以启动下一个完整 pair")
                if pair_executor is None:
                    outcome = execute_real_pair(manifest, pair, pair_dir, async_runner)
                else:
                    outcome = pair_executor(manifest, pair, pair_dir)
                _write_once(outcome_path, outcome)
                outcomes.append(outcome)
                require_zero_managed_containers()
        report = summarize(manifest, release, canary, outcomes)
        if report["recorded_tokens"] > manifest["authorization"]["model_tokens_authorized"]:
            raise AuthorizedPilotError("pilot 超过授权总 recorded-token 上限")
        _write_once(output_dir / PILOT_REPORT, report)
    except BaseException as exc:
        _finish_marker(marker, status="failed", error_class=type(exc).__name__)
        raise
    _finish_marker(marker, status="passed")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "preflight", "canary", "batch"))
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
        result = collect_preflight(manifest, output_dir=args.output_dir)
    elif args.command == "canary":
        result = collect_provider_canary(manifest, output_dir=args.output_dir)
    else:
        result = run_pilot(manifest, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
