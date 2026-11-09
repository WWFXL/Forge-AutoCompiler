"""共同初始方案、完整费用和中断分母；使用脚本模型，不调用Provider。"""

import copy
import io
import json
import sys
import tarfile
from collections import Counter
from pathlib import Path

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_simple_build import simple_actions

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_recovery_harness_comparison as comparison  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError, PlanStep  # noqa: E402


def usage(cost, requests=1, unknown=0):
    return dict(estimated_cost_usd_completed_responses=cost, model_requests=requests, unknown_usage_requests=unknown)


@pytest.fixture
def pair():
    item = comparison.shared.load(comparison.FIXTURE)["projects"][0]
    plan = comparison.SimpleBuildPlan(task=item["task"], steps=[PlanStep(step_id="build", role="build", command="make", source="作者入口", expected="构建主库")])
    value = dict(identity=comparison.IDENTITY, projects=[item], schedule=[dict(slot=i + 1, project=item["name"], method=m, repetition=1) for i, m in enumerate(comparison.METHODS)], per_unit_cost_usd="0.40")
    auth = dict(maximum_cost_usd="5.00", deadline_utc="2099-01-01T00:00:00+00:00")
    initial = dict(status="planned", plan=plan.model_dump(mode="json"), plan_sha256=plan.fingerprint(), agent_usage=usage("0.01"), cleanup=dict(succeeded=True), arm_total_wall_seconds=10)
    return item, value, auth, initial


def test_new_projects_once_same_methods_and_balanced_order():
    rows = comparison.schedule()
    assert len(rows) == 36 and len(comparison.projects()) == 18
    assert set(Counter((r["project"], r["method"]) for r in rows).values()) == {1}
    assert Counter(r["method"] for r in rows[::2]) == Counter(H0=9, R1=9)
    tasks = comparison.shared.load(comparison.FIXTURE)["projects"]
    by_name = {p["name"]: p for p in tasks}
    for i in range(0, 18, 3):
        assert {by_name[n]["task"]["build_system"] for n in comparison.projects()[i : i + 3]} == {"cmake", "make", "autotools"}
    assert comparison.harnesses()["R1"].fingerprint() == comparison.CANDIDATE_SHA
    assert comparison.harnesses()["H0"].prompt(comparison.SIMPLE_PROMPT) == comparison.SIMPLE_PROMPT


def test_reference_declarations_match_sources_and_do_not_enter_public_task():
    fixture = comparison.shared.load(comparison.FIXTURE)
    definitions = comparison.FIXTURE.with_name("definitions.json")
    assert comparison.digest(definitions) == fixture["definition_sha256"]
    optimizer_projects = {e["repository_url"].lower() for e in comparison.shared.load(comparison.REVIEWED / "corpus.json")["episodes"]}
    assert not optimizer_projects & {p["task"]["repository_url"].lower() for p in fixture["projects"]}
    for item in fixture["projects"]:
        task = comparison.PublicBuildTask.model_validate(item["task"])
        reference = comparison.BuildReference.model_validate(item["reference"])
        assert reference.task_sha256 == comparison._digest(task.model_dump(mode="json"))
        assert "components" not in task.model_dump() and "reference_actions" not in task.model_dump()
        assert item["source_evidence"]
        assert all(e["quote"] and len(e["sha256"]) == 64 for e in item["source_evidence"])


def test_common_plan_paid_once_but_each_deployment_pays_initial(pair, tmp_path):
    item, value, auth, initial = pair
    calls, plans = [], []

    def planner(**kwargs):
        calls.append(kwargs["item"]["name"])
        return initial

    def executor(**kwargs):
        plans.append(copy.deepcopy(kwargs["initial_plan"]))
        # 模拟第一处理内部修订，不得改变第二处理的共同初始方案。
        kwargs["initial_plan"]["steps"][0]["command"] = "make modified"
        return dict(status="completed", agent_usage=usage("0.02"), cleanup=dict(succeeded=True), layers=dict(main_build_task_completed=True, reproducible_delivery_completed=True), arm_total_wall_seconds=20)

    result = comparison.execute(value, tmp_path / "run", auth, planner, executor)
    assert calls == [item["name"]] and plans[0] == plans[1] == initial["plan"]
    assert result["known_actual_batch_cost_usd"] == "0.05" and result["completed_slots"] == 2
    analysis = comparison.analyze(tmp_path / "run")
    assert analysis["arms"]["H0"]["deployment_cost_usd"] == "0.03"
    assert analysis["arms"]["R1"]["deployment_with_proposal_usd"] == "0.135856"
    assert analysis["pairs"][0]["complete_pair"] and analysis["pairs"][0]["same_initial_plan"]


@pytest.mark.parametrize("unknown", [False, True])
def test_initial_failure_does_not_invent_two_recovery_failures(pair, tmp_path, unknown):
    _, value, auth, initial = pair
    initial.update(status="planning_failed", agent_usage=usage("0.01", unknown=int(unknown)))

    def no_execution(**kwargs):
        pytest.fail("共同规划失败，恢复处理不能假装已经执行")

    result = comparison.execute(value, tmp_path / "run", auth, lambda **kw: initial, no_execution)
    assert result["completed_slots"] == 0 and len(result["unobserved"]) == 2
    assert result["stop_reason"] == ("unknown_usage" if unknown else None)
    assert result["billing_complete"] != unknown
    assert comparison.analyze(tmp_path / "run")["pairs"][0]["same_initial_plan"] is None


@pytest.mark.parametrize("failure", ["cleanup", "unknown", "identity"])
def test_arm_global_failures_stop_before_second_method(pair, tmp_path, failure):
    _, value, auth, initial = pair

    def executor(**kwargs):
        folder = kwargs["folder"]
        (folder / "agent").mkdir(parents=True)
        if failure == "identity":
            (folder / "agent/events.jsonl").write_text(json.dumps(dict(event="model.identity_mismatch")) + "\n")
        return dict(status="error", agent_usage=usage("0.02", unknown=int(failure == "unknown")), cleanup=dict(succeeded=failure != "cleanup"))

    result = comparison.execute(value, tmp_path / "run", auth, lambda **kw: initial, executor)
    assert result["completed_slots"] == 1 and len(result["unobserved"]) == 1
    assert result["stop_reason"] == {"cleanup": "cleanup_failure", "unknown": "unknown_usage", "identity": "model_identity_mismatch"}[failure]


def test_closed_output_is_never_restarted_or_resealed(pair, tmp_path):
    _, value, auth, initial = pair
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "result.json"
    marker.write_text("original failed evidence")
    with pytest.raises(FileExistsError):
        comparison.execute(value, output, auth, lambda **kw: initial, lambda **kw: {})
    assert marker.read_text() == "original failed evidence"


def test_real_planning_graph_is_h0_and_does_not_see_reference(pair, tmp_path):
    item, _, _, _ = pair
    item = copy.deepcopy(item)
    archive_path = tmp_path / "source.tar"
    with tarfile.open(archive_path, "w") as archive:
        body = b"Author ordinary build: make\n"
        member = tarfile.TarInfo("README.md")
        member.size = len(body)
        archive.addfile(member, io.BytesIO(body))
    item["source_archive"] = str(archive_path)
    item["task"]["source_archive_sha256"] = comparison.digest(archive_path)
    model = ScriptedPlanModel(responses=[response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    result = comparison.plan_once(item=item, folder=tmp_path / "initial", model=model, available="0.40", deadline="2099-01-01T00:00:00+00:00", accepted_models=("test-model",))
    assert result["status"] == "planned" and result["agent_usage"]["model_requests"] == 1
    request = comparison.shared.load(tmp_path / "initial/agent/request-1.json")
    assert request["system_message"]["content"] == comparison.SIMPLE_PROMPT
    assert "reference_actions" not in json.dumps(request) and "source_evidence" not in json.dumps(request)


def test_expired_or_different_experiment_authorization_is_rejected():
    with pytest.raises(PlanContractError, match="确切身份"):
        comparison.shared.validate_authorization(dict(identity="old", candidate_sha256="old", user_reply="授权"), "new", identity=comparison.IDENTITY, maximum_hours=4)
