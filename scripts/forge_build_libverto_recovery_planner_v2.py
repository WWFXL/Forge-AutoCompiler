"""供后续新身份显式接线的恢复planner，冻结v1仍只读。"""

from forge_build_libverto_natural_recovery import revise

from deerflow.compile.plan_workflow import BuildPlan, PlanContractError


def planner_for(initial):
    def planner(**kwargs):
        current = kwargs.get("current_plan")
        if current is None:
            return BuildPlan.model_validate(initial), "重放已封存真实初始方案，不重新规划"
        handoff = kwargs["handoff"]
        if current.revision != 1 or handoff.get("plan_sha256") != current.fingerprint():
            raise PlanContractError("只允许当前初始方案的一次修订")
        if handoff.get("reason") != "step_failed_or_expectation_missing" or handoff.get("step_id") != "check":
            raise PlanContractError("非固定测试失败交接，不读取测试诊断")
        source = kwargs["source_root"]
        suite, config = source / "tests/test-suite.log", source / "config.log"
        if not suite.is_file() or not config.is_file():
            raise PlanContractError("固定测试交接缺少必需诊断文件")
        plan = revise(current, handoff, suite.read_text(), config.read_text())
        kwargs["meter"].ledger.append("qualification.natural_revision", plan_sha256=plan.fingerprint(), rule="enable_shared_preserving_static_after_six_context_assertions")
        return plan, "固定单项配置修订，其余任务和完整测试不变"

    return planner
