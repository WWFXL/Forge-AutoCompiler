"""新候选、项目隔离、真实回调装配及独立结果标签；全部零Provider。"""

import copy
import json
import sys
from collections import Counter
from pathlib import Path

import pytest
from test_recovery_harness_comparison import usage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_recovery_harness_r2_comparison as comparison  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError, PlanStep  # noqa: E402
from deerflow.compile.simple_build_task import SimpleBuildPlan  # noqa: E402


def test_new_projects_separated_from_both_optimizer_and_previous_comparison():
    tasks = comparison.base.shared.load(comparison.FIXTURE)["projects"]
    names = {p["name"] for p in tasks}
    assert len(names) == 18
    assert Counter(p["task"]["build_system"] for p in tasks) == Counter(cmake=6, make=6, autotools=6)
    assert not names & set(comparison.base.projects())
    corpus = comparison.base.shared.load(comparison.ROOT / "benchmarks/fixtures/recovery-harness-system-context-v1/corpus.json")
    serialized = json.dumps(corpus).lower()
    for item in tasks:
        assert item["task"]["repository_url"].lower() not in serialized
        assert item["task"]["image_id"] == comparison.IMAGE
        task = comparison.PublicBuildTask.model_validate(item["task"])
        reference = comparison.BuildReference.model_validate(item["reference"])
        assert reference.task_sha256 == comparison._digest(task.model_dump(mode="json"))
        assert not {"components", "reference_actions", "executable_smokes"} & task.model_dump().keys()
    assert comparison.base.shared.load(comparison.SELECTION)["excluded_before_freeze"][0]["name"] == "libui"


def test_once_per_method_interleaved_systems_and_reviewed_prompt():
    rows = comparison.schedule()
    assert len(rows) == 36
    assert set(Counter((r["project"], r["method"]) for r in rows).values()) == {1}
    assert Counter(r["method"] for r in rows[::2]) == Counter(H0=9, R2_system_context=9)
    by_name = {p["name"]: p for p in comparison.base.shared.load(comparison.FIXTURE)["projects"]}
    for i in range(0, 18, 3):
        assert {by_name[n]["task"]["build_system"] for n in comparison.project_order()[i : i + 3]} == {"cmake", "make", "autotools"}
    assert comparison.harnesses()["R2_system_context"].fingerprint() == comparison.CANDIDATE_SHA
    assert comparison.harnesses()["H0"].prompt(comparison.SIMPLE_PROMPT) == comparison.SIMPLE_PROMPT


@pytest.fixture
def pair():
    item = comparison.base.shared.load(comparison.FIXTURE)["projects"][0]
    plan = SimpleBuildPlan(task=item["task"], steps=[PlanStep(step_id="build", role="build", command="make", source="作者入口", expected="主构建")])
    value = dict(
        identity=comparison.IDENTITY,
        methods=list(comparison.METHODS),
        projects=[item],
        schedule=[dict(slot=i + 1, project=item["name"], method=m, repetition=1) for i, m in enumerate(comparison.METHODS)],
        per_unit_cost_usd="0.40",
        proposal_cost_already_paid_usd=comparison.PROPOSAL_COST,
        previous_r2_proposal_cost_already_paid_usd="0.106807",
        boundary="独立新比较",
    )
    initial = dict(status="planned", plan=plan.model_dump(mode="json"), plan_sha256=plan.fingerprint(), agent_usage=usage("0.01"), cleanup=dict(succeeded=True), arm_total_wall_seconds=10)
    auth = dict(maximum_cost_usd="5.00", deadline_utc="2099-01-01T00:00:00+00:00")
    return item, value, initial, auth


def test_reused_driver_preserves_same_plan_and_new_analysis_counts(pair, tmp_path):
    _, value, initial, auth = pair
    received = []

    def execute(**kw):
        received.append(copy.deepcopy(kw["initial_plan"]))
        kw["initial_plan"]["steps"][0]["command"] = "make different"
        return dict(status="completed", agent_usage=usage("0.02"), cleanup=dict(succeeded=True), layers=dict(main_build_task_completed=True, reproducible_delivery_completed=True), arm_total_wall_seconds=20)

    output = tmp_path / "run"
    result = comparison.base.execute(value, output, auth, lambda **kw: initial, execute)
    analysis = comparison.analyze(output)
    assert received == [initial["plan"], initial["plan"]]
    assert result["known_actual_batch_cost_usd"] == "0.05"
    assert analysis["identity"] == comparison.IDENTITY
    assert set(analysis["arms"]) == set(comparison.METHODS) and "R1" not in analysis["arms"]
    assert analysis["arms"]["H0"]["planned"] == 1
    assert analysis["arms"]["H0"]["deployment_cost_usd"] == "0.03"
    assert analysis["arms"]["R2_system_context"]["deployment_with_current_proposal_usd"] == "0.169614"
    assert analysis["arms"]["H0"]["deployment_wall_seconds"] == 30
    assert analysis["by_build_system"]["make"]["H0"]["planned"] == 0
    assert analysis["pairs"][0]["same_initial_plan"] is True


def test_initial_failure_stays_unobserved_for_both_recovery_methods(pair, tmp_path):
    _, value, initial, auth = pair
    initial["status"] = "planning_failed"
    output = tmp_path / "run"
    comparison.base.execute(value, output, auth, lambda **kw: initial, lambda **kw: pytest.fail("初始失败不能执行恢复比较"))
    analysis = comparison.analyze(output)
    for arm in analysis["arms"].values():
        assert arm["planned"] == 1 and arm["observed"] == 0 and arm["unobserved"] == 1
    assert analysis["pairs"][0]["same_initial_plan"] is None
    assert analysis["common_initial_failures"]


def test_paid_callback_dispatches_reviewed_candidate_without_live_credentials(pair, tmp_path, monkeypatch):
    item, value, initial, auth = pair
    value.update(recovery_harnesses={n: h.model_dump(mode="json") for n, h in comparison.harnesses().items()}, arm_seconds=1800, replay_seconds=600)
    auth["credentials_env_file"] = str(tmp_path / "not-present.env")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "zero-provider-test")
    monkeypatch.setattr(comparison.base, "PlanThinkingDeepSeek", lambda **kw: None)
    captured = []
    monkeypatch.setattr(comparison.base.shared, "run_simple_system", lambda **kw: captured.append(kw) or {})
    _, executor = comparison.base.paid_callbacks(value, auth)
    for method in comparison.METHODS:
        executor(slot=dict(method=method), item=item, folder=tmp_path / method, available="0.40", deadline=auth["deadline_utc"], initial_plan=initial["plan"])
        assert captured[-1]["recovery_harness"].fingerprint() == comparison.harnesses()[method].fingerprint()
        assert captured[-1]["state_router"].method == "rule"
        assert captured[-1]["initial_plan"] == initial["plan"]


def test_previous_proposal_authorization_does_not_authorize_new_comparison():
    auth = dict(identity="cpp-build-offline-recovery-harness-system-context-proposal-v1", user_reply="审核通过", candidate_sha256=comparison.CANDIDATE_SHA)
    with pytest.raises(PlanContractError, match="确切身份"):
        comparison.base.shared.validate_authorization(auth, "new-manifest", identity=comparison.IDENTITY, maximum_hours=4)


@pytest.fixture(autouse=True)
def frozen_historical_implementation(monkeypatch, tmp_path):
    from frozen_recovery_context import install_frozen_recovery_context

    install_frozen_recovery_context(monkeypatch, tmp_path, comparison, sys.modules[__name__], scoped=False)
