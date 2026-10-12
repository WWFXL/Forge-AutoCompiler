from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_dynamic_budget_trajectory_qualification.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_dynamic_budget_trajectory_qualification", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def module() -> ModuleType:
    return _load_module()


@pytest.fixture()
def manifest(module: ModuleType) -> dict:
    return module.validate_manifest(module._load_json(module.MANIFEST_PATH))


def test_manifest_freezes_cross_system_schedule_and_zero_provider_boundary(module: ModuleType, manifest: dict) -> None:
    plan = module._plan(manifest)

    assert plan["systems"] == ["cmake", "make", "autotools"]
    assert plan["projects"] == 9
    assert plan["states"] == 27
    assert plan["continuations"] == 54
    assert plan["credential_read"] is False
    assert plan["provider_requests"] == 0
    assert plan["agent_continuation"] is False
    assert plan["controller_implementation"] is False


@pytest.mark.parametrize("field", ["provider_requests", "input_tokens", "output_tokens", "provider_cost_microusd"])
def test_manifest_rejects_nonzero_provider_budget(module: ModuleType, manifest: dict, field: str) -> None:
    changed = copy.deepcopy(manifest)
    changed["shared_block_budget"][field] = 1

    with pytest.raises(module.QualificationError, match="Provider dimensions"):
        module.validate_manifest(changed)


def test_manifest_rejects_historical_evaluation_family(module: ModuleType, manifest: dict) -> None:
    changed = copy.deepcopy(manifest)
    changed["projects"][0]["project_family"] = "github.com/libgit2/libgit2"

    with pytest.raises(module.QualificationError, match="historical Jev evaluation"):
        module.validate_manifest(changed)


def test_manifest_rejects_project_replacement_or_command_drift(module: ModuleType, manifest: dict) -> None:
    changed = copy.deepcopy(manifest)
    changed["projects"].pop()
    with pytest.raises(module.QualificationError, match="nine projects"):
        module.validate_manifest(changed)

    changed = copy.deepcopy(manifest)
    changed["projects"][0]["actions"][0]["command"] = ""
    with pytest.raises(module.QualificationError, match="command is empty"):
        module.validate_manifest(changed)


def test_budget_record_accounts_for_both_physical_continuations(module: ModuleType) -> None:
    before = module._budget_zero()
    before["wall_clock_milliseconds"] = 10
    repetitions = [{"duration_milliseconds": 12}, {"duration_milliseconds": 18}]

    record = module._budget_record(before, repetitions)

    assert record["delta"] == {
        "wall_clock_milliseconds": 30,
        "provider_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "provider_cost_microusd": 0,
        "build_executions": 2,
    }
    assert record["after"]["wall_clock_milliseconds"] == 40
    assert record["after"]["build_executions"] == 2
    assert record["conserved"] is True


def _completed_result(module: ModuleType) -> dict:
    states = []
    projects = []
    blocks = []
    for system in module.SYSTEMS:
        for project_index in range(3):
            case_id = f"{system}-project-{project_index}"
            projects.append({"case_id": case_id, "build_system": system, "state_count": 3})
            for state_index in range(3):
                states.append(
                    {
                        "state_id": f"{case_id}-{state_index}",
                        "checkpoint": {"checkpoint_sha256": "a" * 64},
                        "repetitions": [{"exit_code": 0}, {"exit_code": 0}],
                        "consistent": True,
                        "budget": {"conserved": True},
                        "successor_observed": True,
                        "agent_calls": 0,
                    }
                )
        blocks.append({"within_limit": True, "stop_transfer": {"passed": True}})
    return {
        "projects": projects,
        "states": states,
        "blocks": blocks,
        "managed_containers_after_cleanup": [],
    }


def test_qualification_requires_every_gate(module: ModuleType, manifest: dict) -> None:
    result = _completed_result(module)
    passed = module._qualification(result, manifest)
    assert passed["passed"] is True
    assert passed["decision"] == "proceed_to_agent_continuation_qualification_design"

    result["states"][0]["consistent"] = False
    failed = module._qualification(result, manifest)
    assert failed["passed"] is False
    assert failed["decision"] == "stop_before_agent_continuation_and_controller_implementation"


def test_tree_hash_ignores_mtime_but_detects_content(module: ModuleType, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "value.txt").write_text("same", encoding="utf-8")
    (second / "value.txt").write_text("same", encoding="utf-8")
    (second / "value.txt").touch()

    assert module._tree_sha256(first) == module._tree_sha256(second)
    (second / "value.txt").write_text("different", encoding="utf-8")
    assert module._tree_sha256(first) != module._tree_sha256(second)


def test_snapshot_round_trip_preserves_content_hash(module: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "nested").mkdir()
    (source / "nested/data.txt").write_text("payload", encoding="utf-8")
    (source / "link").symlink_to("nested/data.txt")
    archive = tmp_path / "snapshot.tar.gz"

    module._create_snapshot(source, archive)
    restored = tmp_path / "restored"
    module._restore_snapshot(archive, restored)

    assert module._tree_sha256(source) == module._tree_sha256(restored)


def test_report_markdown_keeps_claim_boundary(module: ModuleType) -> None:
    report = {
        "decision": "proceed_to_agent_continuation_qualification_design",
        "status": "completed",
        "manifest_sha256": "a" * 64,
        "manifest_canonical_sha256": "b" * 64,
        "evidence_inventory_canonical_sha256": "c" * 64,
        "summary": {
            "projects_completed": 9,
            "states_completed": 27,
            "states_attempted": 27,
            "continuations_recorded": 54,
            "successful_recorded_continuations": 54,
            "consistent_states": 27,
            "checkpoint_bindings": 27,
            "budget_conserved_states": 27,
            "stop_transfers": 3,
            "provider_requests": 0,
            "agent_calls": 0,
            "recorded_continuation_wall_clock_milliseconds": 1,
        },
        "qualification": {"gates": {"cleanup": True}},
        "audit": {"inventory_file_count": 1, "inventory_total_bytes": 2},
    }

    markdown = module._render_markdown(report)

    assert "不评价动态预算 controller" in markdown
    assert "Provider requests：`0`" in markdown


def test_restore_failure_report_requires_new_identity(module: ModuleType) -> None:
    report = {
        "decision": "stop_before_agent_continuation_and_controller_implementation",
        "status": "failed",
        "manifest_sha256": "a" * 64,
        "manifest_canonical_sha256": "b" * 64,
        "evidence_inventory_canonical_sha256": "c" * 64,
        "failure": {
            "type": "LinkOutsideDestinationError",
            "message": "合法相对符号链接被恢复器拒绝",
        },
        "failure_classification": "checkpoint_restore_infrastructure_failure",
        "summary": {
            "projects_completed": 6,
            "states_completed": 20,
            "states_attempted": 20,
            "continuations_recorded": 40,
            "successful_recorded_continuations": 40,
            "consistent_states": 20,
            "checkpoint_bindings": 20,
            "budget_conserved_states": 20,
            "stop_transfers": 2,
            "provider_requests": 0,
            "agent_calls": 0,
            "recorded_continuation_wall_clock_milliseconds": 1,
        },
        "qualification": {"gates": {"cleanup": True}},
        "audit": {"inventory_file_count": 1, "inventory_total_bytes": 2},
    }

    markdown = module._render_markdown(report)

    assert "先通过独立的 symlink-safe checkpoint restore 工程门禁" in markdown
    assert "不得续跑或补齐当前 evidence" in markdown


def test_manifest_is_valid_json_and_has_no_credential_reference(module: ModuleType) -> None:
    raw = module.MANIFEST_PATH.read_text(encoding="utf-8")
    json.loads(raw)
    lowered = raw.lower()
    assert "api_key" not in lowered
    assert "jev-apikey" not in lowered
