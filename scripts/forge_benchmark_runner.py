#!/usr/bin/env python3
"""Evidence-first runner for the Forge C/C++ benchmark protocol.

The runner deliberately separates attempt creation from model execution. A
physical-attempt ledger must exist before ``run`` can issue a provider call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[1])).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(Path(__file__).resolve().parent)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_benchmark as protocol  # noqa: E402

from deerflow.compile.evidence import (  # noqa: E402
    EvidenceError,
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
)


class RunnerError(ValueError):
    pass


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_command(arguments: list[str], *, cwd: Path = REPO_ROOT) -> tuple[int, str]:
    try:
        result = subprocess.run(
            arguments,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return result.returncode, result.stdout.strip()


def _git_state(repo_root: Path) -> dict[str, Any]:
    revision_code, revision = _run_command(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
    )
    dirty_code, dirty_output = _run_command(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=repo_root,
    )
    return {
        "revision": revision if revision_code == 0 else None,
        "dirty": bool(dirty_output) if dirty_code == 0 else None,
    }


def _manifest_case(manifest: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in manifest["cases"]:
        if case["id"] == case_id:
            return case
    raise RunnerError(f"Unknown benchmark case: {case_id}")


def _manifest_condition(
    manifest: dict[str, Any],
    condition_id: str,
) -> dict[str, Any]:
    for condition in manifest["conditions"]:
        if condition["id"] == condition_id:
            return condition
    raise RunnerError(f"Unknown benchmark condition: {condition_id}")


def build_policy(
    manifest: dict[str, Any],
    *,
    case_id: str,
    condition_id: str,
    repetition: int,
) -> ExperimentPolicy:
    case = _manifest_case(manifest, case_id)
    condition = _manifest_condition(manifest, condition_id)
    model = manifest["model"]
    runtime = manifest["runtime"]
    constraints = case["constraints"]
    build_arguments = constraints["build_arguments"]
    lead_model = model["roles"]["lead"]
    compiler_model = model["roles"]["compiler"]
    if lead_model != compiler_model:
        raise RunnerError("The v1 runner requires one frozen model for both roles")
    if repetition > condition["repetitions"]:
        raise RunnerError("Repetition exceeds the manifest condition")
    return ExperimentPolicy(
        benchmark_id=manifest["benchmark"]["id"],
        manifest_sha256=protocol.manifest_sha256(manifest),
        case_id=case_id,
        condition=condition_id,
        repetition=repetition,
        expected_repo_url=case["repository_url"],
        expected_commit_sha=case["commit_sha"],
        compile_image=runtime["compile_image"],
        image_id=runtime["image_id"],
        model_name=lead_model,
        endpoint=model["endpoint"].rstrip("/"),
        credential_env=model["credential_env"],
        request_timeout_seconds=model["request_timeout_seconds"],
        model_max_retries=model["max_retries"],
        compiler_max_turns=runtime["compiler_max_turns"],
        subagent_timeout_seconds=runtime["subagent_timeout_seconds"],
        memory_enabled=condition["memory_enabled"],
        skills_enabled=condition["skills_enabled"],
        required_system_packages=tuple(constraints["required_system_packages"]),
        cmake_arguments=tuple(build_arguments["cmake"]),
        configure_arguments=tuple(build_arguments["configure"]),
        environment=tuple(constraints["environment"].items()),
        minimum_replay_delay_seconds=constraints["minimum_replay_delay_seconds"],
    )


def _endpoint_reachable(endpoint: str) -> bool:
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}/models",
        method="GET",
        headers={"User-Agent": "forge-benchmark-preflight/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            return True
    except urllib.error.HTTPError as exc:
        return 100 <= exc.code <= 599
    except (OSError, urllib.error.URLError):
        return False


def _credential_present(variable_name: str) -> bool:
    if variable_name in os.environ:
        return True
    code, container_ids = _run_command(
        [
            "docker",
            "ps",
            "-q",
            "--filter",
            "label=com.docker.compose.service=langgraph",
        ]
    )
    if code != 0:
        return False
    for container_id in container_ids.splitlines():
        exists_code, _ = _run_command(
            [
                "docker",
                "exec",
                container_id,
                "sh",
                "-c",
                f'test "${{{variable_name}+x}}" = x',
            ]
        )
        if exists_code == 0:
            return True
    return False


def collect_preflight(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    check_endpoint: bool = True,
) -> dict[str, Any]:
    forge_state = _git_state(repo_root)
    component_results: dict[str, dict[str, Any]] = {}
    for relative_path, expected_digest in manifest["forge"]["component_sha256"].items():
        actual_digest = _sha256_file(repo_root / relative_path)
        component_results[relative_path] = {
            "expected": expected_digest,
            "actual": actual_digest,
            "matches": actual_digest == expected_digest,
        }

    protocol_results: dict[str, dict[str, Any]] = {}
    for relative_path, expected_digest in manifest["protocol_artifact_sha256"].items():
        actual_digest = _sha256_file(repo_root / relative_path)
        protocol_results[relative_path] = {
            "expected": expected_digest,
            "actual": actual_digest,
            "matches": actual_digest == expected_digest,
        }

    runtime = manifest["runtime"]
    image_code, image_id = _run_command(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}",
            runtime["compile_image"],
        ],
        cwd=repo_root,
    )
    network_code, _ = _run_command(
        ["docker", "network", "inspect", runtime["network_policy"]["network_name"]],
        cwd=repo_root,
    )
    docker_version_code, docker_version = _run_command(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        cwd=repo_root,
    )
    model = manifest["model"]
    condition_baseline = all(not condition["memory_enabled"] and not condition["skills_enabled"] for condition in manifest["conditions"])
    endpoint_reachable = _endpoint_reachable(model["endpoint"]) if check_endpoint else None
    checks = {
        "credential_present": _credential_present(model["credential_env"]),
        "endpoint_reachable": endpoint_reachable,
        "forge_revision_matches": forge_state["revision"] == manifest["forge"]["commit_sha"],
        "forge_clean": forge_state["dirty"] is False,
        "forge_components_match": all(result["matches"] for result in component_results.values()),
        "protocol_artifacts_match": all(result["matches"] for result in protocol_results.values()),
        "image_present": image_code == 0,
        "image_id_matches": image_code == 0 and image_id == runtime["image_id"],
        "network_present": network_code == 0,
        "docker_server_matches": (docker_version_code == 0 and docker_version == runtime["host"]["docker_server_version"]),
        "single_process_serial": runtime["backend_processes"] == 1 and runtime["max_parallel_runs"] == 1,
        "fallback_forbidden": model["fallback_policy"] == "forbidden",
        "memory_skills_disabled": condition_baseline,
        "instrumentation_unblocked": not manifest["scope"]["instrumentation_blocker"],
    }
    required_checks = [
        checks["credential_present"],
        checks["forge_revision_matches"],
        checks["forge_clean"],
        checks["forge_components_match"],
        checks["protocol_artifacts_match"],
        checks["image_id_matches"],
        checks["network_present"],
        checks["single_process_serial"],
        checks["fallback_forbidden"],
        checks["memory_skills_disabled"],
        checks["instrumentation_unblocked"],
    ]
    if check_endpoint:
        required_checks.append(checks["endpoint_reachable"] is True)
    return {
        "ready": all(required_checks),
        "manifest_sha256": protocol.manifest_sha256(manifest),
        "manifest_file_sha256": _sha256_file(repo_root / "benchmarks" / "manifests" / "cpp-pilot-v1.json"),
        "forge": {
            **forge_state,
            "expected_revision": manifest["forge"]["commit_sha"],
            "components": component_results,
        },
        "protocol": protocol_results,
        "runtime": {
            "image_id": image_id if image_code == 0 else None,
            "docker_server_version": (docker_version if docker_version_code == 0 else None),
            "platform_system": platform.system(),
            "platform_machine": platform.machine(),
        },
        "checks": checks,
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    return protocol.validate_manifest(protocol.load_json_document(path))


def _slot_matches(
    events: list[dict[str, Any]],
    policy: ExperimentPolicy,
) -> bool:
    if not events:
        return False
    recorded = events[0]["payload"].get("policy")
    if not isinstance(recorded, dict):
        return False
    return all(
        recorded.get(key) == value
        for key, value in {
            "benchmark_id": policy.benchmark_id,
            "case_id": policy.case_id,
            "condition": policy.condition,
            "repetition": policy.repetition,
        }.items()
    )


def find_slot_ledgers(
    output_dir: Path,
    policy: ExperimentPolicy,
) -> list[tuple[Path, list[dict[str, Any]]]]:
    matches: list[tuple[Path, list[dict[str, Any]]]] = []
    if not output_dir.exists():
        return matches
    for ledger_path in sorted(output_dir.rglob("*.jsonl")):
        try:
            events = ExperimentLedger.verify_path(ledger_path)
        except EvidenceError:
            continue
        if _slot_matches(events, policy):
            matches.append((ledger_path, events))
    return matches


def create_attempt(
    manifest: dict[str, Any],
    *,
    case_id: str,
    condition_id: str,
    repetition: int,
    output_dir: Path,
    replacement_for: str | None = None,
    check_endpoint: bool = True,
    repo_root: Path = REPO_ROOT,
) -> tuple[ExperimentLedger, dict[str, Any]]:
    policy = build_policy(
        manifest,
        case_id=case_id,
        condition_id=condition_id,
        repetition=repetition,
    )
    existing = find_slot_ledgers(output_dir, policy)
    if existing and replacement_for is None:
        raise RunnerError("This benchmark slot already has physical evidence; create an explicit replacement attempt")
    replacement_event: dict[str, Any] | None = None
    if replacement_for is not None:
        replacement_event = next(
            (events[0] for _path, events in existing if events[0]["physical_attempt_id"] == replacement_for),
            None,
        )
        if replacement_event is None:
            raise RunnerError("The replacement attempt does not belong to this slot")

    preflight = collect_preflight(
        manifest,
        repo_root=repo_root,
        check_endpoint=check_endpoint,
    )
    experiment_id = replacement_event["experiment_id"] if replacement_event is not None else new_evidence_id("experiment")
    physical_attempt_id = new_evidence_id("physical_attempt")
    thread_id = new_evidence_id("thread")
    ledger_path = output_dir / policy.case_id / policy.condition / f"rep-{policy.repetition:03d}" / f"{physical_attempt_id}.jsonl"
    context = {
        "thread_id": thread_id,
        "replacement_for_physical_attempt_id": replacement_for,
        "policy": policy.to_payload(),
        "forge": preflight["forge"],
        "protocol": {
            "manifest_sha256": preflight["manifest_sha256"],
            "manifest_file_sha256": preflight["manifest_file_sha256"],
            "artifacts": preflight["protocol"],
        },
        "runtime": preflight["runtime"],
        "preflight_checks": preflight["checks"],
        "preflight_ready": preflight["ready"],
    }
    ledger = ExperimentLedger.create(
        ledger_path,
        experiment_id=experiment_id,
        physical_attempt_id=physical_attempt_id,
        context=context,
    )
    ledger.append(
        "preflight.completed",
        {
            "ready": preflight["ready"],
            "checks": preflight["checks"],
        },
    )
    return ledger, preflight


def recompute_gates(events: list[dict[str, Any]]) -> dict[str, Any]:
    commands: dict[str, dict[str, Any]] = {}
    replays: dict[str, dict[str, Any]] = {}
    deliveries: dict[str, dict[str, Any]] = {}
    submits: list[dict[str, Any]] = []
    for event in events:
        payload = event["payload"]
        if event["event"] == "command.completed":
            commands[payload["command_id"]] = payload
        elif event["event"] == "replay.completed":
            replays[payload["replay_attempt_id"]] = payload
        elif event["event"] == "delivery.completed":
            submit_id = payload.get("submit_attempt_id")
            if submit_id:
                deliveries[submit_id] = payload
        elif event["event"] == "submit.completed":
            submits.append(payload)

    results: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for submit in submits:
        supporting = commands.get(submit.get("supporting_command_id"))
        replay_snapshot = submit.get("replay") or {}
        replay = replays.get(replay_snapshot.get("replay_attempt_id"))
        checks = submit.get("checks") or []
        recomputed = {
            "exit_code": supporting is not None and supporting.get("role") == "build" and supporting.get("exit_code") == 0 and supporting.get("timed_out") is False,
            "candidate_only": submit.get("candidate_status") == "passed" and bool(submit.get("artifacts")) and all(check.get("passed") is True for check in checks),
            "replay_ready": bool(submit.get("recipe_sha256")) and bool(replay_snapshot.get("replay_attempt_id")),
            "clean_replay": replay is not None and replay.get("status") == "passed" and replay.get("cleanup_succeeded") is True and replay.get("primary_failure_classification") is None,
            "delivered": bool(deliveries.get(submit["submit_attempt_id"], {}).get("delivered")),
        }
        recorded = submit.get("gates") or {}
        for gate in ("exit_code", "candidate_only", "replay_ready", "clean_replay"):
            if recorded.get(gate) != recomputed[gate]:
                mismatches.append(
                    {
                        "submit_attempt_id": submit["submit_attempt_id"],
                        "gate": gate,
                        "recorded": recorded.get(gate),
                        "recomputed": recomputed[gate],
                    }
                )
        delivery = deliveries.get(submit["submit_attempt_id"])
        if delivery is not None and delivery.get("delivered") != recomputed["delivered"]:
            mismatches.append(
                {
                    "submit_attempt_id": submit["submit_attempt_id"],
                    "gate": "delivered",
                    "recorded": delivery.get("delivered"),
                    "recomputed": recomputed["delivered"],
                }
            )
        results.append(
            {
                "submit_attempt_id": submit["submit_attempt_id"],
                "gates": recomputed,
            }
        )
    return {"valid": not mismatches, "submits": results, "mismatches": mismatches}


def run_oracle(
    manifest: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    started = events[0]["payload"]
    case = _manifest_case(manifest, started["policy"]["case_id"])
    submits = [event["payload"] for event in events if event["event"] == "submit.completed"]
    if not submits:
        return {"passed": False, "classification": "submit_missing"}
    submit = submits[-1]
    expected_artifacts = {(artifact["relative_path"], artifact["artifact_type"]) for artifact in case["oracle"]["required_artifacts"]}
    actual_artifacts = {(artifact.get("path"), artifact.get("artifact_type")) for artifact in submit.get("artifacts", [])}
    replay = submit.get("replay") or {}
    expected_candidate_pass = case["oracle"]["expected_candidate_status"] == "pass"
    expected_replay_pass = case["oracle"]["expected_clean_replay_status"] == "pass"
    candidate_pass = submit.get("candidate_status") == "passed"
    replay_pass = replay.get("status") == "passed"
    expected_failure = case["oracle"].get("expected_replay_failure_classification")
    actual_failure = replay.get("primary_failure_classification")
    failure_matches = expected_failure is None or actual_failure == expected_failure
    passed = expected_artifacts.issubset(actual_artifacts) and candidate_pass == expected_candidate_pass and replay_pass == expected_replay_pass and failure_matches
    return {
        "passed": passed,
        "classification": None if passed else "oracle_mismatch",
        "submit_attempt_id": submit["submit_attempt_id"],
        "artifact_oracle_passed": expected_artifacts.issubset(actual_artifacts),
        "candidate_expectation_passed": candidate_pass == expected_candidate_pass,
        "replay_expectation_passed": replay_pass == expected_replay_pass,
        "failure_classification_expectation_passed": failure_matches,
    }


def reconcile_orphans(physical_attempt_id: str) -> dict[str, Any]:
    code, output = _run_command(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            (f"label=deerflow.compile.physical_attempt_id={physical_attempt_id}"),
        ]
    )
    identifiers = output.splitlines() if code == 0 and output else []
    removed = 0
    for identifier in identifiers:
        remove_code, _ = _run_command(["docker", "rm", "-f", identifier])
        if remove_code == 0:
            removed += 1
    return {
        "scan_succeeded": code == 0,
        "orphan_count": len(identifiers),
        "removed_count": removed,
        "cleanup_succeeded": code == 0 and removed == len(identifiers),
    }


def run_attempt(
    manifest: dict[str, Any],
    ledger_path: Path,
) -> dict[str, Any]:
    ledger = ExperimentLedger.open(ledger_path)
    events = ledger.read()
    context = events[0]["payload"]
    if context.get("preflight_ready") is not True:
        raise RunnerError("The physical attempt did not pass preflight")
    if any(event["event"].startswith("model.") for event in events):
        raise RunnerError("A physical attempt cannot issue model calls twice")
    policy_data = context["policy"]
    policy = build_policy(
        manifest,
        case_id=policy_data["case_id"],
        condition_id=policy_data["condition"],
        repetition=policy_data["repetition"],
    )
    if policy.to_payload() != policy_data:
        raise RunnerError("The ledger policy no longer matches the manifest")
    thread_id = context["thread_id"]
    activate_experiment(
        thread_id=thread_id,
        experiment_id=ledger.experiment_id,
        physical_attempt_id=ledger.physical_attempt_id,
        ledger=ledger,
        policy=policy,
    )
    run_status = "failed"
    try:
        from deerflow.client import DeerFlowClient

        client = DeerFlowClient(
            model_name=policy.model_name,
            thinking_enabled=False,
            subagent_enabled=True,
            plan_mode=False,
            available_skills=set(),
        )
        message = f"Compile the C/C++ repository at {policy.expected_repo_url} using exact commit {policy.expected_commit_sha}. Use the compiler subagent and finish only after deterministic artifact submission and session finalization."
        for _event in client.stream(message, thread_id=thread_id):
            pass
        run_status = "completed"
    except BaseException as exc:
        ledger.append(
            "run.failed",
            {
                "failure_id": new_evidence_id("failure"),
                "classification": type(exc).__name__,
            },
        )
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        deactivate_experiment(thread_id)
        reconciliation = reconcile_orphans(ledger.physical_attempt_id)
        ledger.append("orphan.reconciled", reconciliation)

    events = ledger.read()
    gates = recompute_gates(events)
    oracle = run_oracle(manifest, events)
    ledger.append("oracle.completed", oracle)
    final_status = "passed" if run_status == "completed" and gates["valid"] and oracle["passed"] and reconciliation["cleanup_succeeded"] else "failed"
    ledger.append(
        "experiment.completed",
        {
            "status": final_status,
            "gate_recomputation_valid": gates["valid"],
            "oracle_passed": oracle["passed"],
            "orphan_cleanup_succeeded": reconciliation["cleanup_succeeded"],
        },
    )
    return {
        "status": final_status,
        "gate_recomputation": gates,
        "oracle": oracle,
        "orphan_reconciliation": reconciliation,
    }


def _json_print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v1.json",
    )
    common.add_argument("--skip-endpoint-check", action="store_true")

    subparsers.add_parser("preflight", parents=[common])
    create = subparsers.add_parser("create-attempt", parents=[common])
    create.add_argument("--case", required=True)
    create.add_argument("--condition", default="baseline")
    create.add_argument("--repetition", type=int, default=1)
    create.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "evidence",
    )
    create.add_argument("--replacement-for")

    verify = subparsers.add_parser("verify-ledger", parents=[common])
    verify.add_argument("--ledger", type=Path, required=True)
    run = subparsers.add_parser("run", parents=[common])
    run.add_argument("--ledger", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        manifest = _load_manifest(args.manifest)
        if args.command == "preflight":
            result = collect_preflight(
                manifest,
                check_endpoint=not args.skip_endpoint_check,
            )
            _json_print(result)
            return 0 if result["ready"] else 2
        if args.command == "create-attempt":
            ledger, preflight = create_attempt(
                manifest,
                case_id=args.case,
                condition_id=args.condition,
                repetition=args.repetition,
                output_dir=args.output_dir,
                replacement_for=args.replacement_for,
                check_endpoint=not args.skip_endpoint_check,
            )
            _json_print(
                {
                    "created": True,
                    "ledger": str(ledger.path),
                    "physical_attempt_id": ledger.physical_attempt_id,
                    "preflight_ready": preflight["ready"],
                }
            )
            return 0
        if args.command == "verify-ledger":
            events = ExperimentLedger.verify_path(args.ledger)
            gates = recompute_gates(events)
            oracle = run_oracle(manifest, events)
            result = {
                "ledger_valid": True,
                "gate_recomputation": gates,
                "oracle": oracle,
            }
            _json_print(result)
            return 0 if gates["valid"] else 2
        if args.command == "run":
            result = run_attempt(manifest, args.ledger)
            _json_print(result)
            return 0 if result["status"] == "passed" else 2
    except (EvidenceError, RunnerError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
