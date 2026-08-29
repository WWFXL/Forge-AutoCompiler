#!/usr/bin/env python3
"""执行 Issue #184 授权的一次 DeepSeek reachability 与 opaque provenance 单 pair。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shlex
import sys
import time
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_multi_checkpoint_behavioral_pilot_v3_authorized_runner as v3_runner  # noqa: E402
import forge_opaque_build_provenance_real_docker_gate as opaque  # noqa: E402
import forge_opaque_provenance_minimal_canary_execution_protocol as protocol  # noqa: E402

primary = v3_runner.primary
v2_runner = v3_runner.v2_runner
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-minimal-canary-authorized-v1")
ARMS = ("baseline", "treatment")


class ExecutionGateError(RuntimeError):
    """授权 identity、预算、evidence、P2 或 cleanup 无效。"""


def _output_dir(manifest: dict[str, Any], output_dir: Path) -> Path:
    expected = Path(manifest["evidence"]["directory"]).resolve(strict=False)
    if output_dir.resolve(strict=False) != expected:
        raise ExecutionGateError("evidence 必须写入 #182 冻结目录")
    return output_dir


def _release_identity(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    branch = v3_runner._git(repo_root, "branch", "--show-current")
    revision = v3_runner._git(repo_root, "rev-parse", "HEAD")
    origin_main = v3_runner._git(repo_root, "rev-parse", "origin/main")
    if branch != manifest["execution"]["release_branch"] or revision != origin_main:
        raise ExecutionGateError("真实执行要求 main == origin/main")
    if v3_runner._git(repo_root, "status", "--porcelain"):
        raise ExecutionGateError("真实执行要求干净工作树")
    try:
        v3_runner._git(repo_root, "merge-base", "--is-ancestor", manifest["parent"]["authorization_baseline_commit"], revision)
    except v3_runner.AuthorizedPilotError as exc:
        raise ExecutionGateError("release revision 不是 #182 基线的后代") from exc
    return {"branch": branch, "revision": revision, "origin_main": origin_main}


def _network_medium(manifest: dict[str, Any]) -> str:
    medium = os.environ.get(manifest["execution"]["network_access_medium_env"])
    if medium not in manifest["preflight"]["allowed_network_media"]:
        raise ExecutionGateError("必须通过 FORGE_NETWORK_ACCESS_MEDIUM 记录当前网络介质")
    return medium


def _provider_preflight(manifest: dict[str, Any]) -> None:
    try:
        v3_runner._provider_config_preflight(manifest)
    except v3_runner.AuthorizedPilotError as exc:
        raise ExecutionGateError(str(exc)) from exc


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    _output_dir(manifest, output_dir)
    release = _release_identity(manifest, repo_root)
    medium = _network_medium(manifest)
    primary.require_compose_dood()
    try:
        v3_runner.require_zero_managed_containers()
    except v3_runner.AuthorizedPilotError as exc:
        raise ExecutionGateError(str(exc)) from exc
    _provider_preflight(manifest)
    entries = sorted(str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file()) if output_dir.exists() else []
    if require_empty and entries:
        raise ExecutionGateError("reachability 前要求冻结 evidence 目录为空")
    return {
        "ready": True,
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": release["revision"],
        "network_access_medium": medium,
        "evidence_files": entries,
        "zero_managed_containers": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def _create_model(manifest: dict[str, Any], *, experiment_thread_id: str | None = None) -> Any:
    model = primary._create_provider_model(manifest["provider"], experiment_thread_id=experiment_thread_id)
    if bool(getattr(model, "streaming", False)):
        raise ExecutionGateError("冻结 provider 必须使用非 streaming 请求")
    return model


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    preflight = collect_preflight(manifest, output_dir=output_dir, repo_root=repo_root, require_empty=True)
    digest = protocol.canonical_sha256(manifest)
    marker = output_dir / manifest["evidence"]["reachability_marker"]
    v3_runner._claim_marker(
        marker,
        kind="forge_opaque_provenance_reachability_attempt",
        manifest_sha256=digest,
        revision=preflight["release_revision"],
    )
    started = time.perf_counter()
    try:
        model = (model_factory or (lambda value: _create_model(value)))(manifest)
        response = model.invoke(manifest["execution"]["reachability_prompt"])
        text = primary._response_text(response).strip()
        actual_model, usage = primary.model_response_metadata(response)
        tokens = usage.get("total_tokens")
        passed = text == manifest["execution"]["reachability_expected_response"] and actual_model == manifest["provider"]["model"] and type(tokens) is int and 0 <= tokens <= manifest["budget"]["reachability_maximum_recorded_tokens"]
        report = {
            "schema_version": "forge-opaque-provenance-reachability-1.0.0",
            "document_type": "forge_opaque_provenance_reachability",
            "manifest_sha256": digest,
            "release_revision": preflight["release_revision"],
            "provider": manifest["provider"]["id"],
            "endpoint": manifest["provider"]["endpoint"],
            "credential_env": manifest["provider"]["credential_env"],
            "network_access_medium": preflight["network_access_medium"],
            "request_count": 1,
            "request_timeout_seconds": manifest["provider"]["request_timeout_seconds"],
            "max_retries": 0,
            "streaming": False,
            "fallback_used": False,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "actual_model": actual_model,
            "recorded_tokens": tokens,
            "passed": passed,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        v3_runner._write_once(output_dir / manifest["execution"]["reachability_report"], report)
        if not passed:
            raise ExecutionGateError("reachability 响应、模型 identity 或 token evidence 无效")
    except BaseException as exc:
        v3_runner._finish_marker(marker, status="failed", error_class=type(exc).__name__)
        raise
    v3_runner._finish_marker(marker, status="passed")
    return report


def _passed_reachability(manifest: dict[str, Any], output_dir: Path, revision: str) -> dict[str, Any]:
    expected_files = sorted(
        (
            manifest["evidence"]["reachability_marker"],
            manifest["execution"]["reachability_report"],
        )
    )
    actual_files = sorted(str(path.relative_to(output_dir)).replace("\\", "/") for path in output_dir.rglob("*") if path.is_file())
    if actual_files != expected_files:
        raise ExecutionGateError("pair 前 evidence 不是唯一 reachability 终态")
    marker = v3_runner._load_json(output_dir / manifest["evidence"]["reachability_marker"])
    report = v3_runner._load_json(output_dir / manifest["execution"]["reachability_report"])
    digest = protocol.canonical_sha256(manifest)
    if (
        marker.get("status") != "passed"
        or marker.get("manifest_sha256") != digest
        or marker.get("release_revision") != revision
        or report.get("passed") is not True
        or report.get("manifest_sha256") != digest
        or report.get("release_revision") != revision
        or type(report.get("recorded_tokens")) is not int
        or report["recorded_tokens"] > manifest["budget"]["reachability_maximum_recorded_tokens"]
    ):
        raise ExecutionGateError("唯一 reachability 未形成同 revision 通过终态")
    return report


def require_arm_budget(manifest: dict[str, Any], *, reachability_tokens: int, completed_arm_tokens: list[int]) -> None:
    values = [reachability_tokens, *completed_arm_tokens]
    if any(type(value) is not int or value < 0 for value in values):
        raise ExecutionGateError("recorded-token evidence 无效")
    used = sum(values)
    if used + manifest["continuation"]["maximum_recorded_tokens_per_arm"] > manifest["budget"]["stage_maximum_recorded_tokens"]:
        raise ExecutionGateError("剩余总预算不足以启动下一臂")


def _policy(manifest: dict[str, Any], *, arm: str, image_id: str) -> Any:
    continuation = manifest["continuation"]
    provider = manifest["provider"]
    return primary.ExperimentPolicy(
        benchmark_id="forge-opaque-provenance-minimal-canary",
        manifest_sha256=protocol.canonical_sha256(manifest),
        case_id=opaque.CASE_ID,
        condition=arm,
        repetition=1,
        expected_repo_url=opaque.REPOSITORY_URL,
        expected_commit_sha=opaque.COMMIT_SHA,
        expected_build_system="cmake",
        compile_image=opaque.COMPILE_IMAGE,
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
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=continuation["maximum_model_turns_per_arm"],
        compiler_graph_recursion_limit=continuation["maximum_graph_steps_per_arm"],
        compiler_wall_clock_seconds=continuation["work_wall_clock_seconds_per_arm"],
        compiler_post_build_reserve_seconds=continuation["cleanup_reserve_seconds_per_arm"],
        source_subdir="examples",
        build_targets=(opaque.TARGET,),
        artifact_instructions=((opaque.STAGED_ARTIFACT, opaque.BUILD_OUTPUT, "executable"),),
    )


def _parent_policy(manifest: dict[str, Any], *, image_id: str) -> Any:
    policy = _policy(manifest, arm="controlled-parent", image_id=image_id)
    return replace(
        policy,
        model_name="deterministic-no-provider",
        endpoint="https://example.invalid/v1",
        credential_env="UNUSED_PROVIDER_KEY",
        request_timeout_seconds=1,
        compiler_max_turns=1,
    )


def _constraint_failures(session: Any) -> list[str]:
    if session.verification is None:
        return []
    checks = [check for check in session.verification.checks if check.name == "benchmark_constraints"]
    return [] if not checks else list(checks[0].actual)


def _failure_event(ledger: Any) -> dict[str, Any]:
    failures = [event for event in ledger.read() if event["event"] == "failure.recorded"]
    if len(failures) != 1:
        raise ExecutionGateError("opaque parent 必须恰有一个 failure.recorded")
    return failures[0]


def _command_tokens(command: str) -> tuple[str, tuple[str, ...]]:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ExecutionGateError("trusted command 无法规范化") from exc
    if not tokens:
        raise ExecutionGateError("trusted command 为空")
    return PurePosixPath(tokens[0]).name, tuple(tokens[1:])


def _evaluate_arm_p2(session: Any, frozen: Any, parent_command_id: str) -> tuple[Any, tuple[Any, ...]]:
    artifact = Path(session.leadagent_repo_dir) / opaque.BUILD_OUTPUT
    tree = Path(session.leadagent_repo_dir) / "build/build.ninja"
    if not artifact.is_file() or not tree.is_file():
        raise ExecutionGateError("arm 丢失冻结 build tree 或 workspace artifact")
    if artifact.stat().st_size != frozen.artifact_size or primary.lifecycle.sha256_file(artifact) != frozen.artifact_sha256:
        raise ExecutionGateError("arm workspace artifact identity 漂移")
    if primary.lifecycle.sha256_file(tree) != frozen.build_tree_sha256:
        raise ExecutionGateError("arm build tree identity 漂移")

    parent = opaque._parent_invocation(frozen, parent_command_id)
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
        output_paths = (opaque.BUILD_OUTPUT,) if record.command_id == producer_id else ()
        invocation = opaque.provenance.record_invocation(
            command_id=record.command_id,
            physical_attempt_id=frozen.physical_attempt_id,
            sequence=len(invocations) + 1,
            repository_url=frozen.repository_url,
            commit_sha=frozen.commit_sha,
            image_id=frozen.image_id,
            executable=executable,
            argv=argv,
            workdir=record.workdir,
            previous_hash=previous_hash,
            exit_code=record.exit_code if record.exit_code is not None else 1,
            timed_out=record.timed_out,
            output_paths=output_paths,
            model_declared_role=record.role,
        )
        invocations.append(invocation)
        previous_hash = invocation.ledger_hash
    commands = {item.command_id: item for item in invocations}
    if producer_id not in commands:
        producer_id = parent_command_id
    identity = opaque.provenance.ArtifactIdentity(
        schema_version=opaque.provenance.SCHEMA_VERSION,
        physical_attempt_id=frozen.physical_attempt_id,
        producer_command_id=producer_id,
        repository_url=frozen.repository_url,
        commit_sha=frozen.commit_sha,
        image_id=frozen.image_id,
        relative_path=frozen.artifact_relative_path,
        artifact_type=frozen.artifact_type,
        size=frozen.artifact_size,
        sha256=frozen.artifact_sha256,
        observed_after_sequence=len(invocations) + 1,
    )
    return opaque.provenance.evaluate_p2(frozen, tuple(invocations), identity), tuple(invocations)


def _run_pair(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
    repo_root: Path,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    from langgraph.checkpoint.sqlite import SqliteSaver

    from deerflow.compile import operations
    from deerflow.compile.paths import get_host_artifacts_dir, get_host_logs_dir, get_host_repro_dir, get_host_workspace_dir
    from deerflow.compile.schemas import utc_now_iso

    preflight = collect_preflight(manifest, output_dir=output_dir, repo_root=repo_root, require_empty=False)
    reachability = _passed_reachability(manifest, output_dir, preflight["release_revision"])
    digest = protocol.canonical_sha256(manifest)
    marker = output_dir / manifest["execution"]["pair_marker"]
    v3_runner._claim_marker(marker, kind="forge_opaque_provenance_pair_attempt", manifest_sha256=digest, revision=preflight["release_revision"])

    capture_id = f"opaque-{uuid.uuid4().hex[:12]}"
    services = operations.get_compile_services()
    manager = services.manager
    runtime = services.runtime
    docker = primary.lifecycle.environment_checkpoint.DockerCLI()
    snapshot = output_dir / "checkpoint" / capture_id
    parent = manager.create_session(
        thread_id=f"parent-{uuid.uuid4().hex[:12]}",
        session_id=f"parent-{uuid.uuid4().hex[:12]}",
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        repo_url=opaque.REPOSITORY_URL,
        image=opaque.COMPILE_IMAGE,
    )
    parent_ledger = primary.ExperimentLedger.create(
        output_dir / manifest["execution"]["parent_ledger"],
        experiment_id=primary.new_evidence_id("experiment"),
        physical_attempt_id=primary.new_evidence_id("mechanism_attempt"),
        context={"scope": "opaque-provenance-controlled-parent", "manifest_sha256": digest, "case_id": opaque.CASE_ID},
    )
    gate = None
    parent_active = False
    cleanup_succeeded = False
    arm_results: list[dict[str, Any]] = []
    try:
        Path(parent.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)
        runtime.create_container(parent)
        manager.save_session(parent)
        clone = runtime.exec(
            parent,
            f"git config --global --add safe.directory /workspace/repo && git init . && git remote add origin {opaque.REPOSITORY_URL} && git fetch --depth 1 origin {opaque.COMMIT_SHA} && git checkout --detach FETCH_HEAD",
            workdir=opaque.WORKDIR,
            timeout_seconds=180,
        )
        if clone.exit_code != 0:
            raise ExecutionGateError("parent 无法检出冻结 commit")
        parent.commit_sha = opaque.COMMIT_SHA
        parent.build_system = "cmake"
        parent.build_system_capabilities = ["cmake"]
        parent.selected_build_system = "cmake"
        parent.status = "inspected"
        manager.save_session(parent)
        supporting = primary._record_command(manager=manager, runtime=runtime, session=parent, command=opaque.PARENT_COMMAND, role="build")
        parent.post_build_supporting_command_id = supporting.command_id
        parent.post_build_started_at = utc_now_iso()
        parent.post_build_commands_remaining = 2
        manager.save_session(parent)

        workspace_artifact = Path(parent.leadagent_repo_dir) / opaque.BUILD_OUTPUT
        build_tree = Path(parent.leadagent_repo_dir) / "build/build.ninja"
        frozen_values = {
            "build_tree_sha256": primary.lifecycle.sha256_file(build_tree),
            "artifact_size": workspace_artifact.stat().st_size,
            "artifact_sha256": primary.lifecycle.sha256_file(workspace_artifact),
        }
        parent_frozen = opaque.build_frozen_identity(
            image_id=parent.image_id,
            physical_attempt_id=parent_ledger.physical_attempt_id,
            **frozen_values,
        )
        parent_p2, parent_history = opaque.evaluate_parent(parent_frozen, parent_command_id=supporting.command_id)
        primary.activate_experiment(
            thread_id=parent.thread_id,
            experiment_id=parent_ledger.experiment_id,
            physical_attempt_id=parent_ledger.physical_attempt_id,
            ledger=parent_ledger,
            policy=_parent_policy(manifest, image_id=parent.image_id),
        )
        parent_active = True
        submit_result: str | None = None

        def submit_parent() -> str:
            nonlocal submit_result
            if submit_result is not None:
                raise ExecutionGateError("parent submit 不得重复执行")
            submit_result = operations.submit_build_result_impl(session=parent, supporting_command_id=supporting.command_id)
            return submit_result

        def capture_evidence() -> dict[str, Any]:
            failure = _failure_event(parent_ledger)["payload"]
            payload = json.loads(submit_result or "{}")
            if (
                payload.get("status") != "failed"
                or payload.get("replay_status") != "not_run"
                or failure.get("classification") != "build_system_unproven"
                or failure.get("secondary_classifications") != []
                or _constraint_failures(parent) != ["build_system_unproven"]
                or parent.replay_attempts
            ):
                raise ExecutionGateError("parent 未形成单一 opaque provenance failure")
            return {
                "classification": failure["classification"],
                "failure_id": failure["failure_id"],
                "submit_attempt_id": failure["submit_attempt_id"],
                "session_sha256": primary.lifecycle.sha256_file(Path(parent.metadata_path)),
                "parent_p2": asdict(parent_p2),
                "parent_command_history_sha256": opaque.provenance.command_history_sha256(parent_history),
            }

        coordinator = primary.lifecycle.CaptureCoordinator(output_dir / "checkpoint/coordinator.sqlite")
        with SqliteSaver.from_conn_string(str(output_dir / "checkpoint/messages.sqlite")) as saver:
            saver.setup()
            message_runtime = primary.lifecycle.LifecycleMessageRuntime(saver, submit_parent, repair_packet=opaque.build_repair_packet())
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
                owner="opaque-provenance-minimal-canary",
            )
            gate.capture(
                capture_id=capture_id,
                session=parent,
                instruction="Continue from the failed submit and satisfy the verifier without changing the frozen repository or target.",
                arm_plan=primary._arm_plan(capture_id),
                bind_sources={
                    "workspace": get_host_workspace_dir(parent.session_id, parent.thread_id, manager.paths),
                    "artifacts": get_host_artifacts_dir(parent.session_id, parent.thread_id, manager.paths),
                    "logs": get_host_logs_dir(parent.session_id, parent.thread_id, manager.paths),
                    "repro": get_host_repro_dir(parent.session_id, parent.thread_id, manager.paths),
                },
                evidence=capture_evidence,
            )
            primary.deactivate_experiment(parent.thread_id)
            parent_active = False
            parent_ledger.append("experiment.completed", {"status": "passed"})
            provisioned = {arm: gate.provision_arm(capture_id, arm, parent_session=parent) for arm in ARMS}
            if gate.canonical_arm_environment("baseline") != gate.canonical_arm_environment("treatment"):
                raise ExecutionGateError("baseline/treatment 初始环境不同源")

            with asyncio.Runner() as async_runner:
                original_policy = primary._policy
                primary._policy = lambda _value, *, arm, image_id: _policy(manifest, arm=arm, image_id=image_id)
                try:
                    for arm in manifest["schedule"][0]["arm_order"]:
                        require_arm_budget(
                            manifest,
                            reachability_tokens=reachability["recorded_tokens"],
                            completed_arm_tokens=[result["recorded_tokens"] for result in arm_results],
                        )
                        current = provisioned[arm]
                        ledger = primary.ExperimentLedger.create(
                            output_dir / manifest["execution"]["arm_ledger_directory"] / f"{arm}.jsonl",
                            experiment_id=primary.new_evidence_id("experiment"),
                            physical_attempt_id=primary.new_evidence_id("mechanism_attempt"),
                            context={"scope": "opaque-provenance-arm", "manifest_sha256": digest, "arm": arm, "capture_id": capture_id},
                        )
                        message_state = primary._message_state(gate, current)
                        try:
                            result = async_runner.run(
                                primary.run_arm_continuation(
                                    manifest,
                                    arm=arm,
                                    lifecycle_arm=current,
                                    message_state=message_state,
                                    ledger=ledger,
                                    model_factory=model_factory,
                                )
                            )
                        except Exception as exc:
                            result = v2_runner.classify_arm_terminal(manifest, arm=arm, ledger=ledger, error=exc)
                        else:
                            result = v2_runner._passed_arm(result, ledger)
                        authoritative = manager.load_session(current.session.session_id, current.session.thread_id)
                        arm_frozen = opaque.build_frozen_identity(
                            image_id=authoritative.image_id,
                            physical_attempt_id=ledger.physical_attempt_id,
                            **frozen_values,
                        )
                        p2, history = _evaluate_arm_p2(authoritative, arm_frozen, supporting.command_id)
                        result["p2"] = asdict(p2)
                        result["command_history_sha256"] = opaque.provenance.command_history_sha256(history)
                        result["post_checkpoint_provenance_conversion"] = p2.status == "proven"
                        if result["verification_outcome"]["status"] == "passed" and p2.status != "proven":
                            raise ExecutionGateError(f"{arm} production verification 通过但 P2 未证明")
                        arm_results.append(result)
                finally:
                    primary._policy = original_policy
            cleaned = gate.cleanup(capture_id, parent_session=parent)
            cleanup_succeeded = cleaned.phase == "cleaned"
            if not cleanup_succeeded:
                raise ExecutionGateError("pair cleanup 未闭合")
            try:
                v3_runner.require_zero_managed_containers()
            except v3_runner.AuthorizedPilotError as exc:
                raise ExecutionGateError("pair cleanup 后仍存在 managed container") from exc

        total_tokens = reachability["recorded_tokens"] + sum(item["recorded_tokens"] for item in arm_results)
        if total_tokens > manifest["budget"]["stage_maximum_recorded_tokens"]:
            raise ExecutionGateError("阶段 recorded-token 超过机械上限")
        report = {
            "schema_version": "forge-opaque-provenance-minimal-canary-report-1.0.0",
            "document_type": "forge_opaque_provenance_minimal_canary_report",
            "manifest_sha256": digest,
            "release_revision": preflight["release_revision"],
            "evidence_identity_sha256": manifest["evidence"]["identity_sha256"],
            "case_id": opaque.CASE_ID,
            "pair_id": manifest["schedule"][0]["pair_id"],
            "arm_order": manifest["schedule"][0]["arm_order"],
            "provider": manifest["provider"]["id"],
            "network_access_medium": preflight["network_access_medium"],
            "reachability_recorded_tokens": reachability["recorded_tokens"],
            "arms": arm_results,
            "recorded_tokens": total_tokens,
            "maximum_recorded_tokens": manifest["budget"]["stage_maximum_recorded_tokens"],
            "complete_pair": len(arm_results) == 2,
            "cleanup_succeeded": cleanup_succeeded,
            "descriptive_only": True,
            "treatment_effect_estimated": False,
            "p_value_computed": False,
            "model_ranking_performed": False,
            "historical_pairs_pooled": False,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        v3_runner._write_once(output_dir / manifest["evidence"]["canary_report"], report)
    except BaseException as exc:
        if parent_active:
            primary.deactivate_experiment(parent.thread_id)
        if gate is not None and not cleanup_succeeded:
            try:
                record = gate.coordinator.get(capture_id)
                if record.phase not in {"committed", "aborted", "cleanup_pending", "cleaned"}:
                    record = gate.reconcile(capture_id)
                cleanup_succeeded = record.phase == "cleaned" or gate.cleanup(capture_id, parent_session=parent).phase == "cleaned"
            except Exception:
                cleanup_succeeded = False
        else:
            runtime.stop_and_remove_container(parent)
        v3_runner._finish_marker(marker, status="failed", error_class=type(exc).__name__)
        raise
    v3_runner._finish_marker(marker, status="passed")
    return report


def execute_pair(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    return _run_pair(manifest, output_dir=output_dir, repo_root=repo_root, model_factory=model_factory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "preflight", "reachability", "pair"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        protocol.verify_frozen_components(manifest)
        result: Any = {"status": "valid", "manifest_sha256": protocol.canonical_sha256(manifest), "provider_calls": 0, "formal_attempts": 0, "model_tokens": 0}
    elif args.command == "preflight":
        result = collect_preflight(manifest, output_dir=args.output_dir, require_empty=True)
    elif args.command == "reachability":
        result = execute_reachability(manifest, output_dir=args.output_dir)
    else:
        result = execute_pair(manifest, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
