"""完整策略比较的有界规则接管；无运行入口，不隐式启动Provider。"""

from forge_build_rule_recovery_qualification import rule_revision

from deerflow.compile.plan_agent_context import propose_with_context


def planner_with_rules(agent_planner=propose_with_context):
    """每条独立构建路径最多一次规则修订，其余交由相同的规划Agent。"""
    used_rule = False

    def planner(**kwargs):
        nonlocal used_rule
        plan = kwargs.get("current_plan")
        meter = kwargs["meter"]
        if plan is not None and not used_rule:
            source = kwargs["source_root"]
            names = {name for name in ("configure.ac", "Makefile.am", "autogen.sh") if (source / name).is_file()}
            candidate = rule_revision(plan, kwargs["handoff"], names)
            if candidate is not None:
                revised, rule = candidate
                used_rule = True
                meter.ledger.append("strategy.rule_revision", rule=rule, plan_sha256=revised.fingerprint())
                return revised, rule
        meter.ledger.append("strategy.agent_planner", phase="initial" if plan is None else "recovery", rule_already_used=used_rule)
        return agent_planner(**kwargs)

    return planner
