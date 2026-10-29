"""新样本比较只检查任务、分母和既有方法复用；不访问Provider或本机归档。"""

import json
import shlex
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_new_project_comparison as new  # noqa: E402


def test_new_sample_has_balanced_pairs_and_does_not_change_method_components():
    candidate = new.candidate_for()
    parent = new.base.load(new.system.MANIFEST)
    assert len(candidate["schedule"]) == 42
    assert Counter(row["method"] for row in candidate["schedule"]) == dict.fromkeys(new.system.METHODS, 14)
    assert all(count == 2 for count in Counter((row["project"], row["method"]) for row in candidate["schedule"]).values())
    assert all(candidate[key] == parent[key] for key in ("provider", "pricing", "runtime", "timing_policy", "baseline", "methods", "dependency_runtime"))
    assert all(candidate["components"][name] == digest for name, digest in parent["components"].items())
    assert not any(key in candidate for key in ("prior_qualification", "prior_replication_exposure", "reference"))
    assert set(candidate["source_index_contracts"]) == {item["name"] for item in candidate["projects"]}


def test_original_conditional_skip_is_visible_and_not_counted_as_method_failure():
    selection = new.base.load(new.SELECTION)
    reference = next(row for row in selection["projects"] if row["name"] == "libxcrypt")
    assert len(selection["projects"]) == 8
    assert reference["role"] == "reference_only_upstream_conditional_skip"
    assert "47 PASS/1 SKIP" in reference["reason"]
    candidate = new.candidate_for()
    assert "libxcrypt" not in {row["project"] for row in candidate["schedule"]}
    assert not candidate["holdout"]


def test_tasks_keep_author_test_scope_and_cmake_goals_available_to_all_methods():
    candidate = new.candidate_for()
    projects = {item["name"]: item for item in candidate["projects"]}
    assert Counter(item["task"]["build_system"] for item in projects.values()) == dict(cmake=3, make=2, autotools=2)
    for item in projects.values():
        task = new.base.PlanTask.model_validate(item["task"])
        assert new.system.common_task(item)["task"] == item["task"]
        assert task.verification_steps[-1].required_output
        if task.build_system == "cmake":
            assert new.system.configuration_goals(task)
            assert "c.find('skipped') is None" in "\n".join(shlex.split(task.verification_steps[-1].command))
    assert "--test-dir build -j1 " in projects["jsoncpp"]["task"]["verification_steps"][-1]["command"]
    assert "text.count('All 131072 tests passed')==2" in "\n".join(shlex.split(projects["fse"]["task"]["verification_steps"][-1]["command"]))
    assert "len(files)==32" in projects["libsigcplusplus"]["task"]["verification_steps"][-1]["command"]


def test_analysis_uses_new_frozen_denominator_and_keeps_unobserved(tmp_path):
    method = new.system.METHODS[0]
    schedule = new.candidate_for()["schedule"]
    row = dict(method=method, strict_completed=False, agent_usage=dict(model_requests=2, estimated_cost_usd_completed_responses="0.02"), arm_total_wall_seconds=12)
    (tmp_path / "protocol.json").write_text(json.dumps(dict(schedule=schedule)))
    (tmp_path / "result.json").write_text(json.dumps(dict(identity=new.IDENTITY, rows=[row], unobserved_schedule=schedule[1:], stop_reason="operator_stop")))
    result = new.analyze(tmp_path)
    assert result["summary"][method]["planned"] == 14
    assert result["summary"][method]["observed"] == 1
    assert result["summary"][method]["unobserved"] == 13
    assert result["summary"][method]["complete"] == 0
    assert result["summary"][method]["known_cost_usd"] == "0.02"
    assert all(summary["planned"] == 14 for summary in result["summary"].values())
