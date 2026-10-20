"""验证有界规则覆盖、失败Agent接管与初始规划计费路径不会被绕开。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_build_rule_recovery_qualification import case

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_full_strategy_components import planner_with_rules  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError


def test_initial_plan_always_uses_agent_and_forwards_original_inputs(tmp_path):
    agent = Mock(return_value=("plan", "reason"))
    kwargs = dict(current_plan=None, source_root=tmp_path, meter=SimpleNamespace(ledger=Mock()), task="fixed-task", model="same-model")
    assert planner_with_rules(agent)(**kwargs) == ("plan", "reason")
    agent.assert_called_once_with(**kwargs)


def test_covered_failure_uses_one_rule_then_next_failure_uses_agent(tmp_path):
    plan, handoff = case("miniz")
    agent = Mock(return_value=("agent-revised", "reason"))
    planner = planner_with_rules(agent)
    kwargs = dict(current_plan=plan, handoff=handoff, source_root=tmp_path, meter=SimpleNamespace(ledger=Mock()))
    revised, rule = planner(**kwargs)
    assert revised.revision == 2 and rule == "remove_missing_explicit_target"
    agent.assert_not_called()
    # 规则未解决后允许同预算Agent调查，不因一次规则资格失败直接停止整个策略。
    assert planner(**{**kwargs, "current_plan": revised, "handoff": {**handoff, "plan_sha256": revised.fingerprint()}}) == ("agent-revised", "reason")
    agent.assert_called_once()


def test_uncovered_failure_keeps_agent_recovery(tmp_path):
    plan, handoff = case("miniz")
    handoff["recent_commands"][-1]["output_tail"] = "unrelated linker failure"
    agent = Mock(return_value=("agent-revised", "reason"))
    assert planner_with_rules(agent)(current_plan=plan, handoff=handoff, source_root=tmp_path, meter=SimpleNamespace(ledger=Mock())) == ("agent-revised", "reason")
    agent.assert_called_once()


def test_stale_state_does_not_silently_escalate(tmp_path):
    plan, handoff = case("miniz")
    handoff["plan_sha256"] = "old"
    agent = Mock()
    with pytest.raises(PlanContractError, match="已过期"):
        planner_with_rules(agent)(current_plan=plan, handoff=handoff, source_root=tmp_path, meter=SimpleNamespace(ledger=Mock()))
    agent.assert_not_called()
