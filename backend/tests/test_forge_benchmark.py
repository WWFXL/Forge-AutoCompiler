from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_benchmark.py"
SPEC = importlib.util.spec_from_file_location("forge_benchmark", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
forge_benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge_benchmark)

IMAGE_ID = f"sha256:{'9' * 64}"
CASE_COMMIT = "1" * 40
SECRET_SENTINEL = "OPENAI_AK_VALUE_DO_NOT_PERSIST"
HOST_PATH_SENTINEL = "C:\\Users\\YiWei\\private-build"


def make_manifest() -> dict:
    cases = []
    case_specs = (
        ("fmt", "https://github.com/fmtlib/fmt.git", CASE_COMMIT, ["C++"], "cmake", "pass", "pass"),
        ("hiredis", "https://github.com/redis/hiredis.git", "2" * 40, ["C"], "make", "pass", "pass"),
        ("check", "https://github.com/libcheck/check.git", "3" * 40, ["C"], "autotools", "pass", "pass"),
        ("libgit2", "https://github.com/libgit2/libgit2.git", "4" * 40, ["C"], "cmake", "pass", "pass"),
        ("sysstat-negative", "https://github.com/sysstat/sysstat.git", "5" * 40, ["C"], "autotools", "pass", "reject"),
    )
    for case_id, repository_url, commit_sha, languages, build_system, candidate_status, replay_status in case_specs:
        environment = (
            {
                "CFLAGS": "-O2 -DUSE_SCCSID",
                "SOURCE_DATE_EPOCH": None,
            }
            if case_id == "sysstat-negative"
            else {}
        )
        cases.append(
            {
                "id": case_id,
                "repository_url": repository_url,
                "commit_sha": commit_sha,
                "languages": languages,
                "build_system": build_system,
                "license": "MIT",
                "oracle": {
                    "expected_candidate_status": candidate_status,
                    "expected_clean_replay_status": replay_status,
                    "required_artifacts": [{"relative_path": "build/output", "artifact_type": "static_library"}],
                },
                "constraints": {
                    "required_system_packages": [],
                    "build_arguments": {"cmake": [], "configure": []},
                    "environment": environment,
                    "minimum_replay_delay_seconds": 0,
                },
            }
        )
    return {
        "schema_version": "1.0.0",
        "document_type": "manifest",
        "manifest_canonicalization": "json-sort-keys-compact-utf8",
        "benchmark": {
            "id": "forge-cpp-pilot-v1",
            "name": "Forge C/C++ pilot",
            "purpose": "clean_replay_collection_calibration",
            "dataset_provenance": "self_selected_calibration_set",
        },
        "scope": {"languages": ["C", "C++"], "phase": "pilot", "formal_comparison_enabled": False, "instrumentation_blocker": True},
        "forge": {
            "repository_url": "https://github.com/WWFXL/Forge-AutoCompiler.git",
            "commit_sha": "a" * 40,
            "component_sha256": {
                "backend/packages/harness/deerflow/subagents/builtins/compiler_agent.py": "1" * 64,
                "backend/packages/harness/deerflow/agents/lead_agent/prompt.py": "2" * 64,
                "backend/packages/harness/deerflow/tools/bound_compile_tools.py": "3" * 64,
                "backend/packages/harness/deerflow/tools/builtins/agent_compile_tools.py": "4" * 64,
                "docker/compile/Dockerfile": "c" * 64,
                "config.example.yaml": "5" * 64,
                "backend/uv.lock": "6" * 64,
            },
        },
        "protocol_artifact_sha256": {
            "scripts/forge_benchmark.py": "7" * 64,
            "benchmarks/schemas/forge-cpp-benchmark-v1.schema.json": "8" * 64,
        },
        "model": {
            "endpoint": "https://richlab-api-x.choosefire.com/v1",
            "credential_env": "OpenAI_AK",
            "fallback_policy": "forbidden",
            "roles": {"lead": "gpt-5.6-sol", "compiler": "gpt-5.6-sol"},
            "request_timeout_seconds": 600,
            "max_retries": 0,
        },
        "runtime": {
            "compile_image": "autocompiler:gcc13",
            "image_id": IMAGE_ID,
            "replay_timeout_seconds": 1200,
            "cleanup_timeout_seconds": 30,
            "docker_control_timeout_seconds": 30,
            "compiler_max_turns": 36,
            "subagent_timeout_seconds": 1800,
            "max_parallel_runs": 1,
            "backend_processes": 1,
            "network_policy": {"network_name": "compile_network_wwf_v1", "egress": "enabled_for_clone_and_dependencies"},
            "host": {
                "wsl_distribution": "Ubuntu",
                "cpu_count": 32,
                "memory_kib": 7723024,
                "kernel": "6.6.114.1-microsoft-standard-WSL2",
                "architecture": "x86_64",
                "docker_server_version": "29.5.3",
            },
        },
        "conditions": [
            {
                "id": "baseline",
                "memory_enabled": False,
                "skills_enabled": False,
                "repetitions": 3,
                "acceptance_gate": "clean_replay",
            }
        ],
        "cases": cases,
    }


def make_session(*, status: str = "completed") -> dict:
    return {
        "session_id": "abcdef123456",
        "thread_id": "thread-value-is-not-recorded",
        "run_id": "123e4567-e89b-12d3-a456-426614174000",
        "repo_url": "https://github.com/fmtlib/fmt",
        "commit_sha": CASE_COMMIT,
        "image": "autocompiler:gcc13",
        "image_id": IMAGE_ID,
        "status": status,
        "build_system": "cmake",
        "created_at": "2026-07-17T00:00:00+00:00",
        "completed_at": "2026-07-17T00:02:00+00:00" if status == "completed" else None,
        "finalized_at": "2026-07-17T00:02:00+00:00" if status == "completed" else None,
        "summary": f"raw model output with {SECRET_SENTINEL}",
        "error": f"failed under {HOST_PATH_SENTINEL}",
        "metadata_path": f"{HOST_PATH_SENTINEL}\\session.json",
        "leadagent_repo_dir": f"{HOST_PATH_SENTINEL}\\workspace\\repo",
        "commands": [
            {
                "stage": "clone",
                "command": f"git clone https://token:{SECRET_SENTINEL}@example.invalid/repo",
                "workdir": "/workspace",
                "exit_code": 0,
                "log_path": f"{HOST_PATH_SENTINEL}\\001_clone.log",
            },
            {
                "stage": "bash",
                "command": f"cmake -S . -B {HOST_PATH_SENTINEL}",
                "workdir": "/workspace/repo",
                "exit_code": 0,
            },
            {
                "stage": "bash",
                "command": f"echo {SECRET_SENTINEL}",
                "workdir": "/workspace/repo",
                "exit_code": 2,
            },
        ],
        "artifacts": [
            {
                "path": f"{HOST_PATH_SENTINEL}\\artifacts\\fmt",
                "source_path": "/artifacts/lib/libfmt.a",
                "artifact_type": "static_library",
                "size_bytes": 4096,
                "sha256": "d" * 64,
                "smoke_command": None,
                "smoke_exit_code": None,
                "smoke_output": SECRET_SENTINEL,
                "smoke_output_sha256": None,
            }
        ],
        "verification": {
            "status": "passed",
            "artifact_count": 1,
            "failed_checks": 0,
            "notes": [SECRET_SENTINEL, HOST_PATH_SENTINEL],
        },
        "replay_attempts": [
            {
                "attempt_id": "123456abcdef",
                "image": "autocompiler:gcc13",
                "image_id": IMAGE_ID,
                "commit_sha": CASE_COMMIT,
                "status": "passed",
                "failure_classification": None,
                "exit_code": 0,
                "cleanup_succeeded": True,
                "duration_seconds": 32.5,
                "timeout_seconds": 1200,
                "recipe_sha256": "e" * 64,
                "log_path": f"{HOST_PATH_SENTINEL}\\replay.log",
                "notes": [SECRET_SENTINEL],
            }
        ],
    }


def completed_events() -> list[dict]:
    return [
        {"event": "session.created", "session_id": "abcdef123456", "metadata_path": HOST_PATH_SENTINEL},
        {"event": "submit.started", "session_id": "abcdef123456", "log_path": HOST_PATH_SENTINEL},
        {
            "event": "submit.completed",
            "session_id": "abcdef123456",
            "status": "passed",
            "artifact_count": 1,
            "failed_checks": 0,
            "candidate_status": "passed",
            "replay_status": "passed",
            "replay_attempt_id": "123456abcdef",
            "raw_output": SECRET_SENTINEL,
        },
    ]


def build_record(*, manifest: dict | None = None, session: dict | None = None, events: list[dict] | None = None) -> dict:
    return forge_benchmark.build_run_record(
        manifest=manifest or make_manifest(),
        case_id="fmt",
        condition_id="baseline",
        repetition=1,
        session=session or make_session(),
        workflow_events=completed_events() if events is None else events,
    )


def freeze_manifest_for_repo(manifest: dict, repo_root: Path = REPO_ROOT) -> dict:
    hash_groups = (
        manifest["forge"]["component_sha256"],
        manifest["protocol_artifact_sha256"],
    )
    for hashes in hash_groups:
        for relative_path in hashes:
            hashes[relative_path] = hashlib.sha256((repo_root / relative_path).read_bytes()).hexdigest()
    return manifest


def test_fixture_manifest_validates_and_hash_is_canonical() -> None:
    manifest = make_manifest()
    assert forge_benchmark.validate_manifest(manifest) is manifest
    assert len({case["id"] for case in manifest["cases"]}) == 5
    compact_hash = forge_benchmark.manifest_sha256(manifest)
    reparsed = json.loads(json.dumps(manifest, indent=4, ensure_ascii=False))
    assert forge_benchmark.manifest_sha256(reparsed) == compact_hash


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda manifest: manifest.update(schema_version="2.0.0"), "unsupported version"),
        (lambda manifest: manifest["cases"][0].update(commit_sha="main"), "movable ref"),
        (lambda manifest: manifest["cases"][0].update(repository_url="https://user:password@github.com/fmtlib/fmt.git"), "credentials"),
        (lambda manifest: manifest["cases"][1].update(id="fmt"), "duplicate case ID"),
        (lambda manifest: manifest["cases"][0].update(languages=["Python"]), "C and/or C++"),
        (lambda manifest: manifest["forge"].update(component_sha256={}), "seven required frozen component"),
        (lambda manifest: manifest["cases"][0]["oracle"].update(expected_clean_replay_status="maybe"), "pass' or 'reject"),
        (lambda manifest: manifest["cases"][0]["constraints"]["environment"].update(OpenAI_AK="forbidden"), "may contain only"),
        (lambda manifest: manifest["model"]["roles"].update(compiler="gpt-5.4"), "must use the same model"),
        (lambda manifest: manifest["scope"].update(languages=[{}]), "exactly C and C\\+\\+"),
        (lambda manifest: manifest["cases"][0].update(languages=[{}]), "C and/or C\\+\\+"),
        (
            lambda manifest: manifest["cases"][0]["constraints"].update(required_system_packages=[{}]),
            "package names",
        ),
    ],
)
def test_manifest_rejects_invalid_protocol(mutate, message: str) -> None:
    manifest = make_manifest()
    mutate(manifest)
    with pytest.raises(forge_benchmark.BenchmarkError, match=message):
        forge_benchmark.validate_manifest(manifest)


def test_happy_record_extracts_only_bounded_evidence() -> None:
    record = build_record()

    assert record["outcome"] == {
        "session_status": "completed",
        "submit_status": "completed",
        "candidate_status": "pass",
        "clean_replay_status": "pass",
        "replay_failure_classification": None,
        "replay_cleanup_succeeded": True,
        "verification_status": "passed",
        "artifact_count": 1,
        "finalized": True,
        "oracle_match": None,
    }
    assert record["failure_attribution"] == {
        "model_endpoint": None,
        "agent": None,
        "build": None,
        "candidate_generation": False,
        "clean_replay": False,
        "cleanup": False,
        "completion": False,
    }
    assert record["evidence"]["command_summary"] == {"total": 3, "successful_bash": 1, "failed_bash": 1}
    assert record["evidence"]["artifacts"] == [
        {
            "relative_path": "lib/libfmt.a",
            "artifact_type": "static_library",
            "size_bytes": 4096,
            "sha256": "d" * 64,
            "smoke_exit_code": None,
            "smoke_output_sha256": None,
        }
    ]
    assert record["evidence"]["session_duration_seconds"] == 120.0


def test_failed_submit_records_candidate_rejection_without_inventing_build_or_endpoint_failure() -> None:
    session = make_session(status="verification_failed")
    session["completed_at"] = None
    session["finalized_at"] = None
    session["verification"] = {"status": "failed", "artifact_count": 0, "failed_checks": 1}
    session["artifacts"] = []
    session["replay_attempts"] = []
    events = [
        {
            "event": "submit.completed",
            "session_id": "abcdef123456",
            "status": "failed",
            "artifact_count": 0,
            "failed_checks": 1,
            "candidate_status": "failed",
            "replay_status": "not_run",
            "replay_attempt_id": None,
            "message": SECRET_SENTINEL,
        }
    ]

    record = build_record(session=session, events=events)

    assert record["outcome"]["candidate_status"] == "reject"
    assert record["outcome"]["clean_replay_status"] is None
    assert record["failure_attribution"]["candidate_generation"] is True
    assert record["failure_attribution"]["model_endpoint"] is None
    assert record["failure_attribution"]["agent"] is None
    assert record["failure_attribution"]["build"] is None


def test_passed_replay_requires_complete_linked_evidence() -> None:
    session = make_session()
    session["replay_attempts"][0]["recipe_sha256"] = None

    with pytest.raises(forge_benchmark.BenchmarkError, match="passed replay evidence is incomplete"):
        build_record(session=session)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("image", None, "missing frozen image or commit identity"),
        ("image_id", f"sha256:{'8' * 64}", "does not match the frozen manifest"),
        ("commit_sha", "f" * 40, "does not match the frozen manifest"),
        ("timeout_seconds", 1199, "does not match the frozen manifest"),
    ],
)
def test_passed_replay_requires_matching_frozen_identity_and_timeout(field: str, value, message: str) -> None:
    session = make_session()
    session["replay_attempts"][0][field] = value

    with pytest.raises(forge_benchmark.BenchmarkError, match=message):
        build_record(session=session)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("image", "autocompiler:gcc12"),
        ("image_id", f"sha256:{'8' * 64}"),
        ("commit_sha", "f" * 40),
        ("timeout_seconds", 1199),
    ],
)
def test_rejected_replay_rejects_observed_frozen_identity_mismatch(field: str, value) -> None:
    session = make_session(status="verification_failed")
    session["verification"].update(status="failed", failed_checks=1)
    session["replay_attempts"][0].update(status="failed", failure_classification="sha256_mismatch")
    session["replay_attempts"][0][field] = value
    events = [
        {
            "event": "submit.completed",
            "session_id": "abcdef123456",
            "status": "failed",
            "artifact_count": 1,
            "failed_checks": 1,
            "candidate_status": "passed",
            "replay_status": "failed",
            "replay_attempt_id": "123456abcdef",
        }
    ]

    with pytest.raises(forge_benchmark.BenchmarkError, match="frozen manifest"):
        build_record(session=session, events=events)


def test_image_identity_unavailable_preserves_null_image_id_rejection() -> None:
    session = make_session(status="verification_failed")
    session["image_id"] = None
    session["verification"].update(status="failed", failed_checks=1)
    session["replay_attempts"][0].update(
        image_id=None,
        status="failed",
        failure_classification="image_identity_unavailable",
        exit_code=None,
    )
    events = [
        {
            "event": "submit.completed",
            "session_id": "abcdef123456",
            "status": "failed",
            "artifact_count": 1,
            "failed_checks": 1,
            "candidate_status": "passed",
            "replay_status": "failed",
            "replay_attempt_id": "123456abcdef",
        }
    ]

    record = build_record(session=session, events=events)

    assert record["source"]["image_id"] is None
    assert record["outcome"]["clean_replay_status"] == "reject"
    assert record["outcome"]["replay_failure_classification"] == "image_identity_unavailable"
    assert record["evidence"]["replay_attempt"]["image_id"] is None


def test_cleanup_failure_is_not_misattributed_to_clean_replay_body() -> None:
    session = make_session(status="verification_failed")
    session["completed_at"] = None
    session["finalized_at"] = None
    session["verification"]["status"] = "failed"
    session["verification"]["failed_checks"] = 1
    session["replay_attempts"][0].update(status="failed", failure_classification="cleanup_failed", cleanup_succeeded=False)
    events = [
        {
            "event": "submit.completed",
            "session_id": "abcdef123456",
            "status": "failed",
            "artifact_count": 1,
            "failed_checks": 1,
            "candidate_status": "passed",
            "replay_status": "failed",
            "replay_attempt_id": "123456abcdef",
        }
    ]

    record = build_record(session=session, events=events)

    assert record["outcome"]["clean_replay_status"] == "reject"
    assert record["failure_attribution"]["clean_replay"] is None
    assert record["failure_attribution"]["cleanup"] is True
    assert record["failure_attribution"]["completion"] is None


def test_candidate_pass_requires_complete_artifact_snapshot() -> None:
    session = make_session(status="verification_failed")
    session["completed_at"] = None
    session["finalized_at"] = None
    session["verification"]["status"] = "failed"
    session["verification"]["artifact_count"] = 0
    session["verification"]["failed_checks"] = 1
    session["artifacts"] = []
    session["replay_attempts"][0].update(status="failed", failure_classification="sha256_mismatch")
    events = [
        {
            "event": "submit.completed",
            "session_id": "abcdef123456",
            "status": "failed",
            "artifact_count": 0,
            "failed_checks": 1,
            "candidate_status": "passed",
            "replay_status": "failed",
            "replay_attempt_id": "123456abcdef",
        }
    ]

    with pytest.raises(forge_benchmark.BenchmarkError, match="candidate pass requires"):
        build_record(session=session, events=events)


def test_no_submit_does_not_turn_successful_bash_into_an_acceptance_decision() -> None:
    session = make_session(status="failed")
    session["completed_at"] = "2026-07-17T00:01:00+00:00"
    session["finalized_at"] = "2026-07-17T00:01:00+00:00"

    record = build_record(session=session, events=[{"event": "session.status_changed", "session_id": "abcdef123456", "status": "failed"}])

    assert record["outcome"]["submit_status"] == "not_observed"
    assert record["outcome"]["candidate_status"] is None
    assert record["outcome"]["clean_replay_status"] is None
    assert record["outcome"]["artifact_count"] is None
    assert record["evidence"]["artifacts"] is None
    assert record["failure_attribution"]["build"] is None
    assert record["failure_attribution"]["completion"] is None
    assert record["evidence"]["command_summary"]["successful_bash"] == 1


def test_started_submit_is_preserved_without_inventing_an_outcome() -> None:
    session = make_session(status="inspected")
    record = build_record(
        session=session,
        events=[
            {
                "event": "submit.started",
                "session_id": "abcdef123456",
                "log_path": HOST_PATH_SENTINEL,
            }
        ],
    )

    assert record["outcome"]["submit_status"] == "started"
    assert record["outcome"]["candidate_status"] is None
    assert record["outcome"]["clean_replay_status"] is None
    assert record["evidence"]["submit_event"] == {
        "event": "submit.started",
        "stage": None,
        "status": None,
        "artifact_count": None,
        "failed_checks": None,
        "candidate_status": None,
        "replay_status": None,
        "replay_attempt_id": None,
    }
    assert record["evidence"]["replay_attempt"] is None
    assert record["evidence"]["artifacts"] is None


def test_started_submit_does_not_reuse_an_older_completion_event() -> None:
    session = make_session(status="inspected")
    events = completed_events()
    events.extend(
        [
            {
                "event": "artifact.finalization_recheck",
                "session_id": "abcdef123456",
                "passed": False,
            },
            {"event": "submit.started", "session_id": "abcdef123456"},
        ]
    )

    record = build_record(session=session, events=events)

    assert record["outcome"]["submit_status"] == "started"
    assert record["evidence"]["completion_event"] is None
    assert record["failure_attribution"]["completion"] is None


def test_workflow_events_require_a_matching_session_id(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.log"
    workflow_path.write_text('{"event":"submit.started"}\n', encoding="utf-8")

    with pytest.raises(forge_benchmark.BenchmarkError, match="must be present"):
        forge_benchmark._load_workflow_events(workflow_path, "abcdef123456")


def test_early_failure_allows_unobserved_commit_and_image_identity() -> None:
    session = make_session(status="failed")
    session.update(commit_sha=None, image=None, image_id=None)

    record = build_record(session=session, events=[])

    assert record["source"]["commit_sha"] is None
    assert record["source"]["image_id"] is None
    assert record["outcome"]["submit_status"] == "not_observed"


def test_explicit_post_submit_completion_failure_is_attributed() -> None:
    session = make_session(status="failed")
    session["verification"]["status"] = "failed"
    session["verification"]["failed_checks"] = 1
    events = completed_events()
    events.append(
        {
            "event": "artifact.finalization_recheck",
            "session_id": "abcdef123456",
            "passed": False,
            "details": SECRET_SENTINEL,
        }
    )

    record = build_record(session=session, events=events)

    assert record["outcome"]["candidate_status"] == "pass"
    assert record["outcome"]["clean_replay_status"] == "pass"
    assert record["outcome"]["verification_status"] == "failed"
    assert record["failure_attribution"]["completion"] is True
    assert record["evidence"]["completion_event"] == {
        "event": "artifact.finalization_recheck",
        "reason": None,
        "passed": False,
    }


def test_finalize_deferred_cleanup_failure_is_bounded_completion_evidence() -> None:
    session = make_session(status="failed")
    events = completed_events()
    events.append(
        {
            "event": "finalize.deferred",
            "session_id": "abcdef123456",
            "reason": "container_cleanup_failed",
            "error": SECRET_SENTINEL,
        }
    )

    record = build_record(session=session, events=events)

    assert record["failure_attribution"]["completion"] is True
    assert record["evidence"]["completion_event"] == {
        "event": "finalize.deferred",
        "reason": "container_cleanup_failed",
        "passed": None,
    }


def test_pre_submit_finalize_deferred_is_preserved_and_attributed() -> None:
    session = make_session(status="failed")
    events = [
        {
            "event": "finalize.deferred",
            "session_id": "abcdef123456",
            "reason": "container_cleanup_failed",
            "error": SECRET_SENTINEL,
        }
    ]

    record = build_record(session=session, events=events)

    assert record["outcome"]["submit_status"] == "not_observed"
    assert record["failure_attribution"]["completion"] is True
    assert record["evidence"]["completion_event"] == {
        "event": "finalize.deferred",
        "reason": "container_cleanup_failed",
        "passed": None,
    }


def test_finalize_completed_preserves_interruption_after_replay_pass() -> None:
    session = make_session(status="cancelled")
    session["finalized_at"] = "2026-07-17T00:02:00+00:00"
    events = completed_events()
    events.append(
        {
            "event": "finalize.completed",
            "session_id": "abcdef123456",
            "status": "cancelled",
            "summary": SECRET_SENTINEL,
            "finalized_at": "2026-07-17T00:02:00+00:00",
        }
    )

    record = build_record(session=session, events=events)

    assert record["outcome"]["candidate_status"] == "pass"
    assert record["outcome"]["clean_replay_status"] == "pass"
    assert record["outcome"]["session_status"] == "cancelled"
    assert record["outcome"]["finalized"] is True
    assert record["failure_attribution"]["completion"] is None
    assert record["evidence"]["completion_event"] == {
        "event": "finalize.completed",
        "reason": "cancelled",
        "passed": None,
    }


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"failed_checks": 1}, "passed status is inconsistent"),
        (
            {"status": "failed", "replay_status": "failed", "failed_checks": 0},
            "failed status is inconsistent",
        ),
        (
            {
                "status": "failed",
                "candidate_status": "failed",
                "replay_status": "failed",
                "failed_checks": 1,
            },
            "candidate rejection must not claim",
        ),
        (
            {
                "status": "failed",
                "candidate_status": "passed",
                "replay_status": "not_run",
                "replay_attempt_id": None,
                "failed_checks": 1,
            },
            "candidate pass requires a terminal clean replay",
        ),
        ({"artifact_count": 0}, "passed status is inconsistent"),
    ],
)
def test_completed_submit_rejects_inconsistent_cross_field_combinations(updates: dict, message: str) -> None:
    events = completed_events()
    events[-1].update(updates)

    with pytest.raises(forge_benchmark.BenchmarkError, match=message):
        build_record(events=events)


def test_missing_commands_produce_null_command_summary() -> None:
    session = make_session()
    session["commands"] = None

    record = build_record(session=session)

    assert record["evidence"]["command_summary"] is None


def test_boolean_exit_code_is_not_counted_as_success() -> None:
    session = make_session()
    session["commands"] = [{"stage": "bash", "exit_code": False}]

    record = build_record(session=session)

    assert record["evidence"]["command_summary"] == {
        "total": 1,
        "successful_bash": 0,
        "failed_bash": 0,
    }


def test_aborted_submit_is_explicit_and_does_not_reuse_stale_session_verification() -> None:
    session = make_session(status="cancelled")
    events = [
        {"event": "submit.completed", "session_id": "abcdef123456", "candidate_status": "passed", "replay_status": "passed", "replay_attempt_id": "123456abcdef"},
        {"event": "submit.aborted", "session_id": "abcdef123456", "stage": "final_checkpoint", "status": "cancelled", "error": SECRET_SENTINEL},
    ]

    record = build_record(session=session, events=events)

    assert record["outcome"]["submit_status"] == "aborted"
    assert record["outcome"]["candidate_status"] is None
    assert record["outcome"]["clean_replay_status"] is None
    assert record["outcome"]["verification_status"] is None
    assert record["evidence"]["submit_event"]["event"] == "submit.aborted"
    assert record["evidence"]["replay_attempt"] is None
    assert record["evidence"]["artifacts"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("repo_url", "https://github.com/other/project.git"),
        ("commit_sha", "f" * 40),
        ("image_id", f"sha256:{'8' * 64}"),
    ],
)
def test_record_rejects_session_identity_mismatch(field: str, value: str) -> None:
    session = make_session()
    session[field] = value
    with pytest.raises(forge_benchmark.BenchmarkError, match="does not match"):
        build_record(session=session)


def test_record_rejects_build_system_mismatch() -> None:
    session = make_session()
    session["build_system"] = "make"

    with pytest.raises(forge_benchmark.BenchmarkError, match="build_system"):
        build_record(session=session)


def test_completed_session_requires_finalization_evidence() -> None:
    session = make_session()
    session["finalized_at"] = None

    with pytest.raises(forge_benchmark.BenchmarkError, match="completed requires"):
        build_record(session=session)


def test_record_never_contains_raw_secret_error_command_or_host_path() -> None:
    serialized = json.dumps(build_record(), ensure_ascii=False)
    assert SECRET_SENTINEL not in serialized
    assert HOST_PATH_SENTINEL not in serialized
    assert "raw model output" not in serialized
    assert "cmake -S" not in serialized


def test_overlong_run_id_is_normalized_to_null() -> None:
    session = make_session()
    session["run_id"] = "a" * 161

    assert build_record(session=session)["source"]["run_id"] is None


def test_overlong_artifact_relative_path_cannot_support_candidate_pass() -> None:
    session = make_session()
    session["artifacts"][0]["source_path"] = f"/artifacts/{'a' * 513}"

    with pytest.raises(forge_benchmark.BenchmarkError, match="candidate pass requires"):
        build_record(session=session)


def test_more_than_one_thousand_artifacts_is_rejected() -> None:
    session = make_session()
    session["artifacts"] = session["artifacts"] * 1001

    with pytest.raises(forge_benchmark.BenchmarkError, match="more than 1000"):
        build_record(session=session)


def test_append_rejects_duplicate_slot_before_second_write(tmp_path: Path) -> None:
    output = tmp_path / "runs.jsonl"
    record = build_record()
    forge_benchmark.append_run_record(output, record)
    first_bytes = output.read_bytes()

    with pytest.raises(forge_benchmark.BenchmarkError, match="duplicate"):
        forge_benchmark.append_run_record(output, copy.deepcopy(record))

    assert output.read_bytes() == first_bytes
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


def test_append_rejects_an_invalid_existing_run_record(tmp_path: Path) -> None:
    output = tmp_path / "runs.jsonl"
    output.write_text('{"document_type":"run_record"}\n', encoding="utf-8")

    with pytest.raises(forge_benchmark.BenchmarkError, match="not a valid run_record"):
        forge_benchmark.append_run_record(output, build_record())


def test_append_rejects_duplicate_slots_already_in_existing_jsonl(
    tmp_path: Path,
) -> None:
    output = tmp_path / "runs.jsonl"
    existing = build_record()
    output.write_text(
        "\n".join(json.dumps(existing, separators=(",", ":")) for _ in range(2)) + "\n",
        encoding="utf-8",
    )
    next_record = copy.deepcopy(existing)
    next_record["repetition"] = 2

    with pytest.raises(forge_benchmark.BenchmarkError, match="duplicates an earlier"):
        forge_benchmark.append_run_record(output, next_record)


def test_append_wraps_output_directory_creation_errors(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("file", encoding="utf-8")

    with pytest.raises(forge_benchmark.BenchmarkError, match="could not create the output directory"):
        forge_benchmark.append_run_record(blocked_parent / "runs.jsonl", build_record())


def test_record_cli_reads_default_workflow_log_and_appends_once(tmp_path: Path, capsys) -> None:
    manifest_path = tmp_path / "manifest.json"
    session_dir = tmp_path / "session"
    session_path = session_dir / "session.json"
    workflow_path = session_dir / "logs" / "workflow.log"
    output_path = tmp_path / "runs.jsonl"
    workflow_path.parent.mkdir(parents=True)
    frozen_manifest = freeze_manifest_for_repo(make_manifest())
    manifest_path.write_text(json.dumps(frozen_manifest), encoding="utf-8")
    session_path.write_text(json.dumps(make_session()), encoding="utf-8")
    workflow_path.write_text("\n".join(json.dumps(event) for event in completed_events()) + "\n", encoding="utf-8")

    exit_code = forge_benchmark.main(
        [
            "record",
            "--manifest",
            str(manifest_path),
            "--case-id",
            "fmt",
            "--condition",
            "baseline",
            "--repetition",
            "1",
            "--session-json",
            str(session_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    stdout_record = json.loads(capsys.readouterr().out)
    output_record = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_record == output_record
    assert output_record["manifest_sha256"] == forge_benchmark.manifest_sha256(frozen_manifest)
    assert SECRET_SENTINEL not in output_path.read_text(encoding="utf-8")


def test_run_record_matches_committed_schema_required_shapes() -> None:
    schema = json.loads((REPO_ROOT / "benchmarks" / "schemas" / "forge-cpp-benchmark-v1.schema.json").read_text(encoding="utf-8"))
    record = build_record()
    run_schema = schema["$defs"]["run_record"]

    assert set(record) == set(run_schema["required"])
    for field in ("source", "outcome", "failure_attribution", "evidence"):
        assert set(record[field]) == set(run_schema["properties"][field]["required"])
    submit_schema = schema["$defs"]["submit_event"]["oneOf"][1]
    replay_schema = schema["$defs"]["replay_attempt"]["oneOf"][1]
    artifact_schema = schema["$defs"]["normalized_artifact"]
    assert set(record["evidence"]["submit_event"]) == set(submit_schema["required"])
    assert set(record["evidence"]["replay_attempt"]) == set(replay_schema["required"])
    assert set(record["evidence"]["artifacts"][0]) == set(artifact_schema["required"])


def test_stdlib_run_record_validator_accepts_generated_record() -> None:
    record = build_record()

    assert forge_benchmark.validate_run_record(record) is record


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda record: record.update(unexpected=True), "unsupported fields"),
        (lambda record: record["source"].pop("image_id"), "missing required fields"),
        (
            lambda record: record["outcome"].update(submit_status="unknown"),
            "supported submit status",
        ),
        (
            lambda record: record["outcome"].update(artifact_count=True),
            "integer or null",
        ),
        (
            lambda record: record["source"].update(session_id="not-a-session"),
            "12-character hexadecimal",
        ),
        (
            lambda record: record["failure_attribution"].update(agent=True),
            "pre-model evidence ledger",
        ),
        (
            lambda record: record["outcome"].update(finalized=False),
            "completed requires",
        ),
        (
            lambda record: record["evidence"].update(session_duration_seconds=float("inf")),
            "finite number",
        ),
        (
            lambda record: record["evidence"]["completion_event"].update(reason="unbounded"),
            "boolean result and null reason",
        ),
    ],
)
def test_stdlib_run_record_validator_rejects_malformed_nested_values(mutate, message: str) -> None:
    record = build_record()
    record["evidence"]["completion_event"] = {
        "event": "artifact.finalization_recheck",
        "reason": None,
        "passed": True,
    }
    mutate(record)

    with pytest.raises(forge_benchmark.BenchmarkError, match=message):
        forge_benchmark.validate_run_record(record)


def test_stdlib_run_record_validator_rejects_overlong_run_id() -> None:
    record = build_record()
    record["source"]["run_id"] = "a" * 161

    with pytest.raises(forge_benchmark.BenchmarkError, match="bounded run ID"):
        forge_benchmark.validate_run_record(record)


@pytest.mark.parametrize("control_character", ["\t", "\x7f"])
def test_stdlib_run_record_validator_rejects_control_character_artifact_path(
    control_character: str,
) -> None:
    record = build_record()
    record["evidence"]["artifacts"][0]["relative_path"] = f"lib/{control_character}fmt.a"

    with pytest.raises(forge_benchmark.BenchmarkError, match="relative path"):
        forge_benchmark.validate_run_record(record)


def test_stdlib_run_record_validator_rejects_more_than_one_thousand_artifacts() -> None:
    record = build_record()
    record["evidence"]["artifacts"] = record["evidence"]["artifacts"] * 1001
    record["outcome"]["artifact_count"] = 1001
    record["evidence"]["submit_event"]["artifact_count"] = 1001

    with pytest.raises(forge_benchmark.BenchmarkError, match="more than 1000"):
        forge_benchmark.validate_run_record(record)


def test_committed_pilot_manifest_has_five_unique_cpp_cases() -> None:
    manifest_path = REPO_ROOT / "benchmarks" / "manifests" / "cpp-pilot-v1.json"
    manifest = forge_benchmark.validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    frozen_revision = manifest["forge"]["commit_sha"]
    git = shutil.which("git")
    if git is not None:
        for relative_path, expected_digest in manifest["forge"]["component_sha256"].items():
            result = subprocess.run(
                [git, "show", f"{frozen_revision}:{relative_path}"],
                cwd=REPO_ROOT,
                capture_output=True,
                check=True,
            )
            assert hashlib.sha256(result.stdout).hexdigest() == expected_digest
    assert all(len(digest) == 64 for digest in manifest["forge"]["component_sha256"].values())
    for relative_path, expected_digest in manifest["protocol_artifact_sha256"].items():
        assert hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest() == expected_digest
    assert len(manifest["cases"]) == 5
    assert len({case["id"] for case in manifest["cases"]}) == 5
    assert all(set(case["languages"]) <= {"C", "C++"} for case in manifest["cases"])


def test_frozen_component_verification_rejects_file_drift(tmp_path: Path) -> None:
    manifest = make_manifest()
    hash_groups = (
        manifest["forge"]["component_sha256"],
        manifest["protocol_artifact_sha256"],
    )
    for hashes in hash_groups:
        for relative_path in hashes:
            candidate = tmp_path / relative_path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(f"frozen:{relative_path}\n", encoding="utf-8")
            hashes[relative_path] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    forge_benchmark.verify_frozen_components(manifest, tmp_path)

    drifted_path = tmp_path / next(iter(manifest["forge"]["component_sha256"]))
    drifted_path.write_text("drifted\n", encoding="utf-8")

    with pytest.raises(forge_benchmark.BenchmarkError, match="does not match the current repository file"):
        forge_benchmark.verify_frozen_components(manifest, tmp_path)
