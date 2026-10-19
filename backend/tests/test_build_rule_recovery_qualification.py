"""强规则只接受明确且未过期的失败，不改变固定测试或任务身份。"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_build_plan_recovery_qualification import reference

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rule_recovery_qualification import NoProviderMeter, controlled_plan, rule_revision  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def case(name):
    plan = controlled_plan(reference(name), name)
    failed = next(s for s in plan.steps if s.step_id == ("configure" if name == "libite" else "build"))
    logs = {
        "miniz": "gmake: *** No rule to make target 'forge_missing_target_qualification'. Stop.",
        "pigz": "make: forge_missing_compiler_qualification: No such file or directory",
        "libite": "bash: line 2: ./configure: No such file or directory",
    }
    handoff = {"plan_sha256": plan.fingerprint(), "reason": "step_failed_or_expectation_missing", "step_id": failed.step_id, "recent_commands": [{"command": failed.command, "exit_code": 2, "timed_out": False, "output_tail": logs[name]}]}
    return plan, handoff


@pytest.mark.parametrize("name", ["miniz", "pigz", "libite"])
def test_rule_repairs_only_one_command_while_preserving_identity_and_fixed_tests(name):
    plan, handoff = case(name)
    revised, reason = rule_revision(plan, handoff, {"configure.ac", "Makefile.am", "autogen.sh"})
    assert reason and revised.revision == 2
    assert revised.model_dump(exclude={"revision", "steps"}) == plan.model_dump(exclude={"revision", "steps"})
    assert [s for s in revised.steps if s.role == "smoke"] == [s for s in plan.steps if s.role == "smoke"]
    assert sum(a.command != b.command for a, b in zip(plan.steps, revised.steps)) == 1
    assert "forge_missing" not in " ".join(s.command for s in revised.steps)


@pytest.mark.parametrize("name", ["miniz", "pigz", "libite"])
def test_similar_failure_without_exact_error_evidence_abstains(name):
    plan, handoff = case(name)
    handoff["recent_commands"][-1]["output_tail"] = "unrelated linker error"
    assert rule_revision(plan, handoff, {"configure.ac", "Makefile.am", "autogen.sh"}) is None


def test_stale_state_and_timeout_cannot_trigger_direct_rule():
    plan, handoff = case("miniz")
    handoff["plan_sha256"] = "0" * 64
    with pytest.raises(PlanContractError, match="已过期"):
        rule_revision(plan, handoff, set())
    handoff["plan_sha256"] = plan.fingerprint()
    handoff["recent_commands"][-1]["timed_out"] = True
    assert rule_revision(plan, handoff, set()) is None


def test_missing_project_bootstrap_evidence_abstains():
    plan, handoff = case("libite")
    assert rule_revision(plan, handoff, {"configure.ac", "Makefile.am"}) is None


def test_meter_prohibits_model_before_request_accounting(tmp_path):
    meter = NoProviderMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("scripted-gate",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: {})
    with pytest.raises(PlanContractError, match="禁止任何模型请求"):
        meter._before_request()
    assert meter.summary()["model_requests"] == 0
    assert meter.tracker.limits.node_timeout_seconds == 300
