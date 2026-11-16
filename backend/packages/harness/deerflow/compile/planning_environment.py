"""初始规划的真实容器依赖查询；安装动作仍由Workflow执行。"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_environment import environment_tools, query_command
from deerflow.compile.schemas import BuildCommandRecord, CommandResult, utc_now_iso

PLANNING_DEPENDENCY_VERSION = "planning-dependency-check-v1"
PLANNING_DEPENDENCY_PROMPT = """
规划前可用search_build_files和inspect_build_environment核实实际编译容器的依赖状态。
先从README/INSTALL、CI和构建声明（如configure.ac、CMakeLists.txt、pkg-config要求）识别主要构建所需工具、开发库及宏，不为可选示例/完整测试额外安装依赖。
针对明确依赖线索查询：command查工具版本，package查安装状态，package_search查包名和描述，package_description核实用途；知道头文件/宏文件名后用package_file_search查提供包，不能用宏名代替文件名。search_build_files可搜索项目声明及已安装宏/头文件/pkgconfig；需要时核实版本和search_paths。
将源码声明、真实查询和已验证经验结合，区分缺包、路径未生效与版本不兼容；本地目录无命中不证明功能被删除，索引缺失也不证明没有提供包。不要凭猜测降级工具或伪造宏。
已确认缺失的必要依赖写入dependency步骤（如apt-get update及apt-get install -y --no-install-recommends的具体包），路径修正写入相应步骤，然后安排原配置生成、配置、编译。查询不会安装包；安装必须交给Workflow执行。
依赖已满足就直接生成构建方案；不要机械遍历所有依赖或重复同一查询。证据足够即提交SimpleBuildActions，保留无法预知的错误供执行后恢复。
"""


class PlanningEnvironment:
    """只在初始方案生成期间有效，使用原容器、命令日志及任务预算。"""

    dependency_diagnosis = None

    def __init__(self, *, session, manager, runtime, meter):
        self.session_id, self.thread_id = session.session_id, session.thread_id
        self.source_root = Path(session.leadagent_repo_dir).resolve()
        self.session_root = Path(session.metadata_path).parent.resolve()
        self.manager, self.runtime, self.meter = manager, runtime, meter
        self.calls = 0
        self.seconds = 0.0
        self.closed = False

    def tools(self):
        return environment_tools(self)

    def close(self):
        self.closed = True

    def execute(self, operation, query, **kwargs):
        try:
            command = query_command(operation, query, **kwargs)
        except ValueError as exc:
            return dict(status="invalid_query", reason=str(exc))
        with self.manager.session_lock(self.thread_id, self.session_id):
            session = self.manager.load_session(self.session_id, self.thread_id)
            if self.closed or session.status != "inspected" or any(c.stage != "planning_dependency" for c in session.commands):
                raise PlanContractError("规划查询只允许在初始方案生成期间使用")
            if self.calls >= 12:
                return dict(status="budget_exhausted", reason="规划查询额度已用完，请依据现有证据提交方案")
            self.meter.tracker.observe_elapsed(time.monotonic() - self.meter.started_monotonic)
            remaining = self.meter.tracker.remaining().node_seconds
            if remaining < 1:
                raise PlanContractError("规划查询前任务时间已耗尽")
            self.meter.tracker.consume(commands=1)
            self.calls += 1
            timeout = min(25 if kwargs.get("kind") == "package_file_search" else 15, int(remaining))
            record = BuildCommandRecord(stage="planning_dependency", role="diagnostic", command=command, workdir="/workspace/repo", timeout_seconds=timeout)
            record.log_path = str(self.manager.local_logs_dir(session) / (record.command_id + ".log"))
            started = time.monotonic()
            try:
                output = self.runtime.exec(session, command, workdir=record.workdir, timeout_seconds=timeout, log_path=record.log_path, strict_shell=True)
            except subprocess.TimeoutExpired as exc:
                Path(record.log_path).write_text(str(exc))
                output = CommandResult(124, "", str(exc), str(exc), record.log_path)
            finally:
                self.seconds += time.monotonic() - started
            record.exit_code, record.timed_out = output.exit_code, output.exit_code == 124
            record.termination = "timeout" if record.timed_out else "completed" if output.exit_code == 0 else "failed"
            record.completed_at, record.duration_seconds = utc_now_iso(), time.monotonic() - started
            self.manager.record_command(session, record)
            try:
                result = json.loads(output.stdout) if output.exit_code == 0 else dict(status="query_failed", output=output.combined_output[-2000:])
            except ValueError:
                result = dict(status="query_failed", output=output.combined_output[-2000:])
            result.update(command_id=record.command_id, exit_code=record.exit_code, timed_out=record.timed_out, log_path="logs/" + record.command_id + ".log")
            self.meter.ledger.append("planning.environment_query", version=PLANNING_DEPENDENCY_VERSION, operation=operation, query=query, **kwargs, result=result)
            return result
