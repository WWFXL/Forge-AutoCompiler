"""第二轮排期、来源隔离与一次提案边界；不请求真实Provider。"""

import json
import sys
from collections import Counter
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_offline_harness_round2 as second  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def test_twelve_projects_once_and_balanced_method_positions():
    rows = second.schedule()
    assert len(rows) == 36
    assert len({r["project"] for r in rows}) == 12
    assert {r["repetition"] for r in rows} == {1}
    assert all(n == 1 for n in Counter((r["project"], r["method"]) for r in rows).values())
    assert all(n == 4 for n in Counter((r["method"], i % 3) for i, r in enumerate(rows)).values())


def test_sources_and_independent_references_are_separate():
    value = second.shared.load(second.MANIFEST)
    for item in value["projects"]:
        task = second.PublicBuildTask.model_validate(item["task"])
        reference = second.BuildReference.model_validate(item["reference"])
        assert reference.task_sha256 == second._digest(task.model_dump(mode="json"))
    corpus = second.shared.load(second.CORPUS)
    assert len(corpus["episodes"]) == 24
    assert not set(second.PROJECTS) & second.EXCLUDED_FAMILIES
    assert all(p["task"]["task_version"] == "main-build-v1" for p in value["projects"])
    assert all("reference" not in e["task"] for e in corpus["episodes"])
    assert value["original_h1"]["planning_guidance"] == value["previous_harness"]["planning_guidance"]
    assert value["baseline"]["base_prompt_sha256"] == value["previous_harness"]["base_prompt_sha256"]


class OnceModel:
    def __init__(self, response):
        self.response, self.calls = response, 0

    def invoke(self, messages):
        self.calls += 1
        return self.response


def test_no_change_stops_without_inventing_comparison_success(tmp_path):
    model = OnceModel(AIMessage(content=json.dumps(dict(diagnoses=[], planning_guidance="", no_change=True)), usage_metadata=dict(input_tokens=100, output_tokens=20, total_tokens=120), response_metadata=dict(model_name="gpt-5.6")))
    harness, usage = second.optimize(second.shared.load(second.MANIFEST), tmp_path / "optimizer", model)
    assert model.calls == 1 and harness.name == "H0"
    assert usage["estimated_cost_usd_completed_responses"] == "0.00012"
    (tmp_path / "no-change.json").write_text("{}")
    result = second.analyze(tmp_path)
    assert result["status"] == "no_change" and result["observed_comparisons"] == 0
    assert result["unobserved_comparisons"] == 36 and result["treatment_effect"] is None


def test_unknown_usage_stops_after_one_request(tmp_path):
    model = OnceModel(AIMessage(content="{}", response_metadata=dict(model_name="gpt-5.6")))
    with pytest.raises(PlanContractError, match="用量未知"):
        second.optimize(second.shared.load(second.MANIFEST), tmp_path / "optimizer", model)
    assert model.calls == 1
    assert second.shared.load(tmp_path / "optimizer/failure.json")["unknown_usage"]


def test_candidate_is_bound_to_current_source_files():
    value = second.shared.load(second.MANIFEST)
    value["schedule"][0]["repetition"] = 2
    with pytest.raises(PlanContractError, match="排期变化"):
        second.validate(value)
