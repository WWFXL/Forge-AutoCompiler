"""新身份门禁的固定分母与原任务隔离检查。"""

import ast
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import forge_build_cxx_common_input_gate as gate  # noqa: E402


def test_eleven_slots_keep_all_three_methods_and_two_recoveries():
    rows = gate.schedule()
    assert len(rows) == 11
    assert len([r for r in rows if r["case"] == "command_recovery"]) == 2
    for name in gate.PROJECTS:
        assert {r["method"] for r in rows if r["project"] == name} == set(gate.METHODS)


def test_task_change_is_functional_and_does_not_mutate_reference(tmp_path):
    from test_plan_workflow import make_plan

    index = tmp_path / "hashes.json"
    index.write_text(json.dumps({"CMakeLists.txt": "1" * 64}))
    item = {"name": "simdutf", "plan": make_plan().model_dump(mode="json"), "source_archive": "not-executed.tar", "source_file_hashes_path": str(index)}
    item["plan"]["source_archive_sha256"] = "2" * 64
    before = copy.deepcopy(item)
    project, reference = gate.task_and_reference(item)
    assert item == before
    check = project["task"]["verification_steps"][0]
    assert "ctest --test-dir build --output-on-failure --no-tests=error --verbose" in check["command"]
    assert "FORGE_CTEST_ACTUALLY_PASSED=94" in check["required_output"]
    assert "--output-junit" in check["command"]
    assert check == next(s for s in reference["steps"] if s["role"] == "smoke")
    assert project["task"]["artifact_paths"] == item["plan"]["artifact_paths"]


def test_adapter_prepares_before_initial_planner_and_keeps_recovery_prefix():
    # 同时由真实Docker门禁验证执行；这里防止后续接线挪到规划之后。
    source = (REPO / "scripts/forge_build_prepared_arm.py").read_text()
    ast.parse(source)
    assert source.index("preparation_service.execute(") < source.index("plan, _ = planner(")
    assert "plan = with_preparation(plan, expected_source_paths)" in source
    assert "revised = with_preparation(revised, expected_source_paths)" in source
    assert 'preparation_command_id=prepared["command_id"]' in source


def test_gate_has_no_provider_or_credential_execution_path():
    tree = ast.parse(Path(gate.__file__).read_text())
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "PlanThinkingDeepSeek" not in names
    assert "SharedResearchBudget" not in names
    assert "DEEPSEEK_API_KEY" not in Path(gate.__file__).read_text()
