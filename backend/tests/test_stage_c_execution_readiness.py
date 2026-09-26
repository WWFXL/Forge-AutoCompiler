from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_stage_c_controlled_baseline as baseline  # noqa: E402
import forge_stage_c_protocol as protocol  # noqa: E402
import forge_stage_c_remediation_protocol as remediation_protocol  # noqa: E402
import forge_stage_c_runner as runner  # noqa: E402
import forge_stage_c_task_qualification as qualification  # noqa: E402


@dataclass
class _FakeExecutor:
    results: list[baseline.ControlledBuildResult]

    def execute(self, dockerfile: str, *, revision: int) -> baseline.ControlledBuildResult:
        assert revision >= 1
        assert baseline.validate_dockerfile(dockerfile, _IMAGE_ID) == dockerfile
        return self.results.pop(0)


class _FakeModel:
    def __init__(self, values: list[dict[str, object]]):
        self.values = values

    def invoke(self, _prompt: str) -> SimpleNamespace:
        value = self.values.pop(0)
        return SimpleNamespace(
            content=json.dumps(value),
            usage_metadata={"total_tokens": 11},
        )


_IMAGE_ID = "sha256:" + "a" * 64
_DOCKERFILE = f"FROM {_IMAGE_ID}\nCOPY source/ /workspace/repo/\nRUN mkdir -p /artifacts/bin && cc /workspace/repo/main.c -o /artifacts/bin/app\n"
_DOCKER_ENABLED = os.getenv("FORGE_RUN_STAGE_C_DOCKER") == "1"
_DOCKER_FIXTURES = {
    "cmake": (
        {
            "CMakeLists.txt": "cmake_minimum_required(VERSION 3.16)\nproject(stage_c_fixture C)\nadd_executable(stage_c_fixture main.c)\n",
            "main.c": '#include <stdio.h>\nint main(void){puts("stage-c-fixture");return 0;}\n',
        },
        "RUN cd /workspace/repo && cmake -S . -B build && cmake --build build --parallel 2 && mkdir -p /artifacts/bin && cp build/stage_c_fixture /artifacts/bin/app",
    ),
    "make": (
        {
            "Makefile": "app: main.c\n\t$(CC) -O2 -o $@ $<\n",
            "main.c": '#include <stdio.h>\nint main(void){puts("stage-c-fixture");return 0;}\n',
        },
        "RUN cd /workspace/repo && make -j2 && mkdir -p /artifacts/bin && cp app /artifacts/bin/app",
    ),
    "autotools": (
        {
            "configure.ac": "AC_INIT([stage-c-fixture], [1.0])\nAM_INIT_AUTOMAKE([foreign])\nAC_PROG_CC\nAC_CONFIG_FILES([Makefile])\nAC_OUTPUT\n",
            "Makefile.am": "bin_PROGRAMS = app\napp_SOURCES = main.c\n",
            "main.c": '#include <stdio.h>\nint main(void){puts("stage-c-fixture");return 0;}\n',
        },
        "RUN cd /workspace/repo && autoreconf -fi && ./configure && make -j2 && mkdir -p /artifacts/bin && cp app /artifacts/bin/app",
    ),
}


def _execution(*, succeeded: bool, revision: int) -> baseline.ControlledBuildResult:
    return baseline.ControlledBuildResult(
        execution_id=f"execution-{revision}",
        dockerfile_sha256=baseline.hashlib.sha256(_DOCKERFILE.encode()).hexdigest(),
        succeeded=succeeded,
        timed_out=False,
        exit_code=0 if succeeded else 1,
        duration_seconds=0.1,
        output_tail="ok" if succeeded else "failed",
        artifact_paths=("bin/app",) if succeeded else (),
        artifact_manifest_sha256="b" * 64 if succeeded else None,
        candidate_image_id="sha256:" + "c" * 64 if succeeded else None,
    )


def _parser_value() -> dict[str, object]:
    return {
        "build_system": "make",
        "dependencies": [],
        "build_steps": ["make"],
        "artifact_steps": ["cp app /artifacts/bin/app"],
    }


def test_stage_c_qualification_contract_is_result_blind_and_balanced() -> None:
    pool = qualification.validate_source_pool(qualification.load_json(qualification.DEFAULT_POOL))
    plan = qualification.load_plan()

    assert len(pool["tasks"]) == 12
    assert len(plan["tasks"]) == 12
    assert plan["authorization"]["provider_calls_authorized"] is False
    assert plan["authorization"]["model_tokens_authorized"] == 0
    assert pool["exclusions"]["historical_a_or_b_model_results_observed"] is False
    assert {task["task_id"] for task in pool["tasks"]}.isdisjoint(pool["exclusions"]["stage_b_task_ids"])


def test_stage_c_8cc_oracle_uses_supported_compile_mode() -> None:
    plan = qualification.load_plan()
    task = next(item for item in plan["tasks"] if item["task_id"] == "8cc")
    command = task["oracle"]["argv"][2]

    assert "/artifacts/bin/8cc -c -o /tmp/forge-8cc-oracle.o" in command
    assert "cc /tmp/forge-8cc-oracle.o -o /tmp/forge-8cc-oracle" in command


def test_stage_c_theora_oracle_matches_legacy_header_api() -> None:
    plan = qualification.load_plan()
    task = next(item for item in plan["tasks"] if item["task_id"] == "theora")
    source = task["oracle"]["source"]

    assert "theora_info_init(&i)" in source
    assert "theora_info_clear(&i)" in source
    assert "th_info" not in source


def test_stage_c_libsndfile_autotools_dependency_and_recipe_are_valid() -> None:
    plan = qualification.load_plan()
    task = next(item for item in plan["tasks"] if item["task_id"] == "libsndfile")
    dockerfile = (REPO_ROOT / "docker/compile/Dockerfile.stage-c").read_text()

    assert "      autogen \\\n" in dockerfile
    assert task["reference_recipe"][0] == "autoreconf -vif"
    assert "--disable-programs" not in task["reference_recipe"][1]


def test_stage_c_civetweb_reference_recipe_repairs_frozen_upstream_commit() -> None:
    plan = qualification.load_plan()
    task = next(item for item in plan["tasks"] if item["task_id"] == "civetweb")
    patch_command = task["reference_recipe"][0]

    assert "patch -p1 --fuzz=0" in patch_command
    assert 'mg_strcasecmp(h_chunk, "identity")' in patch_command
    assert "strtoll(h_len, &endptr, 10)" in patch_command
    assert task["reference_recipe"][1].startswith("make -j4 lib")


def test_stage_c_image_identity_is_bound_to_current_dockerfile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = qualification.load_plan()
    dockerfile = REPO_ROOT / plan["environment"]["dockerfile_path"]
    expected_digest = qualification.file_sha256(dockerfile)

    monkeypatch.setattr(
        qualification,
        "_run_checked",
        lambda _argv: f"{_IMAGE_ID}\t{'0' * 64}",
    )
    with pytest.raises(
        qualification.StageCTaskQualificationError,
        match="必须重新执行 build-image",
    ):
        qualification.image_id(plan)

    monkeypatch.setattr(
        qualification,
        "_run_checked",
        lambda _argv: f"{_IMAGE_ID}\t{expected_digest}",
    )
    assert qualification.image_id(plan) == _IMAGE_ID


def test_stage_c_image_build_records_current_dockerfile_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = qualification.load_plan()
    dockerfile = REPO_ROOT / plan["environment"]["dockerfile_path"]
    expected_digest = qualification.file_sha256(dockerfile)
    commands: list[list[str]] = []

    monkeypatch.setattr(qualification, "require_zero_managed_resources", lambda: None)
    monkeypatch.setattr(
        qualification,
        "_run_checked",
        lambda argv, **_kwargs: commands.append(argv) or "",
    )
    monkeypatch.setattr(qualification, "image_id", lambda _plan: _IMAGE_ID)

    result = qualification.build_image(plan)

    assert len(commands) == 1
    command = commands[0]
    assert command[command.index("--label") + 1] == (f"{qualification.DOCKERFILE_SHA256_LABEL}={expected_digest}")
    assert result["dockerfile_sha256"] == expected_digest
    assert result["image_id"] == _IMAGE_ID


def test_stage_c_dockerfile_bootstraps_ca_before_verified_snapshot_install() -> None:
    dockerfile = (REPO_ROOT / "docker/compile/Dockerfile.stage-c").read_text()

    bootstrap_config = "/etc/apt/apt.conf.d/81-stage-c-ca-bootstrap"
    bootstrap_write = dockerfile.index(f"> {bootstrap_config}")
    ca_install = dockerfile.index("apt-get install -y --no-install-recommends ca-certificates")
    bootstrap_remove = dockerfile.index(f"rm -f {bootstrap_config}")
    verified_update = dockerfile.index("apt-get update", bootstrap_remove)
    toolchain_install = dockerfile.index("apt-get install -y --no-install-recommends \\", verified_update)

    assert 'Acquire::https::Verify-Peer "false";' in dockerfile
    assert dockerfile.count("apt-get update") == 2
    assert bootstrap_write < ca_install < bootstrap_remove < verified_update < toolchain_install


def test_stage_c_qualification_containers_use_host_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docker_runs: list[list[str]] = []
    docker_removals: list[list[str]] = []

    def fake_clone(_task: dict[str, Any], destination: Path) -> None:
        destination.mkdir(parents=True)

    def fake_checked(argv: list[str], **_kwargs: Any) -> str:
        docker_runs.append(argv)
        return ""

    monkeypatch.setattr(qualification, "_clone_exact", fake_clone)
    monkeypatch.setattr(qualification, "_verify_source", lambda *_args: {})
    monkeypatch.setattr(qualification, "_artifact_evidence", lambda *_args: [])
    monkeypatch.setattr(qualification, "_run_checked", fake_checked)
    monkeypatch.setattr(
        qualification.subprocess,
        "run",
        lambda argv, **_kwargs: docker_removals.append(argv),
    )
    plan = {"environment": {"parallel_jobs": 4, "per_task_timeout_seconds": 60}}
    task = {
        "task_id": "fixture",
        "reference_recipe": ["true"],
        "oracle": {"kind": "command", "argv": ["true"]},
    }

    qualification._run_reference_once(
        plan,
        {},
        task,
        tmp_path / "replicate-1",
        1,
        _IMAGE_ID,
    )

    assert len(docker_runs) == 2
    for command in docker_runs:
        assert command[command.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
        assert command[command.index("--env") + 1] == "HOME=/tmp"
    assert len(docker_removals) == 2
    assert all(command[:3] == ["docker", "rm", "-f"] for command in docker_removals)


def test_controlled_baseline_submits_unified_candidate(tmp_path: Path) -> None:
    model = _FakeModel(
        [
            _parser_value(),
            {"dockerfile": _DOCKERFILE},
            {"success": True, "advice": None},
        ]
    )
    runner = baseline.ControlledBaselineRunner(
        task_contract={"required_artifacts": ["bin/app"]},
        source_observation={"files": ["Makefile", "main.c"]},
        task_id="fixture",
        attempt_id="fixture-a-r1",
        base_image_id=_IMAGE_ID,
        model=model,
        executor=_FakeExecutor([_execution(succeeded=True, revision=1)]),
        limits=baseline.ControlledBaselineLimits(24, 300_000, 1800),
        output_dir=tmp_path / "attempt",
    )

    outcome = runner.run()

    assert outcome.candidate_generated is True
    assert outcome.candidate_submitted is True
    assert outcome.model_requests == 3
    assert outcome.recorded_tokens == 33
    assert outcome.executor_runs == 1
    assert outcome.candidate is not None
    assert (tmp_path / "attempt/candidate.json").is_file()
    assert (tmp_path / "attempt/Dockerfile").read_text() == _DOCKERFILE


def test_controlled_baseline_modifier_stays_inside_global_budget(tmp_path: Path) -> None:
    model = _FakeModel(
        [
            _parser_value(),
            {"dockerfile": _DOCKERFILE},
            {"success": False, "advice": "修复构建命令"},
            {"dockerfile": _DOCKERFILE},
            {"success": True, "advice": None},
        ]
    )
    runner = baseline.ControlledBaselineRunner(
        task_contract={"required_artifacts": ["bin/app"]},
        source_observation={"files": ["Makefile", "main.c"]},
        task_id="fixture",
        attempt_id="fixture-a-r1",
        base_image_id=_IMAGE_ID,
        model=model,
        executor=_FakeExecutor(
            [
                _execution(succeeded=False, revision=1),
                _execution(succeeded=True, revision=2),
            ]
        ),
        limits=baseline.ControlledBaselineLimits(5, 300_000, 1800),
        output_dir=tmp_path / "attempt",
    )

    outcome = runner.run()

    assert outcome.candidate_submitted is True
    assert outcome.model_requests == 5
    assert outcome.executor_runs == 2
    assert outcome.judge_runs == 2
    assert outcome.modifier_runs == 1


def test_controlled_baseline_rejects_networked_dockerfile() -> None:
    dockerfile = f"FROM {_IMAGE_ID}\nCOPY source/ /workspace/repo/\nRUN curl https://example.invalid/file -o /artifacts/file\n"

    with pytest.raises(baseline.ControlledBaselineError, match="禁用"):
        baseline.validate_dockerfile(dockerfile, _IMAGE_ID)


def test_stage_c_schedule_is_deterministic_and_counterbalanced() -> None:
    pool = qualification.validate_source_pool(qualification.load_json(qualification.DEFAULT_POOL))

    first = protocol._schedule(pool)
    second = protocol._schedule(pool)

    assert first == second
    assert first["pair_count"] == 24
    assert first["physical_attempt_count"] == 48
    assert [pair["arm_order"][0] for pair in first["pairs"]].count("A") == 12
    assert [pair["arm_order"][0] for pair in first["pairs"]].count("B") == 12
    for task_id in first["project_order"]:
        orders = [pair["arm_order"] for pair in first["pairs"] if pair["task_id"] == task_id]
        assert orders[1] == list(reversed(orders[0]))


def test_stage_c_cost_audit_recomputes_history_and_binds_hard_ceiling() -> None:
    audit = protocol._validate_cost_audit(REPO_ROOT)
    decision = audit["decision"]

    assert audit["stage_c_outcomes_observed"] is False
    assert [item["total_recorded_tokens"] for item in audit["historical_inputs"]] == [212_109, 918_121]
    assert max(task["recorded_tokens"] for item in audit["historical_inputs"] for task in item["tasks"]) == decision["historical_max_recorded_tokens"] == 279_841
    assert decision["max_recorded_tokens_per_arm"] == 300_000
    assert decision["observed_max_headroom_tokens"] == 20_159
    assert decision["upper_bound_role"] == "hard_stop_not_expected_consumption"


def test_stage_c_manifest_binds_qualification_and_cost_audit() -> None:
    manifest = protocol.generate_manifest()

    assert manifest["qualification"]["result_file_sha256"] == qualification.file_sha256(qualification.DEFAULT_RESULT)
    audit = manifest["budget"]["cost_sensitivity_audit"]
    assert audit["path"] == protocol.COST_AUDIT_PATH
    assert audit["file_sha256"] == qualification.file_sha256(REPO_ROOT / protocol.COST_AUDIT_PATH)
    assert audit["decision"]["total_max_recorded_tokens"] == 14_405_000
    assert protocol.COST_AUDIT_PATH in manifest["frozen_components"]


def test_stage_c_remediation_manifest_binds_failed_v1_without_importing_outcomes() -> None:
    manifest = remediation_protocol.generate_manifest()
    prior = manifest["prior_failed_identity"]

    assert prior["manifest_sha256"] == "6ef6f6fe9986ad6eb53d57273d4901389e96bff5b6b69d884d09282d391ac641"
    assert prior["must_not_resume"] is True
    assert prior["historical_outcomes_imported"] is False
    assert manifest["execution"]["evidence_directory"] == remediation_protocol.DEFAULT_EVIDENCE_DIRECTORY
    assert manifest["authorization"]["prior_reachability_recorded_tokens"] == 70
    assert manifest["authorization"]["cumulative_max_recorded_tokens"] == 14_405_070
    assert all(pair["pair_id"].startswith("stage-c-v2-") for pair in manifest["schedule"]["pairs"])
    assert len({attempt for pair in manifest["schedule"]["pairs"] for attempt in pair["attempt_ids"].values()}) == 48


def test_stage_c_public_tasks_do_not_expose_reference_recipes() -> None:
    pool = qualification.validate_source_pool(qualification.load_json(qualification.DEFAULT_POOL))
    plan = qualification.load_plan()
    result = {
        "tasks": [
            {
                "task_id": task["task_id"],
                "passed": True,
                "bitwise_reproducible": True,
                "replicates": [{}, {}],
            }
            for task in plan["tasks"]
        ]
    }

    public = protocol._public_tasks(pool, plan, result)

    assert len(public) == 12
    assert all("reference_recipe" not in task for task in public)
    assert all("target_contract" in task and "oracle" in task for task in public)


def _valid_qualification_result() -> tuple[dict[str, Any], dict[str, Any]]:
    pool = qualification.validate_source_pool(qualification.load_json(qualification.DEFAULT_POOL))
    plan = qualification.load_plan()
    pool_by_id = {task["task_id"]: task for task in pool["tasks"]}
    receipts = []
    for task in plan["tasks"]:
        source = pool_by_id[task["task_id"]]
        artifacts = [
            {
                "path": path,
                "type": artifact_type,
                "size_bytes": 1,
                "sha256": "6" * 64,
                "file_type": "fixture",
            }
            for path, artifact_type in zip(
                task["target"]["required_artifacts"],
                task["target"]["artifact_types"],
                strict=True,
            )
        ]
        source_identity = {
            "commit_sha": source["commit_sha"],
            "source_snapshot_sha256": source["source_snapshot_sha256"],
            "license_sha256": source["license_sha256"],
            "submodule_commits": source["submodule_commits"],
        }
        receipts.append(
            {
                "task_id": task["task_id"],
                "passed": True,
                "bitwise_reproducible": True,
                "replicates": [
                    {
                        "replicate": replicate,
                        "source_identity": source_identity,
                        "artifacts": [dict(artifact) for artifact in artifacts],
                        "oracle_passed": True,
                        "duration_seconds": 0.1,
                    }
                    for replicate in (1, 2)
                ],
            }
        )
    result = {
        "schema_version": "forge-stage-c-task-qualification-result-1.0.0",
        "status": "passed",
        "plan_canonical_sha256": qualification.canonical_sha256(plan),
        "source_pool_canonical_sha256": qualification.canonical_sha256(pool),
        "dockerfile_sha256": qualification.file_sha256(REPO_ROOT / plan["environment"]["dockerfile_path"]),
        "image_id": _IMAGE_ID,
        "ubuntu_snapshot": plan["environment"]["ubuntu_snapshot"],
        "task_count": 12,
        "reference_build_count": 24,
        "provider_request_count": 0,
        "model_created": False,
        "model_tokens": 0,
        "formal_stage_c_attempt_created": False,
        "formal_stage_c_evidence_written": False,
        "zero_managed_resources_before": True,
        "zero_managed_resources_after": True,
        "tasks": receipts,
    }
    return result, plan


def test_qualification_result_rejects_tampered_replicate_evidence() -> None:
    result, plan = _valid_qualification_result()
    qualification.validate_result(result, plan)
    result["tasks"][0]["replicates"][1]["artifacts"][0]["sha256"] = "7" * 64

    with pytest.raises(
        qualification.StageCTaskQualificationError,
        match="bitwise receipt 与 artifact evidence 不一致",
    ):
        qualification.validate_result(result, plan)


def test_stage_c_node_input_matches_runtime_v2_contract() -> None:
    task = {
        "task_id": "fixture",
        "repository_url": "https://example.com/fixture.git",
        "commit_sha": "1" * 40,
        "source_snapshot_sha256": "2" * 64,
        "build_system_capabilities": ["cmake"],
        "selected_build_system": "cmake",
        "qualification_receipt": {"receipt_sha256": "3" * 64},
        "target_contract": {
            "target_id": "fixture-library",
            "required_artifacts": ["include/fixture.h", "lib/libfixture.a"],
            "artifact_types": ["support_file", "static_library"],
            "bitwise_required": True,
        },
    }
    manifest = {
        "environment": {
            "compile_image": "autocompiler:stage-c-v1",
            "image_id": _IMAGE_ID,
            "parallel_jobs": 4,
        },
        "budget": {
            "per_arm": {
                "max_model_requests": 24,
                "max_recorded_tokens": 300_000,
                "forge_max_agent_steps": 64,
                "forge_max_tool_calls": 48,
                "forge_max_commands": 32,
                "work_timeout_seconds": 1800,
                "command_timeout_seconds": 900,
                "evaluator_timeout_seconds": 1800,
                "replay_timeout_seconds": 1800,
                "cleanup_reserve_seconds": 120,
            }
        },
        "frozen_components": {
            remediation_protocol.PROTOCOL_PATH: "4" * 64,
            remediation_protocol.RUNNER_PATH: "5" * 64,
        },
    }

    node_input = runner._node_input(manifest, task, SimpleNamespace(session_id="session-fixture"), "attempt-fixture")

    node_input.validate()
    assert node_input.environment.image_id == _IMAGE_ID
    assert node_input.target_contract.artifact_types == ("static_library",)
    assert node_input.source_snapshot_sha256 == "2" * 64
    assert node_input.budget.evaluator_timeout_seconds == 1800


def test_controlled_baseline_budget_exhaustion_is_a_closed_arm(tmp_path: Path) -> None:
    model = _FakeModel(
        [
            _parser_value(),
            {"dockerfile": _DOCKERFILE},
            {"success": False, "advice": "继续修改"},
        ]
    )
    controlled = baseline.ControlledBaselineRunner(
        task_contract={"required_artifacts": ["bin/app"]},
        source_observation={"files": ["Makefile", "main.c"]},
        task_id="fixture",
        attempt_id="fixture-budget",
        base_image_id=_IMAGE_ID,
        model=model,
        executor=_FakeExecutor([_execution(succeeded=False, revision=1)]),
        limits=baseline.ControlledBaselineLimits(3, 300_000, 1800),
        output_dir=tmp_path / "attempt",
    ).run()

    assert controlled.candidate_generated is True
    assert controlled.candidate_submitted is False
    assert controlled.termination_reason == "budget_exhausted:model_requests"
    assert controlled.model_requests == 3


def _batch_manifest(*, formal_token_budget: int = 600_000) -> dict[str, Any]:
    pair = {
        "pair_id": "stage-c-fixture-r1",
        "task_id": "fixture",
        "replicate": 1,
        "arm_order": ["A", "B"],
        "attempt_ids": {"A": "fixture-a", "B": "fixture-b"},
    }
    return {
        "tasks": [{"task_id": "fixture", "source_snapshot_sha256": "2" * 64}],
        "schedule": {"pairs": [pair], "project_order": ["fixture"]},
        "budget": {
            "per_arm": {"max_recorded_tokens": 300_000},
            "formal_arms_max_recorded_tokens": formal_token_budget,
        },
        "execution": {
            "batch_marker": "markers/batch.json",
            "batch_report": "reports/deployment.json",
            "paired_report": "reports/paired.json",
        },
    }


def _arm_result(manifest: dict[str, Any], pair: dict[str, Any], arm: str, *, success: bool) -> dict[str, Any]:
    return {
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": "release",
        "pair_id": pair["pair_id"],
        "task_id": pair["task_id"],
        "replicate": pair["replicate"],
        "arm": arm,
        "method": ("cxxcrafter-controlled" if arm == "A" else "forge-agent-workflow-node-v2"),
        "attempt_id": pair["attempt_ids"][arm],
        "candidate_generated": success,
        "candidate_submitted": success,
        "s0_s5": [],
        "strict_reproducible_build_success": success,
        "bitwise_reproducible": None,
        "recorded_tokens": 10,
        "cleanup_succeeded": True,
        "zero_managed_resources": True,
    }


def _patch_batch_preflight(monkeypatch: pytest.MonkeyPatch, manifest: dict[str, Any]) -> None:
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *_args, **_kwargs: {
            "release_revision": "release",
            "ready": True,
            "incomplete_pairs": [],
        },
    )
    monkeypatch.setattr(
        runner,
        "_require_reachability",
        lambda *_args, **_kwargs: {"recorded_tokens": 7},
    )
    monkeypatch.setattr(runner, "require_zero_managed_resources", lambda: None)


def test_stage_c_first_arm_failure_does_not_block_second(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _batch_manifest()
    pair = manifest["schedule"]["pairs"][0]
    _patch_batch_preflight(monkeypatch, manifest)
    observed: list[str] = []

    def execute(
        _manifest: dict[str, Any],
        _task: dict[str, Any],
        _pair: dict[str, Any],
        *,
        release_revision: str,
        arm_dir: Path,
    ) -> dict[str, Any]:
        arm = arm_dir.name
        observed.append(arm)
        runner._register_arm_attempt(
            manifest,
            pair,
            arm,
            release_revision=release_revision,
            arm_dir=arm_dir,
            source_snapshot_sha256="2" * 64,
        )
        value = _arm_result(manifest, pair, arm, success=arm == "B")
        runner._write_once(arm_dir / "result.json", value)
        return value

    report = runner.run_batch(
        manifest,
        output_dir=tmp_path,
        arm_executors={"A": execute, "B": execute},
    )

    assert observed == ["A", "B"]
    assert report["pair_count"] == 1
    assert report["strict_success"] == {"A": 0, "B": 1}
    assert report["pairs"][0]["paired_delta"] == 1
    pair_path = tmp_path / "pairs" / pair["pair_id"] / "pair.json"
    tampered = json.loads(pair_path.read_text())
    tampered["paired_delta"] = 0
    pair_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(runner.StageCRunnerError, match="pair result 无效"):
        runner._completed_pairs(manifest, tmp_path)


def test_stage_c_pair_boundary_budget_gate_starts_no_arm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _batch_manifest(formal_token_budget=599_999)
    _patch_batch_preflight(monkeypatch, manifest)

    def unexpected(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("预算不足时不得启动 arm")

    report = runner.run_batch(
        manifest,
        output_dir=tmp_path,
        arm_executors={"A": unexpected, "B": unexpected},
    )

    assert report["pair_count"] == 0
    marker = json.loads((tmp_path / "markers/batch.json").read_text())
    assert marker["status"] == "budget_stopped"


def test_stage_c_incomplete_pair_and_managed_orphan_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _batch_manifest()
    pair = manifest["schedule"]["pairs"][0]
    arm_dir = tmp_path / "pairs" / pair["pair_id"] / "A"
    runner._write_once(arm_dir / "result.json", _arm_result(manifest, pair, "A", success=False))

    with pytest.raises(runner.StageCRunnerError, match="未闭合 pair"):
        runner._completed_pairs(manifest, tmp_path)

    monkeypatch.setattr(runner.stage_b, "require_zero_managed_resources", lambda: None)
    monkeypatch.setattr(
        runner,
        "_run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=f"{runner.MANAGED_A_PREFIX}leftover\n"),
    )
    with pytest.raises(runner.StageCRunnerError, match="managed orphan"):
        runner.require_zero_managed_resources()


def test_stage_c_controlled_source_failure_creates_no_formal_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _batch_manifest()
    pair = manifest["schedule"]["pairs"][0]
    task = manifest["tasks"][0]
    monkeypatch.setattr(
        runner,
        "_clone_export",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(runner.StageCRunnerError("source fetch failed")),
    )

    with pytest.raises(runner.StageCRunnerError, match="source fetch failed"):
        runner.execute_controlled_arm(
            manifest,
            task,
            pair,
            release_revision="release",
            arm_dir=tmp_path / "pairs" / pair["pair_id"] / "A",
            model_factory=lambda *_args: (_ for _ in ()).throw(AssertionError("源码准备失败前不得创建模型")),
        )

    assert not (tmp_path / "pairs").exists()


def test_stage_c_forge_source_failure_creates_no_formal_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _batch_manifest()
    manifest["environment"] = {"image_id": _IMAGE_ID}
    pair = manifest["schedule"]["pairs"][0]
    task = manifest["tasks"][0]
    task.update(
        {
            "repository_url": "https://example.invalid/fixture.git",
            "commit_sha": "1" * 40,
        }
    )

    @contextmanager
    def runtime_identity(_manifest: dict[str, Any]):
        yield SimpleNamespace()

    monkeypatch.setattr(runner, "_stage_c_runtime_identity", runtime_identity)
    monkeypatch.setattr(
        runner,
        "_clone_export",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(runner.StageCRunnerError("source fetch failed")),
    )
    monkeypatch.setattr(runner, "require_zero_managed_resources", lambda: None)

    with pytest.raises(runner.StageCRunnerError, match="source fetch failed"):
        asyncio.run(
            runner.execute_forge_arm(
                manifest,
                task,
                pair,
                release_revision="release",
                arm_dir=tmp_path / "pairs" / pair["pair_id"] / "B",
            )
        )

    assert not (tmp_path / "pairs").exists()


def test_stage_c_forge_source_preparation_populates_session_before_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = tmp_path / "prepared-repository"
    source = tmp_path / "prepared-source"
    repository.mkdir()
    source.mkdir()
    (repository / ".git").mkdir()
    (repository / ".git/HEAD").write_text("ref: refs/heads/main\n")
    (repository / "CMakeLists.txt").write_text("project(fixture)\n")
    (source / "CMakeLists.txt").write_text("project(fixture)\n")
    session_repo = tmp_path / "session/workspace/repo"
    session = SimpleNamespace(
        leadagent_repo_dir=str(session_repo),
        commit_sha=None,
        summary=None,
    )
    events: list[tuple[str, dict[str, Any]]] = []

    class Manager:
        def create_session(self, **_kwargs: Any) -> SimpleNamespace:
            session_repo.parent.mkdir(parents=True)
            return session

        def save_session(self, _session: SimpleNamespace) -> None:
            events.append(("saved", {}))

        def log_event(self, _session: SimpleNamespace, event: str, **payload: Any) -> None:
            events.append((event, payload))

        def mark_session_status(self, _session: SimpleNamespace, status: str, **_kwargs: Any) -> None:
            events.append(("status", {"status": status}))

    task = {
        "task_id": "fixture",
        "repository_url": "https://example.invalid/fixture.git",
        "commit_sha": "1" * 40,
        "source_snapshot_sha256": "2" * 64,
        "build_system_capabilities": ["cmake"],
    }
    pair = {"pair_id": "stage-c-v2-fixture-r1"}
    monkeypatch.setattr(
        runner,
        "_clone_export",
        lambda *_args, **_kwargs: {
            "repository": repository,
            "source": source,
            "source_snapshot_sha256": "2" * 64,
        },
    )

    prepared, source_digest = runner._prepare_forge_session(
        task,
        pair,
        "stage-c-v2-fixture",
        SimpleNamespace(manager=Manager()),
    )

    assert prepared is session
    assert source_digest == "2" * 64
    assert session.commit_sha == "1" * 40
    assert (session_repo / "CMakeLists.txt").read_text() == "project(fixture)\n"
    assert (session_repo / ".git/HEAD").is_file()
    assert ("status", {"status": "source_ready"}) in events


def test_stage_c_preflight_recomputes_usage_and_incomplete_pairs(tmp_path: Path) -> None:
    runner._write_once(
        tmp_path / "reports/reachability.json",
        {"request_count": 1, "recorded_tokens": 70},
    )
    runner._write_once(
        tmp_path / "pairs/pair-1/A/attempt.json",
        {"status": "started"},
    )
    runner._write_once(
        tmp_path / "pairs/pair-1/A/result.json",
        {"model_requests": 3, "recorded_tokens": 123},
    )

    state = runner._recorded_evidence_state(tmp_path)

    assert state == {
        "formal_stage_c_attempts": 1,
        "incomplete_pairs": ["pair-1"],
        "provider_calls": 4,
        "model_tokens": 193,
    }


@pytest.mark.skipif(
    not _DOCKER_ENABLED,
    reason="set FORGE_RUN_STAGE_C_DOCKER=1 to run the Stage C Docker gate",
)
@pytest.mark.parametrize("build_system", tuple(_DOCKER_FIXTURES))
def test_stage_c_a_docker_fixture_covers_oracle_replay_and_cleanup(build_system: str, tmp_path: Path) -> None:
    image_id = subprocess.run(
        ["docker", "image", "inspect", "autocompiler:gcc13", "--format", "{{.Id}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    files, build_command = _DOCKER_FIXTURES[build_system]
    source = tmp_path / "source"
    source.mkdir()
    for relative, contents in files.items():
        (source / relative).write_text(contents, encoding="utf-8")
    task = {
        "task_id": f"fixture-{build_system}",
        "target_contract": {
            "required_artifacts": ["bin/app"],
            "artifact_types": ["executable"],
        },
        "oracle": {
            "kind": "command",
            "argv": ["sh", "-c", "/artifacts/bin/app | grep -F stage-c-fixture"],
        },
    }
    manifest = {"environment": {"image_id": image_id}}
    dockerfile = f"FROM {image_id}\nCOPY source/ /workspace/repo/\n{build_command}\n"
    executor = runner.DockerfileExecutor(
        source=source,
        task=task,
        arm_dir=tmp_path / "arm",
        timeout_seconds=180,
    )
    try:
        first = executor.execute(dockerfile, revision=1)
        replay = executor.execute(dockerfile, revision=2)
        assert first.succeeded is True
        assert replay.succeeded is True
        assert first.artifact_manifest_sha256 == replay.artifact_manifest_sha256
        assert runner._run_oracle(
            manifest,
            task,
            executor.artifact_dirs[1],
            f"fixture-{build_system}",
        )
    finally:
        executor.cleanup()
    runner.require_zero_managed_resources()
