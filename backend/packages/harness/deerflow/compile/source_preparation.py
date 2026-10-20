"""归档源码的共同Git索引准备；所有策略与干净重放使用同一显式步骤。"""

from __future__ import annotations

import hashlib
import json
import shlex

from deerflow.compile.plan_agent_canary import CanaryWorkflow
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError, PlanStep

PREPARATION_ID = "forge-source-prepare"


def paths_fingerprint(paths) -> str:
    return hashlib.sha256(json.dumps(sorted(paths), ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def index_check_script(expected: str) -> str:
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise PlanContractError("源码文件集合指纹必须是SHA256")
    return f"""import hashlib,json,subprocess
rows=subprocess.run(['git','ls-files','-z'],check=True,capture_output=True).stdout.decode().split('\\0')
assert rows[-1]=='', 'Git索引输出不完整'
names=rows[:-1]
actual=hashlib.sha256(json.dumps(sorted(names),ensure_ascii=True,separators=(',',':')).encode()).hexdigest()
assert actual=={expected!r}, 'Git索引文件集合与固定原源码不同'
assert subprocess.run(['git','rev-parse','--verify','HEAD'],capture_output=True).returncode!=0, '不允许伪造源码commit'
print('FORGE_SOURCE_INDEX_VERIFIED='+actual)
"""


def index_check_command(expected: str) -> str:
    return "python3 -c " + shlex.quote(index_check_script(expected))


def preparation_step(expected: str) -> PlanStep:
    script = """from pathlib import Path
import subprocess
assert str(Path.cwd())=='/workspace/repo', '准备目录必须是容器仓库根'
assert not Path('.git').exists(), '归档源码不得包含既有Git身份'
subprocess.run(['git','init','-q'],check=True)
subprocess.run(['git','config','--global','--add','safe.directory','/workspace/repo'],check=True)
subprocess.run(['git','add','--force','--all'],check=True)
""" + index_check_script(expected)
    return PlanStep(
        step_id=PREPARATION_ID,
        role="dependency",
        command="python3 -c " + shlex.quote(script),
        source="系统共同来源准备：归档原文件集合；无人工构建配方、无伪commit",
        expected="原执行与clean replay均在首次构建动作前准备相同源码索引",
        required_output=("FORGE_SOURCE_INDEX_VERIFIED=" + expected,),
    )


def with_preparation(plan: BuildPlan, expected: str) -> BuildPlan:
    if any(s.step_id == PREPARATION_ID for s in plan.steps):
        raise PlanContractError("模型/工具动作不得覆盖系统源码准备步骤")
    return BuildPlan.model_validate({**plan.model_dump(), "steps": (preparation_step(expected), *plan.steps)})


class PreparedWorkflow(CanaryWorkflow):
    """将首次规划前已执行的共同命令绑定为成功前缀，原验收会显式重放它。"""

    def __init__(self, *, preparation_command_id: str, **kwargs):
        super().__init__(**kwargs)
        step = self.plan.steps[0]
        records = [r for r in self._session.commands if r.command_id == preparation_command_id]
        if step.step_id != PREPARATION_ID or len(records) != 1:
            raise PlanContractError("共同来源准备缺少唯一权威记录")
        record = records[0]
        if (record.command, record.role, record.workdir, record.exit_code, record.timed_out) != (step.command, step.role, step.workdir, 0, False):
            raise PlanContractError("共同来源准备记录与方案不符")
        self.completed[PREPARATION_ID] = preparation_command_id
        self.commands_used = 1
        self._persist()
