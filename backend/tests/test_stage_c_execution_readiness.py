from __future__ import annotations

import json
import os
import subprocess
import sys
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
            protocol.PROTOCOL_PATH: "4" * 64,
            protocol.RUNNER_PATH: "5" * 64,
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
        "tasks": [{"task_id": "fixture"}],
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
        lambda *_args, **_kwargs: {"release_revision": "release"},
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
