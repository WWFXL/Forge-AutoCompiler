"""让精确生成命令与附加路径观察分别执行，保持原写权限和全部检查。"""

from __future__ import annotations

import hashlib

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.unified_plan_equivalent import BuildActions, assemble_plan
from deerflow.compile.unified_plan_equivalent_observed import compile_action


def compile_generation_actions(proposal, boundary):
    declared = {(rule.command, rule.workdir) for rule in boundary.generations}
    identifiers = {action.step_id for action in proposal.steps}
    steps = []
    for action in proposal.steps:
        compiled = compile_action(action)
        if (action.command, action.workdir) in declared and (action.files_exist or action.directories_exist):
            execution_id = "generation-" + hashlib.sha256(action.step_id.encode()).hexdigest()[:20]
            if execution_id in identifiers:
                raise PlanContractError("生成执行派生ID与原动作冲突")
            identifiers.add(execution_id)
            execution = compile_action(action.model_copy(update={"step_id": execution_id, "files_exist": (), "directories_exist": ()}))
            prefix = "(\n" + action.command + "\n)\n"
            if not compiled.command.startswith(prefix):
                raise PlanContractError("原路径观察编译格式变化，不猜测生成动作")
            # 原ID表示整个动作及观察均成立，后继requires不用重写。
            observation = compiled.model_copy(update={"command": compiled.command[len(prefix) :], "requires": (execution_id,), "required_output": ()})
            steps.extend((execution, observation))
        else:
            steps.append(compiled)
    return BuildActions(reason=proposal.reason, steps=[step.model_dump() for step in steps])


def assemble_generation_actions(task, proposal, *, revision, boundary):
    return assemble_plan(task, compile_generation_actions(proposal, boundary), revision=revision)
