#!/usr/bin/env python3
"""执行 Workflow + Jev + Agent 混合链路的零 Provider Docker 资格。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from deerflow.compile.hybrid_workflow import (  # noqa: E402
    HybridAgentHandoff,
    HybridStepOutcome,
    HybridWorkflowBudget,
    HybridWorkflowObservation,
    HybridWorkflowSnapshot,
    run_hybrid_workflow,
)
from deerflow.compile.jev_controller import (  # noqa: E402
    ACTION_FAMILIES,
    CalibrationContract,
    CandidateAction,
    DecisionState,
    TypedDecision,
    VerifierCapabilities,
)
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    get_compile_services,
    inspect_build_system_impl,
    prepare_compile_session_impl,
    submit_build_result_impl,
)
from deerflow.tools.bound_compile_tools import _run_container_bash_impl  # noqa: E402

IDENTITY = "cpp-jev-hybrid-workflow-qualification-v1"
BRANCH = "yiwei/409-jev-hybrid-workflow"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / f"{IDENTITY}.json"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.json"
REPORT_MARKDOWN_PATH = REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.md"
FAILURE_JSON_PATH = REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}-failure.json"
FAILURE_MARKDOWN_PATH = REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}-failure.md"
MANAGED_CONTAINER_PREFIXES = ("deerflow-compile-", "deerflow-replay-")
CALIBRATION = CalibrationContract(model="jev-1.13.0", coefficient=1.0, intercept=0.0, threshold=0.8)
VERIFIER_CAPABILITIES = VerifierCapabilities(True, True, True, True)


class QualificationError(RuntimeError):
    """资格身份、执行或证据不满足冻结合同。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _manifest_sha256(manifest: dict[str, Any]) -> str:
    return _sha256_bytes(_canonical_json(manifest).encode())


def _write_once(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise QualificationError(f"create-once 路径已存在: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _write_once_json(path: Path, value: Any) -> None:
    _write_once(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={REPO_ROOT}", *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise QualificationError("无法核验 qualification Git identity")
    return result.stdout.strip()


def _docker_output(*arguments: str) -> str:
    result = subprocess.run(
        ["docker", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise QualificationError("无法核验 qualification Docker identity")
    return result.stdout.strip()


def _load_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError("无法读取 qualification manifest") from exc
    if manifest.get("identity") != IDENTITY or manifest.get("branch") != BRANCH:
        raise QualificationError("qualification manifest identity 漂移")
    if manifest.get("authorization") != {
        "credential_reads": False,
        "docker_execution": True,
        "formal_attempts": 0,
        "provider_calls": False,
        "qualification_attempts": 3,
    }:
        raise QualificationError("qualification 授权边界漂移")
    if manifest.get("evidence", {}).get("create_once") is not True:
        raise QualificationError("qualification evidence 必须 create-once")
    if len(manifest.get("cases", [])) != 3:
        raise QualificationError("qualification 必须冻结三个构建系统 case")
    return manifest


def require_zero_managed_resources() -> None:
    names = _docker_output("ps", "-a", "--format", "{{.Names}}")
    managed = sorted(name for name in names.splitlines() if name.startswith(MANAGED_CONTAINER_PREFIXES))
    if managed:
        raise QualificationError(f"存在 Compile Session/replay orphan: {','.join(managed)}")
    paused = _docker_output("ps", "-q", "--filter", "status=paused", "--filter", "label=deerflow.compile.managed=true")
    managed_images = _docker_output("images", "-q", "--filter", "label=deerflow.compile.managed=true")
    if paused or managed_images:
        raise QualificationError("存在 paused parent 或受管镜像")


def preflight(*, require_clean: bool = True, require_absent_outputs: bool = True) -> dict[str, Any]:
    manifest = _load_manifest()
    if _git("branch", "--show-current") != BRANCH:
        raise QualificationError("当前分支与 qualification identity 不一致")
    if require_clean and _git("status", "--porcelain", "--untracked-files=normal"):
        raise QualificationError("qualification 执行要求干净工作树")
    head = _git("rev-parse", "HEAD")
    implementation_revision = manifest["implementation_revision"]
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", implementation_revision, head],
        cwd=REPO_ROOT,
        check=False,
        timeout=30,
    )
    if ancestor.returncode != 0:
        raise QualificationError("HEAD 不是冻结 implementation revision 的后代")
    remote_refs = {line.strip() for line in _git("branch", "-r", "--contains", head).splitlines()}
    if f"origin/{BRANCH}" not in remote_refs:
        raise QualificationError("qualification revision 尚未推送")
    for relative_path, expected_sha256 in manifest["components"].items():
        if _file_sha256(REPO_ROOT / relative_path) != expected_sha256:
            raise QualificationError(f"冻结组件漂移: {relative_path}")
    actual_image_id = _docker_output("image", "inspect", manifest["environment"]["compile_image"], "--format", "{{.Id}}")
    if actual_image_id != manifest["environment"]["image_id"]:
        raise QualificationError("qualification Docker image ID 漂移")
    if require_absent_outputs:
        evidence_root = REPO_ROOT / manifest["evidence"]["root"]
        output_paths = (REPORT_JSON_PATH, REPORT_MARKDOWN_PATH, FAILURE_JSON_PATH, FAILURE_MARKDOWN_PATH)
        if evidence_root.exists() or any(path.exists() for path in output_paths):
            raise QualificationError("qualification create-once 输出已存在")
    require_zero_managed_resources()
    os.environ["DEER_FLOW_WORKSPACE_ROOT"] = str(REPO_ROOT)
    os.environ["DEER_FLOW_HOST_WORKSPACE_ROOT"] = str(REPO_ROOT)
    return {
        "branch": BRANCH,
        "release_revision": head,
        "implementation_revision": implementation_revision,
        "manifest_sha256": _manifest_sha256(manifest),
        "image_id": actual_image_id,
        "provider_calls": 0,
        "credential_reads": 0,
        "formal_attempts": 0,
        "managed_resources_before": 0,
    }


class CaseHarness:
    def __init__(self, manifest: dict[str, Any], case: dict[str, Any], sequence: int):
        self.manifest = manifest
        self.case = case
        self.sequence = sequence
        self.services = get_compile_services()
        self.session = None
        self.observation_id = 0
        self.command_records: list[Any] = []
        self.agent_triggers: list[str] = []
        self.submit_payload: dict[str, Any] | None = None

    def prepare(self) -> dict[str, Any]:
        digest = _manifest_sha256(self.manifest)
        task_id = self.case["task_id"]
        thread_id = f"jev-hybrid-qualification-{self.sequence:02d}-{task_id}-{digest[:10]}"
        self.session = prepare_compile_session_impl(
            thread_id=thread_id,
            repo_url=self.case["repository_url"],
            run_id=f"jev-hybrid-qualification-{uuid.uuid4().hex}",
            task_description=f"Jev hybrid workflow zero-provider qualification: {task_id}",
        )
        if self.session.image_id != self.manifest["environment"]["image_id"]:
            raise QualificationError(f"{task_id} compile image identity 漂移")
        clone, _message = clone_repository_impl(
            session=self.session,
            repo_url=self.case["repository_url"],
            commit_sha=self.case["commit_sha"],
            depth=1,
            max_retries=1,
        )
        if clone.exit_code != 0 or self.session.commit_sha != self.case["commit_sha"]:
            raise QualificationError(f"{task_id} exact commit checkout 失败")
        primary, detected, _suggested = inspect_build_system_impl(session=self.session)
        if primary != self.case["build_system"]:
            raise QualificationError(f"{task_id} build-system detection 漂移")
        self.session.selected_build_system = primary
        self.services.manager.save_session(self.session)
        return {
            "primary": primary,
            "detected": [{"build_system": system, "marker": marker} for system, marker in detected],
        }

    def _current(self) -> Any:
        if self.session is None:
            raise QualificationError("Compile Session 尚未准备")
        return self.services.manager.load_session(self.session.session_id, self.session.thread_id)

    def _run_commands(self, commands: list[dict[str, str]]) -> HybridStepOutcome:
        for item in commands:
            result, _message, record = _run_container_bash_impl(
                session=self._current(),
                command=item["command"],
                command_role=item["role"],
                timeout_seconds=self.manifest["budget"]["command_timeout_seconds"],
                workdir="/workspace/repo",
            )
            self.command_records.append(record)
            if result.exit_code != 0 or record.timed_out:
                return HybridStepOutcome(False, f"{item['role']}_command_failed")
        return HybridStepOutcome(True, "bound_commands_succeeded")

    def _submit(self) -> HybridStepOutcome:
        current = self._current()
        successful = [record for record in current.commands if record.exit_code == 0 and not record.timed_out]
        build_records = [record for record in successful if record.role == "build"]
        if not build_records:
            return HybridStepOutcome(False, "supporting_build_missing")
        recipe_command_ids = [record.command_id for record in successful if record.role in {"dependency", "dependency_setup", "configure", "build", "artifact_stage"}]
        verification_command_ids = [record.command_id for record in successful if record.role == "smoke"]
        self.submit_payload = json.loads(
            submit_build_result_impl(
                session=current,
                supporting_command_id=build_records[-1].command_id,
                recipe_command_ids=recipe_command_ids,
                verification_command_ids=verification_command_ids,
            )
        )
        passed = self.submit_payload.get("status") == "passed" and self.submit_payload.get("replay_status") == "passed"
        return HybridStepOutcome(passed, "strict_submit_passed" if passed else "strict_submit_failed", reported_terminal_success=passed)

    def _finish_normal_path(self) -> HybridStepOutcome:
        outcome = self._run_commands(self.case["workflow_after_direct"])
        return self._submit() if outcome.succeeded else outcome

    def observer(self, _snapshot: HybridWorkflowSnapshot) -> HybridWorkflowObservation:
        current = self._current()
        self.observation_id += 1
        state_id = f"{self.case['task_id']}-state-{self.observation_id}"
        terminal_status = "pending"
        terminal_reason = None
        if current.status == "verified" and current.verification is not None and current.verification.status == "passed":
            terminal_status = "strict_success"
            terminal_reason = "forge_strict_verification_passed"
        elif current.status in {"failed", "verification_failed", "cancelled", "timed_out"}:
            terminal_status = "terminal_failure"
            terminal_reason = f"compile_session_{current.status}"
        candidates = tuple(
            CandidateAction(
                action_id=f"{state_id}:{family}",
                action_family=family,
                bound_commands=tuple(self.case["candidate_commands"].get(family, [])),
                direct_execution=family != "escalate_agent",
                preconditions_satisfied=True,
            )
            for family in ACTION_FAMILIES
        )
        successful_roles = {record.role for record in current.commands if record.exit_code == 0 and not record.timed_out}
        return HybridWorkflowObservation(
            observation_id=self.observation_id,
            decision_state=DecisionState(
                state_id=state_id,
                build_system=self.case["build_system"],
                phase_facts={
                    "dependency_succeeded": bool(successful_roles & {"dependency", "dependency_setup"}),
                    "configured": "configure" in successful_roles,
                    "build_succeeded": "build" in successful_roles,
                    "strict_verified": terminal_status == "strict_success",
                },
                remaining_actions=0,
                remaining_wall_clock_seconds=0,
                expected_request_fingerprint=hashlib.sha256(f"{IDENTITY}:{state_id}".encode()).hexdigest(),
            ),
            candidates=candidates,
            verifier_capabilities=VERIFIER_CAPABILITIES,
            terminal_status=terminal_status,
            terminal_reason=terminal_reason,
        )

    def decision_provider(self, observation: HybridWorkflowObservation) -> TypedDecision | None:
        if self.case["route_mode"] == "agent":
            return None
        selected = self.case["selected_action_family"]
        probabilities = {family: 0.01 / 3 for family in ACTION_FAMILIES}
        probabilities[selected] = 0.99
        return TypedDecision(
            state_id=observation.decision_state.state_id,
            model=CALIBRATION.model,
            request_fingerprint=observation.decision_state.expected_request_fingerprint,
            primary_choice=selected,
            reverse_choice=selected,
            probabilities=probabilities,
            reverse_probabilities=probabilities,
        )

    def direct_executor(self, candidate: CandidateAction) -> HybridStepOutcome:
        expected_family = self.case["selected_action_family"]
        if candidate.action_family != expected_family or tuple(self.case["candidate_commands"][expected_family]) != candidate.bound_commands:
            return HybridStepOutcome(False, "bound_candidate_identity_mismatch")
        outcome = self._run_commands([{"role": expected_family, "command": command} for command in candidate.bound_commands])
        return self._finish_normal_path() if outcome.succeeded else outcome

    def agent_runner(self, handoff: HybridAgentHandoff) -> HybridStepOutcome:
        self.agent_triggers.append(handoff.trigger)
        outcome = self._run_commands(self.case["agent_commands"])
        return self._submit() if outcome.succeeded else outcome

    def cleanup(self, *, failed: bool) -> dict[str, Any]:
        if self.session is None:
            return {"succeeded": True, "removed": True, "status": "not_created"}
        current = self._current()
        finalized, cleanup = cleanup_and_finalize_compile_session_impl(
            session=current,
            interrupted_status="failed" if failed and current.status != "verified" else None,
            error="Hybrid workflow qualification failed." if failed else None,
        )
        return {
            "succeeded": cleanup.succeeded,
            "removed": cleanup.removed,
            "status": finalized.status,
            "session_id": finalized.session_id,
            "thread_id": finalized.thread_id,
            "session_path": str(Path(finalized.metadata_path).relative_to(REPO_ROOT)),
            "replay_status": finalized.replay_verification.status if finalized.replay_verification else None,
        }


async def _run_case(manifest: dict[str, Any], case: dict[str, Any], sequence: int) -> dict[str, Any]:
    harness = CaseHarness(manifest, case, sequence)
    detection: dict[str, Any] | None = None
    result = None
    cleanup: dict[str, Any] | None = None
    error_class: str | None = None
    try:
        detection = harness.prepare()
        result = await run_hybrid_workflow(
            budget=HybridWorkflowBudget(**manifest["budget"]["hybrid_workflow"]),
            calibration=CALIBRATION,
            observer=harness.observer,
            decision_provider=harness.decision_provider,
            direct_executor=harness.direct_executor,
            agent_runner=harness.agent_runner,
        )
        if result.status != "strict_success":
            raise QualificationError(f"{case['task_id']} 混合链路未得到严格成功: {result.reason}")
        cleanup = harness.cleanup(failed=False)
        if not cleanup["succeeded"] or not cleanup["removed"] or cleanup["status"] != "completed":
            raise QualificationError(f"{case['task_id']} cleanup/finalize 未闭合")
    except Exception as exc:
        error_class = type(exc).__name__
        if cleanup is None:
            try:
                cleanup = harness.cleanup(failed=True)
            except Exception:
                cleanup = {"succeeded": False, "removed": False, "status": "cleanup_exception"}
        raise
    finally:
        require_zero_managed_resources()
    assert result is not None and cleanup is not None and detection is not None
    return {
        "sequence": sequence,
        "task_id": case["task_id"],
        "build_system": case["build_system"],
        "route_mode": case["route_mode"],
        "selected_action_family": case["selected_action_family"],
        "detection": detection,
        "hybrid_result": {
            "status": result.status,
            "reason": result.reason,
            "cycles": result.cycles,
            "decisions": result.decisions,
            "direct_actions": result.direct_actions,
            "agent_handoffs": result.agent_handoffs,
            "observations": result.observations,
            "fail_closed": result.fail_closed,
            "trace": [asdict(entry) for entry in result.trace],
        },
        "agent_triggers": harness.agent_triggers,
        "submit": harness.submit_payload,
        "cleanup": cleanup,
        "error_class": error_class,
    }


def _markdown_report(report: dict[str, Any]) -> str:
    rows = report["rows"]
    return (
        "# Workflow + Jev + Agent 混合链路零 Provider 资格报告\n\n"
        f"- 决定：`{report['decision']}`\n"
        f"- CMake / Make / Autotools 严格成功：`{sum(row['hybrid_result']['status'] == 'strict_success' for row in rows)}/3`\n"
        f"- Jev 直接动作：`{sum(row['hybrid_result']['direct_actions'] for row in rows)}`\n"
        f"- Agent handoff：`{sum(row['hybrid_result']['agent_handoffs'] for row in rows)}`\n"
        "- Provider / credential / formal attempt：`0 / 0 / 0`\n"
        f"- cleanup 后受管资源：`{report['managed_resources_after']}`\n\n"
        "该结果只证明限定 fixture 上的控制权交还、严格 submit、clean replay 和 cleanup 能够闭合；"
        "不证明自然失败上的成功率、成本收益、动态预算优势或开放世界泛化。\n"
    )


def execute() -> dict[str, Any]:
    manifest = _load_manifest()
    preflight_result = preflight()
    evidence_root = REPO_ROOT / manifest["evidence"]["root"]
    marker_path = evidence_root / "attempt.json"
    result_path = evidence_root / "result.json"
    _write_once_json(
        marker_path,
        {
            "identity": IDENTITY,
            "manifest_sha256": _manifest_sha256(manifest),
            "release_revision": preflight_result["release_revision"],
            "started_at": _now(),
            "status": "started",
        },
    )
    rows: list[dict[str, Any]] = []
    try:
        for sequence, case in enumerate(manifest["cases"], start=1):
            rows.append(asyncio.run(_run_case(manifest, case, sequence)))
        require_zero_managed_resources()
        gates = {
            "all_build_systems": {row["build_system"] for row in rows} == {"cmake", "make", "autotools"},
            "all_strict_success": all(row["hybrid_result"]["status"] == "strict_success" for row in rows),
            "all_clean_replay_passed": all(row["submit"].get("replay_status") == "passed" for row in rows),
            "all_cleanup_completed": all(row["cleanup"]["status"] == "completed" and row["cleanup"]["succeeded"] for row in rows),
            "direct_control_return_observed": sum(row["hybrid_result"]["direct_actions"] for row in rows) >= 2,
            "agent_control_return_observed": sum(row["hybrid_result"]["agent_handoffs"] for row in rows) >= 1,
            "zero_managed_resources": True,
            "zero_provider": True,
            "zero_credential_read": True,
            "zero_formal_attempt": True,
        }
        passed = all(gates.values())
        report = {
            "schema_version": "forge-jev-hybrid-workflow-qualification-1.0.0",
            "identity": IDENTITY,
            "manifest_sha256": _manifest_sha256(manifest),
            "created_at": _now(),
            "preflight": preflight_result,
            "rows": rows,
            "gates": gates,
            "passed": passed,
            "decision": "proceed_to_provider_canary_identity_freeze" if passed else "stop_and_repair_hybrid_workflow",
            "provider_calls": 0,
            "credential_reads": 0,
            "formal_attempts": 0,
            "managed_resources_after": 0,
            "interpretation": manifest["interpretation"],
        }
        _write_once_json(result_path, report)
        _write_once_json(REPORT_JSON_PATH, report)
        _write_once(REPORT_MARKDOWN_PATH, _markdown_report(report))
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker.update({"completed_at": _now(), "status": "completed", "result_sha256": _file_sha256(result_path)})
        _atomic_json(marker_path, marker)
        return report
    except Exception as exc:
        require_zero_managed_resources()
        failure = {
            "schema_version": "forge-jev-hybrid-workflow-qualification-failure-1.0.0",
            "identity": IDENTITY,
            "manifest_sha256": _manifest_sha256(manifest),
            "created_at": _now(),
            "preflight": preflight_result,
            "completed_rows": rows,
            "error_class": type(exc).__name__,
            "decision": "stop_and_repair_hybrid_workflow",
            "provider_calls": 0,
            "credential_reads": 0,
            "formal_attempts": 0,
            "managed_resources_after": 0,
        }
        _write_once_json(result_path, failure)
        _write_once_json(FAILURE_JSON_PATH, failure)
        _write_once(
            FAILURE_MARKDOWN_PATH,
            f"# Workflow + Jev + Agent 混合链路零 Provider 资格失败\n\n- 错误类别：`{type(exc).__name__}`\n- 决定：`stop_and_repair_hybrid_workflow`\n- Provider / credential / formal attempt：`0 / 0 / 0`\n",
        )
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker.update({"completed_at": _now(), "status": "failed", "error_class": type(exc).__name__, "result_sha256": _file_sha256(result_path)})
        _atomic_json(marker_path, marker)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "execute"))
    arguments = parser.parse_args()
    try:
        result = preflight(require_clean=False, require_absent_outputs=False) if arguments.command == "preflight" else execute()
    except QualificationError as exc:
        print(f"qualification error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
