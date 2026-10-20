"""类型明确的观察与同等性暂存共享装配；旧实验接口保持冻结。"""

from __future__ import annotations

import json
import shlex
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from langchain.agents import create_agent
from langchain.agents.structured_output import StructuredOutputValidationError, ToolStrategy
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from deerflow.compile.plan_agent import PlanResponseCapture
from deerflow.compile.plan_agent_context import safe_readonly_tools
from deerflow.compile.plan_workflow import PlanContractError, PlanStep
from deerflow.compile.unified_plan_equivalent import PROMPT, BuildActions, assemble_plan, tool_actions, unified_planner, validate_recovery


def relative_path(value: str, *, directory: bool = False) -> str:
    # 只删除目录的尾斜杠，不折叠 ../、双斜杠或 ./，避免掩盖错误。
    normalized = value.rstrip("/") if directory and not value.startswith("/") else value
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or path.as_posix() != normalized or path.as_posix() == "." or ".." in path.parts or "\\" in normalized or ":" in normalized or "\x00" in normalized:
        raise ValueError("必须使用工作目录内的规范POSIX相对路径；目录仅允许省略尾斜杠")
    return normalized


class ObservedBuildAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    role: Literal["dependency", "configure", "build"]
    command: str = Field(min_length=1)
    source: str = Field(min_length=1)
    expected: str = Field(min_length=1, description="说明文字，不参与成功判定")
    workdir: str = "/workspace/repo"
    requires: tuple[str, ...] = ()
    stdout_contains: tuple[str, ...] = Field(default=(), description="命令日志必须实际包含的字面文本。不要填文件路径；不确定时留空。例如 Configuring done。")
    files_exist: tuple[str, ...] = Field(default=(), description="执行后必须存在的普通文件，相对workdir。例如 build/CMakeCache.txt，不要求该路径出现在日志。")
    directories_exist: tuple[str, ...] = Field(default=(), description="执行后必须存在的目录，相对workdir。例如 build/。允许安全目录尾斜杠。")
    diagnostic_paths: tuple[str, ...] = Field(default=(), description="失败后尝试采集的诊断文件；不是成功断言。目录不递归复制。")

    @field_validator("files_exist")
    @classmethod
    def files(cls, values):
        return tuple(relative_path(v) for v in values)

    @field_validator("directories_exist", "diagnostic_paths")
    @classmethod
    def directories(cls, values):
        return tuple(relative_path(v, directory=True) for v in values)

    @model_validator(mode="after")
    def validate_step(self) -> Self:
        # 复用原执行目录、输出非空等安全约束；不提供旧required_output字段。
        PlanStep(**self.model_dump(exclude={"stdout_contains", "files_exist", "directories_exist"}), required_output=self.stdout_contains)
        return self


class ObservedBuildActions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)
    steps: list[ObservedBuildAction] = Field(min_length=1)

    @model_validator(mode="after")
    def order(self) -> Self:
        seen, rank = set(), -1
        for step in self.steps:
            current = {"dependency": 0, "configure": 1, "build": 2}[step.role]
            if current < rank or step.step_id in seen or not set(step.requires).issubset(seen):
                raise ValueError("依赖→配置→编译必须按顺序返回；标识唯一且requires只能引用更早步骤，系统不会自动重排")
            seen.add(step.step_id)
            rank = current
        if self.steps[-1].step_id != "build" or self.steps[-1].role != "build":
            raise ValueError("最后步骤必须是step_id=build的编译动作")
        return self


def compile_action(action: ObservedBuildAction) -> PlanStep:
    """把确定性文件检查纳入显式命令，原执行和clean replay执行同一检查。"""
    value = action.model_dump(exclude={"stdout_contains", "files_exist", "directories_exist"})
    if action.files_exist or action.directories_exist:
        checks = [("file", p) for p in action.files_exist] + [("directory", p) for p in action.directories_exist]
        script = """import json,pathlib,sys
root=pathlib.Path.cwd().resolve(); rows=[]
for kind,name in CHECKS:
 p=(root/name).resolve(); inside=p.is_relative_to(root)
 passed=inside and (p.is_file() if kind=='file' else p.is_dir())
 rows.append({'kind':kind,'path':name,'passed':passed,'inside_workdir':inside})
print('FORGE_PATH_OBSERVATIONS='+json.dumps(rows,sort_keys=True))
sys.exit(0 if all(r['passed'] for r in rows) else 86)
""".replace("CHECKS", repr(checks))
        # 严格Shell先执行原命令，失败即停止；检查不能覆盖原非零退出码。
        value["command"] = "(\n" + action.command + "\n)\npython3 -c " + shlex.quote(script)
    return PlanStep(**value, required_output=action.stdout_contains)


def assemble_observed(task, proposal: ObservedBuildActions, *, revision: int):
    return assemble_plan(task, BuildActions(reason=proposal.reason, steps=[compile_action(s).model_dump() for s in proposal.steps]), revision=revision)


def observed_tool_actions(task, source_root):
    original, receipt = tool_actions(task, source_root)
    steps = []
    for step in original.steps:
        value = step.model_dump()
        value["stdout_contains"] = value.pop("required_output")
        steps.append(value)
    return ObservedBuildActions(reason=original.reason, steps=steps), receipt


def execution_changed(before, after):
    keys = ("step_id", "role", "command", "workdir", "requires", "required_output")
    return [[getattr(s, k) for k in keys] for s in before.steps] != [[getattr(s, k) for k in keys] for s in after.steps]


def recovery_feedback(current_plan, handoff):
    if current_plan is None:
        return None
    step = next((s for s in current_plan.steps if s.step_id == handoff.get("step_id")), None)
    record = next((r for r in reversed(handoff.get("recent_commands", [])) if step and (r.get("command"), r.get("role"), r.get("workdir")) == (step.command, step.role, step.workdir)), None)
    if record is None:
        return {"category": handoff.get("reason"), "detail": "按权威交接和原始日志判断；没有可匹配的步骤记录"}
    path = Path(record["log_path"]) if record.get("log_path") else None
    # handoff已投影日志为容器路径；完整内容由只读工具读取，预览只用于明确反馈。
    output = path.read_text(errors="replace") if path and path.is_file() else record.get("output_tail", "")
    failed = record.get("exit_code") != 0 or record.get("timed_out")
    return {
        "category": "command_failed" if failed else "output_expectation_missing",
        "command_id": record.get("command_id"),
        "exit_code": record.get("exit_code"),
        "missing_stdout_in_preview": [v for v in step.required_output if v not in output],
        "detail": "非零退出可能来自原构建命令或显式文件检查，请读取完整日志" if failed else "命令exit0；仅日志断言未满足，不能据此声称编译命令失败。文件存在性应使用files_exist/directories_exist。",
    }


OBSERVED_PROMPT = (
    PROMPT
    + """
本版本响应必须为ObservedBuildActions，禁止旧required_output字段。
stdout_contains只表示日志字面文本；files_exist表示文件存在；directories_exist表示目录存在，均相对workdir。
例如CMake配置的files_exist=["build/CMakeCache.txt"]，directories_exist=["build/"]；不要求路径出现在日志。
没有可靠日志断言时stdout_contains留空；实际测试仍由系统固定且不可删减。expected/source只是说明。
目录仅安全删除尾斜杠，不自动重排阶段、不猜测旧字段含义。诊断路径不参与成功判定。
恢复必须改变命令、前提或可执行检查；只修改reason/source/expected不能恢复。不要为通过而删除有效检查。
结构或装配错误最多给予一次明确纠错机会，全部模型请求/读取/失败/输出仍计入同一预算；Provider异常立即向上传播。
"""
)


def propose_observed(*, model, task, source_root, session_root, meter, current_plan=None, handoff=None):
    validate_recovery(task, current_plan, handoff)
    revision = current_plan.revision + 1 if current_plan else 1
    meter.requires_structured_response = True
    meter.ledger.append("agent.started", revision=revision, recovery=current_plan is not None, contract="ObservedBuildActions")
    feedback = recovery_feedback(current_plan, handoff)
    messages = [HumanMessage(content="请返回完整构建动作。额外权威恢复说明：" + json.dumps(feedback, ensure_ascii=False))]
    agent = create_agent(model=model, tools=safe_readonly_tools(source_root, session_root), system_prompt=OBSERVED_PROMPT, middleware=[meter], response_format=ToolStrategy(ObservedBuildActions, handle_errors=False))
    for correction in range(2):
        proposal = None
        try:
            result = agent.invoke({"messages": messages}, config={"max_concurrency": 1, "recursion_limit": 100, "callbacks": [PlanResponseCapture(meter)]})
            proposal = result.get("structured_response")
            if not isinstance(proposal, ObservedBuildActions):
                raise PlanContractError("未返回ObservedBuildActions")
            meter.ledger.save(f"observed-actions-{revision}-{correction}.json", proposal.model_dump(mode="json"))
            plan = assemble_observed(task, proposal, revision=revision)
            if current_plan is not None and not execution_changed(current_plan, plan):
                raise PlanContractError("no_execution_change：仅修改说明不能修复；必须根据真实失败改变动作或检查")
        except (ValidationError, StructuredOutputValidationError, PlanContractError) as exc:
            # 仅处理结构/装配/无变化建议，不捕获Provider、计量或预算异常。
            # PlanContractError也可能来自meter；只有已得到proposal的装配错误允许纠错。
            if isinstance(exc, PlanContractError) and proposal is None:
                raise
            detail = str(exc)[:6000]
            meter.ledger.append("observed.proposal_rejected", revision=revision, correction=correction, category=type(exc).__name__, detail=detail)
            if correction:
                raise
            messages.append(HumanMessage(content="上次建议结构/装配不合法，尚未执行。仅允许一次纠错，保持原任务和验收。错误：" + detail))
            continue
        return plan, proposal.reason
    raise PlanContractError("有界纠错结束")


def observed_planner(source, *, agent=propose_observed, generator=observed_tool_actions):
    def compiled_generator(task, source_root):
        actions, receipt = generator(task, source_root)
        return BuildActions(reason=actions.reason, steps=[compile_action(s).model_dump() for s in actions.steps]), receipt

    return unified_planner(source, agent=agent, generator=compiled_generator)
