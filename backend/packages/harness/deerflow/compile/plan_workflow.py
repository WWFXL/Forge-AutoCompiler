"""项目构建方案的规则执行原型；不负责模型调用，不替代正式验收。"""

from __future__ import annotations

import hashlib
import json
import math
import shlex
import subprocess
import time
import uuid
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import build_replay_recipe, get_compile_services, infer_command_roles, submit_build_result_impl
from deerflow.compile.schemas import TERMINAL_COMPILE_SESSION_STATUSES, BuildCommandRecord, CommandResult, CompileSession, ReplayRecipe, utc_now_iso


class PlanContractError(ValueError):
    """方案、交接或权威命令记录不一致。"""


class PlanStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    step_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    role: Literal["dependency", "configure", "build", "smoke", "artifact_stage"]
    command: str = Field(min_length=1)
    source: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    workdir: str = "/workspace/repo"
    requires: tuple[str, ...] = ()
    required_output: tuple[str, ...] = ()
    diagnostic_paths: tuple[str, ...] = ()

    @field_validator("workdir")
    @classmethod
    def validate_workdir(cls, value: str) -> str:
        path = PurePosixPath(value)
        if value != path.as_posix() or ".." in path.parts or not any(path.is_relative_to(root) for root in ("/workspace/repo", "/artifacts")):
            raise ValueError("执行目录必须是仓库或交付目录内的规范绝对路径")
        return value

    @field_validator("diagnostic_paths")
    @classmethod
    def validate_diagnostics(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _relative_path(value)
        return values

    @model_validator(mode="after")
    def validate_expectation(self) -> Self:
        if any(not marker for marker in self.required_output) or (self.role == "smoke" and not self.required_output):
            raise ValueError("任务验证必须提供非空输出依据，不能仅凭退出码判定实际运行过测试")
        return self


class BuildPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    plan_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    revision: int = Field(default=1, ge=1)
    repository_url: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_archive_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    build_system: Literal["cmake", "make", "autotools"]
    artifact_paths: tuple[str, ...] = Field(min_length=1)
    steps: tuple[PlanStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_steps(self) -> Self:
        seen: set[str] = set()
        previous_rank = -1
        for step in self.steps:
            if step.step_id in seen or not set(step.requires).issubset(seen):
                raise ValueError("步骤标识必须唯一，前提只能引用更早步骤")
            rank = {"dependency": 0, "configure": 1, "build": 2, "smoke": 3, "artifact_stage": 3}[step.role]
            if rank < previous_rank:
                raise ValueError("依赖、配置、编译与交付验证必须按前提顺序排列")
            previous_rank = rank
            seen.add(step.step_id)
        if not {"build", "smoke", "artifact_stage"}.issubset(step.role for step in self.steps):
            raise ValueError("方案必须包含编译、任务验证和产物暂存步骤")
        for value in self.artifact_paths:
            _relative_path(value)
        if len(set(self.artifact_paths)) != len(self.artifact_paths):
            raise ValueError("交付路径不得重复")
        return self

    def fingerprint(self) -> str:
        return _digest(self.model_dump(mode="json"))


class PlanBudget(BaseModel):
    """方案执行预算；系统验收和诊断采集另有现有运行时的控制时限。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_commands: int = Field(default=32, ge=1)
    max_handoffs: int = Field(default=2, ge=0)
    wall_clock_seconds: int = Field(default=600, ge=1)
    command_timeout_seconds: int = Field(default=120, ge=1)


def _relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or value != path.as_posix() or path.as_posix() == "." or ".." in path.parts:
        raise ValueError("路径必须是规范相对路径")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PlanWorkflow:
    """独占一个 Session 的同步原型；交接返回方案建议，由 Workflow 执行。

    当前支持同进程暂停/返回，持久化文件用于审计而非进程重启恢复。
    接管方不得直接修改 Session；未知外部命令会使交接失效。
    """

    def __init__(
        self,
        *,
        plan: BuildPlan,
        session: CompileSession,
        manager: CompileSessionManager,
        runtime: CompileDockerRuntime,
        budget: PlanBudget | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.plan = BuildPlan.model_validate(plan)
        self.manager = manager
        self.runtime = runtime
        self.session_id = session.session_id
        self.thread_id = session.thread_id
        self.budget = budget or PlanBudget()
        self.clock = clock
        self.started = clock()
        self.commands_used = 0
        self.handoffs_used = 0
        self.completed: dict[str, str] = {}
        self.status = "pending"
        self.handoff: dict | None = None
        self._session = self._load()
        if self._session.status == "verified":
            raise PlanContractError("不能在已验收的 Session 中开始新方案")
        self._expected_frontier = self._frontier()
        self.directory = Path(self._session.metadata_path).parent / "build-plan"
        self.directory.mkdir(exist_ok=False)
        self._write_plan()
        self._persist()

    def _load(self) -> CompileSession:
        session = self.manager.load_session(self.session_id, self.thread_id)
        if (session.repo_url, session.commit_sha, session.image_id) != (self.plan.repository_url, self.plan.commit_sha, self.plan.image_id):
            raise PlanContractError("源码或环境身份与方案不符")
        if session.replay_source_archive_sha256 != self.plan.source_archive_sha256:
            raise PlanContractError("源码归档身份与方案不符")
        if (session.selected_build_system or session.build_system) != self.plan.build_system:
            raise PlanContractError("构建系统与方案不符")
        if session.status in TERMINAL_COMPILE_SESSION_STATUSES:
            raise PlanContractError("不能继续已终结的 Session")
        return session

    def _frontier(self) -> str:
        return _digest([asdict(record) for record in self._session.commands])

    def _observe(self) -> None:
        self._session = self._load()
        if self._frontier() != self._expected_frontier:
            raise PlanContractError("权威命令记录变化；旧方案状态或交接已失效")
        records = {row.command_id: row for row in self._session.commands}
        for step in self.plan.steps:
            if step.step_id not in self.completed:
                continue
            record = records[self.completed[step.step_id]]
            if (record.command, record.workdir, record.role) != (step.command, step.workdir, step.role) or record.exit_code != 0 or record.timed_out:
                raise PlanContractError("成功步骤与权威命令不符")

    def _remaining(self) -> int:
        return max(0, math.floor(self.budget.wall_clock_seconds - (self.clock() - self.started)))

    def _write_plan(self) -> None:
        with (self.directory / f"plan-{self.plan.revision}.json").open("x") as handle:
            handle.write(self.plan.model_dump_json(indent=2) + "\n")

    def snapshot(self) -> dict:
        return {
            "status": self.status,
            "plan_sha256": self.plan.fingerprint(),
            "revision": self.plan.revision,
            "completed": dict(self.completed),
            "commands_used": self.commands_used,
            "handoffs_used": self.handoffs_used,
            "remaining_seconds": self._remaining(),
            "handoff": deepcopy(self.handoff),
        }

    def _persist(self) -> None:
        payload = self.snapshot()
        (self.directory / "state.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self.manager.log_event(self._session, "plan.state", **payload)

    def _request_handoff(self, reason: str, step: PlanStep | None = None) -> dict:
        if self.handoffs_used >= self.budget.max_handoffs or self.commands_used >= self.budget.max_commands or self._remaining() <= 0:
            self.status = "budget_exhausted"
        else:
            self.handoffs_used += 1
            self.status = "needs_handoff"
            self.handoff = {
                "handoff_id": uuid.uuid4().hex,
                "reason": reason,
                "step_id": step.step_id if step else None,
                "plan_sha256": self.plan.fingerprint(),
                "command_frontier": self._expected_frontier,
                "recent_commands": [self._command_evidence(row) for row in self._session.commands[-6:]],
                "return_contract": "返回完整修订方案及修改理由；禁止自行降低验收或宣告成功",
            }
            (self.directory / f"handoff-{self.handoff['handoff_id']}.json").write_text(json.dumps(self.handoff, ensure_ascii=False, indent=2) + "\n")
        self._persist()
        return self.snapshot()

    def _command_evidence(self, record: BuildCommandRecord) -> dict:
        evidence = asdict(record)
        path = Path(record.log_path) if record.log_path else None
        if path is not None and path.is_file():
            content = path.read_bytes()
            evidence.update(log_sha256=hashlib.sha256(content).hexdigest(), output_tail=content[-4000:].decode(errors="replace"))
        evidence["diagnostic_directory"] = str(self.manager.local_logs_dir(self._session) / "plan-diagnostics" / record.command_id)
        return evidence

    def _capture_diagnostics(self, step: PlanStep, command_id: str) -> None:
        if not step.diagnostic_paths:
            return
        # 复制发生在容器内；拒绝逃出当前工作目录的符号链接，并保留缺失原因。
        script = """import pathlib,shutil,json,hashlib
root=pathlib.Path.cwd().resolve(); out=pathlib.Path('/logs/plan-diagnostics')/COMMAND_ID
rows=[]
for name in PATHS:
 p=(root/name).resolve(); row={'path':name}
 if not p.is_relative_to(root) or not p.is_file(): row['status']='missing_or_outside'
 elif p.stat().st_size>16777216: row['status']='size_limit'
 else:
  target=out/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,target)
  row.update(status='captured',sha256=hashlib.sha256(target.read_bytes()).hexdigest())
 rows.append(row)
print(json.dumps(rows))
""".replace("COMMAND_ID", repr(command_id)).replace("PATHS", repr(step.diagnostic_paths))
        path = self.manager.local_logs_dir(self._session) / f"{command_id}-diagnostics.log"
        try:
            captured = self.runtime.exec(self._session, "python3 -c " + shlex.quote(script), workdir=step.workdir, timeout_seconds=10, log_path=str(path), strict_shell=True)
            self.manager.log_event(self._session, "plan.diagnostics", command_id=command_id, exit_code=captured.exit_code, log_path=str(path))
        except Exception as exc:
            path.write_text(f"诊断日志采集失败：{type(exc).__name__}: {exc}\n")
            self.manager.log_event(self._session, "plan.diagnostics_failed", command_id=command_id, log_path=str(path))

    def _execute(self, step: PlanStep) -> bool:
        from deerflow.tools.bound_compile_tools import _disables_strict_shell

        roles = infer_command_roles(step.command)
        if _disables_strict_shell(step.command) or (len(roles) > 1):
            raise PlanContractError("步骤不能关闭严格 Shell 或混合多个逻辑阶段")
        timeout = min(self.budget.command_timeout_seconds, self._remaining())
        record = BuildCommandRecord(stage="plan", command=step.command, workdir=step.workdir, role=step.role, timeout_seconds=timeout)
        path = self.manager.local_logs_dir(self._session) / f"{record.command_id}.log"
        record.log_path = str(path)
        started = self.clock()
        self.commands_used += 1
        try:
            result = self.runtime.exec(self._session, step.command, workdir=step.workdir, timeout_seconds=timeout, log_path=str(path), strict_shell=True)
        except Exception as exc:
            timed_out = isinstance(exc, subprocess.TimeoutExpired)
            output = f"执行器异常：{type(exc).__name__}: {exc}\n"
            for partial in (getattr(exc, "stdout", None), getattr(exc, "stderr", None)):
                if partial:
                    output += partial.decode(errors="replace") if isinstance(partial, bytes) else str(partial)
            with path.open("a") as handle:
                handle.write(output)
            result = CommandResult(124 if timed_out else 125, "", output, output, str(path))
        record.completed_at = utc_now_iso()
        record.duration_seconds = self.clock() - started
        record.exit_code = result.exit_code
        record.timed_out = result.exit_code == 124
        record.termination = "timeout" if record.timed_out else "completed" if result.exit_code == 0 else "failed"
        self._observe()
        self.manager.record_command(self._session, record)
        self._session = self._load()
        self._expected_frontier = self._frontier()
        self._capture_diagnostics(step, record.command_id)
        passed = result.exit_code == 0 and all(marker in result.combined_output for marker in step.required_output)
        self.manager.log_event(self._session, "plan.step", step_id=step.step_id, revision=self.plan.revision, command_id=record.command_id, expected_satisfied=passed)
        if passed:
            self.completed[step.step_id] = record.command_id
        return passed

    def run(self) -> dict:
        with self.manager.session_lock(self.thread_id, self.session_id):
            self._observe()
            if self.status != "pending":
                return self.snapshot()
            for step in self.plan.steps:
                if step.step_id in self.completed:
                    continue
                if self.commands_used >= self.budget.max_commands or self._remaining() <= 0:
                    self.status = "budget_exhausted"
                    break
                if not set(step.requires).issubset(self.completed):
                    return self._request_handoff("precondition_missing", step)
                self._observe()
                if not self._execute(step):
                    return self._request_handoff("step_failed_or_expectation_missing", step)
                self._persist()
            else:
                self.status = "ready_for_verification"
            self._persist()
            return self.snapshot()

    def apply_revision(self, *, handoff_id: str, plan: BuildPlan, reason: str) -> None:
        with self.manager.session_lock(self.thread_id, self.session_id):
            self._observe()
            plan = BuildPlan.model_validate(plan)
            if self.status != "needs_handoff" or not self.handoff or self.handoff["handoff_id"] != handoff_id or not reason.strip():
                raise PlanContractError("没有匹配的活动交接或修改理由")
            old = self.plan
            identity = ("plan_id", "repository_url", "commit_sha", "image_id", "source_archive_sha256", "build_system", "artifact_paths")
            if any(getattr(plan, key) != getattr(old, key) for key in identity) or plan.revision != old.revision + 1:
                raise PlanContractError("修订不得改变任务身份、交付要求或跳过版本")
            if tuple(s for s in plan.steps if s.role == "smoke") != tuple(s for s in old.steps if s.role == "smoke"):
                raise PlanContractError("修订不得降低或替换任务验证要求")
            prefix = 0
            for before, after in zip(old.steps, plan.steps):
                keys = ("step_id", "command", "role", "workdir", "requires", "required_output")
                if any(getattr(before, key) != getattr(after, key) for key in keys):
                    break
                prefix += 1
            if prefix == len(old.steps) == len(plan.steps):
                raise PlanContractError("无变化修订不能触发相同失败的重复执行")
            keep = {step.step_id for step in old.steps[:prefix]}
            self.completed = {key: value for key, value in self.completed.items() if key in keep}
            self.plan = plan
            self.status = "pending"
            self.handoff = None
            self._write_plan()
            self.manager.log_event(self._session, "plan.revised", revision=plan.revision, reason=reason, retained_steps=sorted(keep))
            self._persist()

    def replay_recipe(self) -> ReplayRecipe:
        self._observe()
        if self.status != "ready_for_verification":
            raise PlanContractError("尚未满足方案的全部步骤")
        selected = {self.completed[step.step_id] for step in self.plan.steps if step.role != "smoke"}
        commands = [row for row in self._session.commands if row.command_id in selected]
        builds = [row.command_id for row in commands if row.role == "build"]
        checks = [self.completed[step.step_id] for step in self.plan.steps if step.role == "smoke"]
        return build_replay_recipe(self._session, supporting_command_id=builds[-1], recipe_command_ids=[row.command_id for row in commands], verification_command_ids=checks)

    def verify(self) -> dict:
        """连接既有产物/配方/干净重建验收；完成方案不自动等于 verified。"""
        with self.manager.session_lock(self.thread_id, self.session_id):
            recipe = self.replay_recipe()
            if self._remaining() <= 0:
                self.status = "budget_exhausted"
                self._persist()
                return self.snapshot()
            artifacts = Path(self._session.metadata_path).parent / "artifacts"
            actual = {p.relative_to(artifacts).as_posix() for p in artifacts.rglob("*") if p.is_file() or p.is_symlink()}
            if actual != set(self.plan.artifact_paths):
                return self._request_handoff("artifact_set_mismatch")
            services = get_compile_services()
            if services.manager is not self.manager or services.runtime is not self.runtime:
                raise PlanContractError("验收服务必须与方案执行使用同一 Session 管理器和运行时")
            submit_build_result_impl(
                session=self._session,
                supporting_command_id=recipe.supporting_command_id,
                recipe_command_ids=[step.command_id for step in recipe.steps],
                verification_command_ids=[step.command_id for step in recipe.verification_steps],
            )
            self._session = self._load()
            self._expected_frontier = self._frontier()
            if self._session.status == "verified" and self._session.replay_attempts and self._session.replay_attempts[-1].status == "passed":
                self.status = "verified"
                self._persist()
                return self.snapshot()
            return self._request_handoff("acceptance_failed")
