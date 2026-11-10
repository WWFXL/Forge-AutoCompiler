"""简洁任务的实际状态、主产物检查和分层执行；不改变旧完整验收语义。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import time
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from deerflow.compile import operations
from deerflow.compile.plan_workflow import PlanContractError, PlanStep, PlanWorkflow, _digest
from deerflow.compile.schemas import BuildCommandRecord, CommandResult, utc_now_iso
from deerflow.compile.simple_author_tests import resolve_author_tests
from deerflow.compile.simple_build_task import BuildReference, SimpleBuildPlan, validate_simple_revision


def file_hash(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def source_inventory(root: Path) -> dict:
    """记录原文件/链接的内容和文件身份；不宣称覆盖所有瞬时写入事件。"""
    rows = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files + [d for d in dirs if (Path(directory) / d).is_symlink()]:
            p = Path(directory) / name
            s = p.lstat()
            if not stat.S_ISREG(s.st_mode) and not stat.S_ISLNK(s.st_mode):
                raise PlanContractError("源码包含不支持的特殊文件")
            rows[p.relative_to(root).as_posix()] = dict(sha256=None if p.is_symlink() else file_hash(p), link=os.readlink(p) if p.is_symlink() else None, mode=s.st_mode, inode=s.st_ino, ctime_ns=s.st_ctime_ns)
    return rows


def source_unchanged(root, baseline, generated_documents=()):
    documents = {d.path: d for d in generated_documents}
    if any(d.path not in baseline or d.template not in baseline or baseline[d.path]["link"] is not None or baseline[d.template]["link"] is not None for d in generated_documents):
        raise PlanContractError("作者生成文档及模板必须是原始普通文件")
    for name, row in baseline.items():
        p = root / name
        try:
            s = p.lstat()
            actual = dict(sha256=None if p.is_symlink() else file_hash(p), link=os.readlink(p) if p.is_symlink() else None, mode=s.st_mode, inode=s.st_ino, ctime_ns=s.st_ctime_ns)
        except OSError as exc:
            raise PlanContractError("原源码/测试缺失：" + name) from exc
        if actual != row:
            document = documents.get(name)
            if document is not None and actual["link"] is None and actual["mode"] == row["mode"] and stat.S_ISREG(s.st_mode) and actual["sha256"] == document.sha256:
                continue
            raise PlanContractError("原源码/测试被修改：" + name)


def observe_configuration(root: Path, system: str, *, directory: str | None = None) -> dict:
    """从实际Cache读取generator和源码，绝不固定要求Ninja。"""
    if system == "autotools":
        folder = root / (directory or ".")
        # GNU Make的标准入口；其他作者自定义入口保留unknown，由真实build反馈确认。
        entry = next((name for name in ("GNUmakefile", "makefile", "Makefile") if (folder / name).is_file()), None)
        return dict(status="passed" if (folder / "config.status").is_file() and entry else "unknown", directory=directory or ".", entry=entry, build_system=system)
    if system != "cmake":
        return dict(status="not_applicable", reason="当前入口不使用CMake/Autotools配置观察；主构建仍须独立产物检查", configurations=[], build_system=system)
    rows = []
    paths = [root / directory / "CMakeCache.txt"] if directory is not None else sorted(root.rglob("CMakeCache.txt"))
    for p in paths:
        if not p.is_file():
            continue
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            continue
        cache = {}
        for line in p.read_text(errors="replace").splitlines():
            if "=" in line and ":" in line.split("=", 1)[0]:
                key, value = line.split("=", 1)
                cache[key.split(":", 1)[0]] = value
        generator = cache.get("CMAKE_GENERATOR")
        entry = {"Unix Makefiles": "Makefile", "Ninja": "build.ninja", "Ninja Multi-Config": "build.ninja"}.get(generator)
        source = cache.get("CMAKE_HOME_DIRECTORY", "")
        directory = cache.get("CMAKE_CACHEFILE_DIR", "")
        expected_directory = "/workspace/repo/" + p.parent.relative_to(root).as_posix()
        expected_directory = expected_directory.removesuffix("/.")
        try:
            src = PurePosixPath(source).relative_to("/workspace/repo")
            source_valid = ".." not in src.parts and (root / src / "CMakeLists.txt").is_file()
        except ValueError:
            source_valid = False
        passed = bool(entry and (p.parent / entry).is_file() and source_valid and directory == expected_directory)
        rows.append(dict(directory=p.parent.relative_to(root).as_posix(), generator=generator, entry=entry, source_directory=source, cache_directory=directory, status="passed" if passed else "unknown" if not entry else "failed"))
    return dict(status="passed" if rows and all(r["status"] == "passed" for r in rows) else "unknown" if not rows or any(r["status"] == "unknown" for r in rows) else "failed", configurations=rows, build_system="cmake")


def configuration_entry(root: Path, step: PlanStep, previous: dict, *, output: str = "", build_directory: str | None = None) -> tuple[str, str | None]:
    """目录来自显式上下文或原生工具反馈；无法绑定时不猜Shell参数含义。"""
    system = previous.get("build_system", "make")
    directory = previous.get("directory") if step.role == "build" else None
    working = PurePosixPath(step.workdir).relative_to("/workspace/repo")
    if build_directory is not None:
        directory = PurePosixPath(build_directory).relative_to("/workspace/repo").as_posix()
    for segment in operations._shell_command_segments(step.command):
        invocation = operations._command_invocation(segment)
        if not invocation:
            continue
        executable, args = invocation
        name = PurePosixPath(executable).name
        if name not in {"cmake", "configure", "make", "gmake", "ninja", "scons", "meson"}:
            continue
        if name == "cmake":
            system = "cmake"
        elif name == "configure":
            system = "autotools"
        elif name in {"make", "gmake", "ninja"} and directory is None:
            # 没有已绑定的生成目录时，以实际构建入口替代初始扫描标签。
            system = "ninja" if name == "ninja" else "make"
        elif name in {"scons", "meson"}:
            system = name
    if system == "cmake":
        # 原生工具负责preset/宏/实际目录；终端日志缺失不等于配置失败。
        for line in output.splitlines():
            prefix = "-- Build files have been written to: "
            if line.startswith(prefix):
                value = PurePosixPath(line.removeprefix(prefix).strip())
                if not value.is_absolute() or not value.is_relative_to("/workspace/repo"):
                    raise PlanContractError("CMake报告的配置目录必须在仓库内")
                directory = value.relative_to("/workspace/repo").as_posix()
    elif directory is None:
        directory = working.as_posix()
    if directory is not None:
        absolute = (root / directory).resolve()
        if not absolute.is_relative_to(root.resolve()):
            raise PlanContractError("配置观察目录必须在仓库内")
        directory = absolute.relative_to(root.resolve()).as_posix()
    return system, directory


def validate_phase_command(step):
    """只把有明确作用域的make clean/distclean当阶段前置，保留其他阶段限制。"""
    from deerflow.tools.bound_compile_tools import _disables_strict_shell

    if _disables_strict_shell(step.command) or "/repro" in step.command:
        raise PlanContractError("不能关闭严格Shell或访问/repro")
    for segment in operations._shell_command_segments(step.command):
        invocation = operations._command_invocation(segment)
        if invocation and invocation[0] in {"rm", "unlink", "rmdir"}:
            raise PlanContractError("生成物清理由系统或作者clean目标执行，不能提交任意删除")
    roles = operations.infer_command_roles(step.command)
    if len(roles) <= 1:
        return
    expected = {"build"} if step.role == "build" else {"configure"} if step.role == "configure" else set()
    if roles != expected | {"housekeeping"}:
        raise PlanContractError("命令混合多个逻辑阶段")
    substantive = False
    for segment in operations._shell_command_segments(step.command):
        invocation = operations._command_invocation(segment)
        if not invocation:
            raise PlanContractError("清理前置必须能确定实际命令")
        executable, args = invocation
        if executable in {"make", "gmake"} and args in (["clean"], ["distclean"]):
            if substantive:
                raise PlanContractError("清理只能发生在当前阶段实际动作之前")
            continue
        if executable in {"rm", "unlink", "rmdir", "bash", "sh", "sudo", "env"}:
            raise PlanContractError("不能通过放宽清理前置执行任意删除或嵌套Shell")
        substantive = True


def generated_reset_step(baseline):
    """只清理本次源码树新增文件，不删除/重写原文件；同一显式动作进入重放。"""
    protected = sorted(baseline)
    script = """import os,pathlib
root=pathlib.Path('/workspace/repo')
protected=set(PROTECTED)
for directory,dirs,files in os.walk(root,topdown=False,followlinks=False):
 p=pathlib.Path(directory)
 if '.git' in p.relative_to(root).parts: continue
 for name in files:
  f=p/name; rel=f.relative_to(root).as_posix()
  if rel not in protected: f.unlink()
 for name in dirs:
  d=p/name; rel=d.relative_to(root).as_posix()
  if name=='.git' or rel in protected: continue
  if d.is_symlink(): d.unlink()
  elif not any(d.iterdir()): d.rmdir()
print('FORGE_GENERATED_RESET')
""".replace("PROTECTED", repr(protected))
    return PlanStep(
        step_id="forge-generated-reset", role="configure", command="python3 - <<'FORGE_RESET_PY'\n" + script + "\nFORGE_RESET_PY", source="系统：依赖/配置变化后清理原输入集合以外的生成文件", expected="物理清理与逻辑后缀失效分别记录"
    )


def primary_artifacts(*, task, reference, root, baseline, deadline):
    """独立组件覆盖＋结构/平台/来源检查；路径定位不改变构建动作。"""
    if reference.task_sha256 != _digest(task.model_dump(mode="json")):
        raise PlanContractError("独立参考与公开任务身份不一致")
    source_unchanged(root, baseline, reference.generated_documents)
    precompiled = set()
    for name, row in baseline.items():
        p = root / name
        if not p.is_symlink():
            with p.open("rb") as stream:
                magic = stream.read(8)
            if magic.startswith(b"\x7fELF") or magic == b"!<arch>\n":
                precompiled.add(row["sha256"])
    names = {n for c in reference.components for n in c.artifact_names}
    candidates = []
    machine = {"x86_64": "Advanced Micro Devices X86-64", "aarch64": "AArch64"}[task.architecture]
    for p in root.rglob("*"):
        if time.monotonic() >= deadline:
            return dict(status="unknown", reason="产物观察达到时限", components=[], artifacts=[])
        if p.name not in names or ".git" in p.relative_to(root).parts:
            continue
        try:
            resolved = p.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
            continue
        relative = resolved.relative_to(root.resolve()).as_posix()
        if relative in baseline:
            continue
        kind = operations._classify_compiled_artifact(resolved, deadline=deadline)
        if kind not in {"executable", "static_library", "shared_library"}:
            continue
        digest = file_hash(resolved)
        if digest in precompiled:
            continue
        header = subprocess.run(["readelf", "-h", str(resolved)], capture_output=True, text=True, timeout=max(0.1, min(10, deadline - time.monotonic())), env={**os.environ, "LC_ALL": "C"})
        machines = {line.split(":", 1)[1].strip() for line in header.stdout.splitlines() if line.strip().startswith("Machine:")}
        if header.returncode != 0 or machines != {machine}:
            continue
        candidates.append(dict(alias=p.name, path=relative, kind=kind, size=resolved.stat().st_size, sha256=digest, mode=resolved.stat().st_mode & 0o777, platform=task.architecture, source="new_file_after_current_source_extraction"))
    rows, selected = [], []
    for component in reference.components:
        matches = [p for p in candidates if p["alias"] in component.artifact_names and p["kind"] in component.kinds]
        # 同一逻辑组件的静态/共享实现均可；逐内容身份去重副本/链接。
        identities = {(p["kind"], p["sha256"], p["mode"]): p for p in reversed(sorted(matches, key=lambda p: p["path"]))}
        covered = bool(identities)
        rows.append(dict(name=component.name, status="passed" if covered else "failed", evidence=component.evidence, candidates=list(identities.values())))
        selected.extend(identities.values())
    unique = {p["path"]: p for p in selected}
    return dict(status="passed" if all(r["status"] == "passed" for r in rows) else "failed", components=rows, artifacts=list(unique.values()))


class SimpleBuildWorkflow(PlanWorkflow):
    plan_model = SimpleBuildPlan

    def __init__(self, *, reference: BuildReference, meter=None, **kwargs):
        self.reference = reference
        self.meter = meter
        self.root = Path(kwargs["session"].leadagent_repo_dir).resolve()
        self.baseline = source_inventory(self.root)
        self.configuration = dict(status="unknown", directory=None, build_system=kwargs["plan"].build_system, reason="尚无当前动作的配置证据")
        self.observation_step = None
        self.observation_record = None
        self.primary = None
        self.layers = dict(
            command_build_passed=None, primary_build_completed=None, delivery="unobserved", author_tests="unobserved", executable_smoke="unobserved", final_verification_passed=None, clean_replay="unobserved", full_completed=None
        )
        self.timings = {}
        super().__init__(**kwargs)
        if meter is not None:
            self.started = meter.started_monotonic
        if reference.task_sha256 != _digest(self.plan.task.model_dump(mode="json")):
            raise PlanContractError("独立参考不属于当前公开任务")
        (self.directory / "source-baseline.json").write_text(json.dumps(self.baseline, ensure_ascii=False, indent=2) + "\n")

    def check_source(self):
        source_unchanged(self.root, self.baseline, self.reference.generated_documents)

    def source_protection(self):
        """保护输入与明确授权的文档生成分列，不把文档变化说成所有原文件字节未变。"""
        self.check_source()
        changes = []
        for document in self.reference.generated_documents:
            path = self.root / document.path
            actual = file_hash(path)
            original = self.baseline[document.path]
            identity = path.lstat()
            content_changed = actual != original["sha256"]
            identity_changed = identity.st_ino != original["inode"] or identity.st_ctime_ns != original["ctime_ns"]
            if content_changed or identity_changed:
                changes.append(dict(path=document.path, template=document.template, source=document.source, before_sha256=original["sha256"], after_sha256=actual, content_changed=content_changed, file_identity_changed=identity_changed))
        return dict(protected_inputs_unchanged=True, generated_document_changes=changes)

    def snapshot(self):
        return {**super().snapshot(), "configuration_state": self.configuration, "layers": dict(self.layers)}

    def _validate_step(self, step):
        validate_phase_command(step)

    def _configuration_observation(self, plan):
        if self.observation_step is None:
            return dict(self.configuration)
        record = self.observation_record
        path = Path(record.log_path) if record and record.log_path else None
        # 配置目录证据只来自当前配置动作，不能拿旧配置日志覆盖当前build目录。
        output = ""
        if self.observation_step.role == "configure" and path and path.is_file():
            with path.open(errors="replace") as stream:
                output = "".join(line for line in stream if line.startswith("-- Build files have been written to: "))
        system, directory = configuration_entry(self.root, self.observation_step, self.configuration, output=output, build_directory=plan.build_directory)
        observation = observe_configuration(self.root, system, directory=directory) if directory is not None else dict(status="unknown", build_system=system, reason="实际构建目录未绑定；不扫描其他目录的旧配置来代替当前证据")
        observation["directory"] = directory
        observation["declared_build_directory"] = plan.build_directory
        observation["command_id"] = record.command_id if record else None
        observation["phase_complete"] = self.observation_step.role != "configure" or not any(s.role == "configure" and s.step_id != self.observation_step.step_id and s.step_id not in self.completed for s in plan.steps)
        return observation

    def refresh_configuration(self):
        self.configuration = self._configuration_observation(self.plan)
        return self.configuration

    def _execute(self, step):
        self.check_source()
        if self.meter is not None:
            self.meter.tracker.observe_elapsed(time.monotonic() - self.started)
            self.meter.tracker.consume(commands=1)
        try:
            self._validate_step(step)
        except PlanContractError as exc:
            record = BuildCommandRecord(stage="plan", command=step.command, workdir=step.workdir, role=step.role, exit_code=126, termination="policy_rejected", completed_at=utc_now_iso())
            record.log_path = str(self.manager.local_logs_dir(self._session) / (record.command_id + ".log"))
            Path(record.log_path).write_text(str(exc))
            self.commands_used += 1
            self.manager.record_command(self._session, record)
            self._session = self._load()
            self._expected_frontier = self._frontier()
            return False
        passed = super()._execute(step)
        record = self._session.commands[-1]
        key = step.role + "_seconds"
        self.timings[key] = self.timings.get(key, 0) + (record.duration_seconds or 0)
        if self.handoffs_used:
            self.timings["recovery_execution_seconds"] = self.timings.get("recovery_execution_seconds", 0) + (record.duration_seconds or 0)
        if step.role == "build":
            self.layers["command_build_passed"] = bool(record.exit_code == 0 and not record.timed_out)
        self.check_source()
        if not passed:
            return False
        if step.role in {"configure", "build"} and step.step_id != "forge-generated-reset":
            self.observation_step = step
            self.observation_record = record
            self.refresh_configuration()
            self.manager.log_event(self._session, "simple.configuration_observed", step_id=step.step_id, **self.configuration)
            # autogen/autoreconf等前置可以单列动作；只在配置阶段结束时要求配置完成。
            # 所有中间动作仍必须成功退出；实际build与独立主产物检查保持不变。
            if self.configuration["phase_complete"] and self.configuration["status"] == "failed":
                self.completed.pop(step.step_id, None)
                return False
            if self.configuration["status"] == "unknown":
                # 只继续已经规划且受原时限/命令数约束的动作；unknown不改写为passed。
                # 构建命令失败仍交接；build退出0后还必须通过独立主产物检查。
                self.manager.log_event(self._session, "simple.observation_inconclusive", step_id=step.step_id, next_action="continue_planned_execution", command_id=record.command_id)
        return True

    def _request_handoff(self, reason, step=None):
        if reason == "step_failed_or_expectation_missing" and self.observation_record and self._session.commands[-1].command_id == self.observation_record.command_id:
            reason = "configuration_inconsistent"
        result = super()._request_handoff(reason, step)
        if self.handoff:
            self.handoff.update(
                configuration_state=self.configuration,
                primary_components=self.primary,
                successful_dependencies=[dict(step_id=s.step_id, command_id=self.completed[s.step_id], command=s.command, workdir=s.workdir) for s in self.plan.steps if s.role == "dependency" and s.step_id in self.completed],
            )
            self._persist()
            (self.directory / f"handoff-{self.handoff['handoff_id']}.json").write_text(json.dumps(self.handoff, ensure_ascii=False, indent=2) + "\n")
            result = self.snapshot()
        return result

    def run(self):
        result = super().run()
        if self.status != "ready_for_verification":
            return result
        # 角色声明表示动作目的；成功记录与下面的独立主产物检查共同确认结果。
        # Shell变量/包装器无法静态识别，不能据此否定已观察到的实际构建。
        self.layers["command_build_passed"] = any(s.role == "build" and s.step_id in self.completed for s in self.plan.steps)
        observed = time.monotonic()
        self.primary = primary_artifacts(task=self.plan.task, reference=self.reference, root=self.root, baseline=self.baseline, deadline=observed + min(30, self._remaining()))
        self.timings["result_location_seconds"] = time.monotonic() - observed
        self.layers["primary_build_completed"] = True if self.layers["command_build_passed"] and self.primary["status"] == "passed" else None if self.primary["status"] == "unknown" else False
        if not self.layers["primary_build_completed"]:
            return self._request_handoff("primary_components_missing_or_unobserved")
        self.status = "primary_completed"
        self.timings["primary_build_seconds"] = self.clock() - self.started
        payload = dict(layers=self.layers, primary=self.primary, configuration=self.configuration, timings=self.timings, workflow=self.snapshot())
        with (self.directory / f"primary-result-r{self.plan.revision}.json").open("x") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        if not (self.directory / "primary-result.json").exists():
            (self.directory / "primary-result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self._persist()
        return self.snapshot()

    def _retain_dependencies(self, plan):
        """遗漏不是删除；有效配方保留成功准备，不收集所有历史命令。"""
        successful = [s for s in self.plan.steps if s.role == "dependency" and s.step_id in self.completed]
        known = {s.step_id for s in successful}
        if not set(plan.discard_dependencies) <= known:
            raise PlanContractError("discard_dependencies只能引用当前已成功的依赖步骤")
        incoming = {s.step_id: s for s in plan.steps}
        retained = []
        keys = ("role", "command", "workdir", "requires", "required_output")
        for old in successful:
            if old.step_id in plan.discard_dependencies:
                continue
            new = incoming.get(old.step_id)
            if new is not None and any(getattr(old, k) != getattr(new, k) for k in keys):
                raise PlanContractError(f"替换成功依赖{old.step_id}须在discard_dependencies中说明理由；不能隐式覆盖")
            if any(s.step_id != old.step_id and (s.role, s.command, s.workdir) == (old.role, old.command, old.workdir) for s in plan.steps):
                raise PlanContractError(f"依赖改名没有改变实际执行动作；请沿用成功依赖的step_id={old.step_id}，不要改名重复执行")
            retained.append(new or old)
        retained_ids = {s.step_id for s in retained}
        # 成功环境准备保持实际先后，新增依赖在其后执行；配置后缀仍会失效。
        value = plan.model_dump()
        value["steps"] = [*retained, *(s for s in plan.steps if s.step_id not in retained_ids)]
        return SimpleBuildPlan.model_validate(value)

    def validate_revision(self, plan):
        """先把可执行性问题反馈给Agent；只改观察上下文时不重跑成功命令。"""
        plan = SimpleBuildPlan.model_validate(plan)
        if plan.task != self.plan.task or plan.revision != self.plan.revision + 1:
            raise PlanContractError("修订不得改变公开任务或资源身份，必须递增一个版本")
        plan = self._retain_dependencies(plan)
        record = self.observation_record
        observation_only = bool(self.handoff and self.handoff["reason"] == "configuration_inconsistent" and record and record.exit_code == 0 and not record.timed_out)
        kind = validate_simple_revision(self.plan, plan, allow_observation_only=observation_only)
        observation = None
        if kind == "observation":
            self.check_source()
            observation = self._configuration_observation(plan)
            if observation["status"] != "passed":
                raise PlanContractError("新观察目录没有通过实际配置核验；不能据此解除配置冲突或重跑原命令")
        return kind, observation

    def apply_revision(self, *, handoff_id, plan, reason):
        with self.manager.session_lock(self.thread_id, self.session_id):
            self._observe()
            if self.status != "needs_handoff" or not self.handoff or self.handoff["handoff_id"] != handoff_id or not reason.strip():
                raise PlanContractError("没有匹配的活动交接或修改理由")
            plan = SimpleBuildPlan.model_validate(plan)
            kind, observation = self.validate_revision(plan)
            plan = self._retain_dependencies(plan)
            if kind == "observation":
                # Agent不可生成/覆盖系统步骤；观察修订仍保留已执行的实际清理配方。
                replacement = {s.step_id: s for s in plan.steps}
                plan = plan.model_copy(update={"steps": tuple(s if s.step_id == "forge-generated-reset" else replacement[s.step_id] for s in self.plan.steps)})
                self.plan, self.configuration = plan, observation
                self.completed[self.observation_step.step_id] = self.observation_record.command_id
                self.status, self.handoff = "pending", None
                self._write_plan()
                self.manager.log_event(self._session, "simple.observation_revised", revision=plan.revision, reason=reason, command_reexecuted=False, configuration=observation)
                self._persist()
                return
            self._apply_execution_revision(handoff_id=handoff_id, plan=plan, reason=reason)

    def _apply_execution_revision(self, *, handoff_id, plan, reason):
        retained_dependencies = {s.step_id: self.completed[s.step_id] for s in self.plan.steps if s.role == "dependency" and s.step_id in self.completed and s.step_id not in plan.discard_dependencies}
        old = [s for s in self.plan.steps if s.step_id != "forge-generated-reset"]
        new = [s for s in plan.steps if s.step_id != "forge-generated-reset"]
        before = [(s.role, s.command, s.workdir) for s in old if s.role in {"dependency", "configure"}]
        after = [(s.role, s.command, s.workdir) for s in new if s.role in {"dependency", "configure"}]
        if before != after:
            position = next((i for i, s in enumerate(new) if s.role != "dependency"), len(new))
            new.insert(position, generated_reset_step(self.baseline))
            plan = plan.model_copy(update={"steps": tuple(new)})
        elif any(s.step_id == "forge-generated-reset" for s in self.plan.steps):
            position = next((i for i, s in enumerate(new) if s.role != "dependency"), len(new))
            new.insert(position, next(s for s in self.plan.steps if s.step_id == "forge-generated-reset"))
            plan = plan.model_copy(update={"steps": tuple(new)})
        super().apply_revision(handoff_id=handoff_id, plan=plan, reason=reason)
        # 删除前面的某个依赖可能使通用前缀算法清空后续完成记录；仍有效的
        # 独立准备动作可复用，避免仅为了保留重放配方而在原容器重装。
        for step in self.plan.steps:
            if step.step_id in retained_dependencies and set(step.requires) <= self.completed.keys():
                self.completed[step.step_id] = retained_dependencies[step.step_id]
        self.manager.log_event(self._session, "simple.dependencies_retained", command_ids=retained_dependencies, discarded=plan.discard_dependencies)
        self._persist()
        self.observation_step = self.observation_record = None
        self.configuration = dict(status="unknown", directory=None, build_system=plan.build_system, reason="方案修订后等待新的实际执行证据")
        self.primary = None
        self.layers["command_build_passed"] = self.layers["primary_build_completed"] = None
        for name in ("delivery", "author_tests", "executable_smoke", "clean_replay"):
            self.layers[name] = "unobserved"
        self.layers["final_verification_passed"] = None

    def _post_command(self, step, timeout):
        from deerflow.tools.bound_compile_tools import _disables_strict_shell

        if _disables_strict_shell(step.command):
            raise PlanContractError("后续检查也必须保持严格Shell")
        self.check_source()
        record = BuildCommandRecord(stage="simple_postcheck", command=step.command, workdir=step.workdir, role=step.role, timeout_seconds=timeout)
        record.log_path = str(self.manager.local_logs_dir(self._session) / (record.command_id + ".log"))
        started = time.monotonic()
        try:
            result = self.runtime.exec(self._session, step.command, workdir=step.workdir, timeout_seconds=timeout, log_path=record.log_path, strict_shell=True)
        except subprocess.TimeoutExpired as exc:
            text = str(exc)
            Path(record.log_path).write_text(text)
            result = CommandResult(124, "", text, text, record.log_path)
        record.exit_code, record.timed_out = result.exit_code, result.exit_code == 124
        record.termination = "timeout" if record.timed_out else "completed" if result.exit_code == 0 else "failed"
        record.completed_at, record.duration_seconds = utc_now_iso(), time.monotonic() - started
        self.manager.record_command(self._session, record)
        self._session = self._load()
        self._expected_frontier = self._frontier()
        self.check_source()
        return record, result

    def _executable_verification(self, timeout, *, native_only=False):
        """执行受信参考中的轻量命令；复用submit原有的成功命令绑定接口。"""
        self.verification_issue = None
        if not self.reference.executable_smokes and not native_only:
            return None, True  # 沿用原默认三参数，不增加隐式探测。
        executables = {Path(p["path"]).name for p in self.primary["artifacts"] if p["kind"] == "executable"}
        selected = [s for s in self.reference.executable_smokes if s.artifact_name in executables]
        if {s.artifact_name for s in selected} != executables:
            self.layers["executable_smoke"] = "unobserved"
            self.verification_issue = dict(kind="missing_native_verification", reason="独立参考缺少可执行文件的作者轻量验证入口；不猜测参数", recoverable=False)
            return None, False
        bindings = {}
        start = time.monotonic()
        self.layers["executable_smoke"] = "not_applicable" if not executables else "passed"
        for smoke in selected:
            remaining = int(timeout - (time.monotonic() - start))
            if remaining <= 0:
                self.layers["executable_smoke"] = "timeout"
                return None, False
            # 原容器与重放共用同一短时限；交付共享库在交付目录内解析。
            step = smoke.step.model_copy(update={"command": "export LD_LIBRARY_PATH=/artifacts${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}\n" + smoke.step.command})
            record, output = self._post_command(step, min(30, remaining))
            if record.exit_code != 0 or record.timed_out or not all(v in output.combined_output for v in smoke.step.required_output):
                self.layers["executable_smoke"] = "timeout" if record.timed_out else "failed"
                self.verification_issue = dict(
                    kind="execution_failed" if record.exit_code != 0 else "output_assertion_failed",
                    command_id=record.command_id,
                    recoverable=record.exit_code != 0 and not record.timed_out,
                    reason="执行未成功" if record.exit_code != 0 else "退出0但输出断言不符，需核对独立验证定义，不能交Agent改写裁判",
                )
                return None, False
            bindings[smoke.artifact_name] = operations.SuccessfulCommandVerification(
                command_id=record.command_id, command=record.command, workdir=record.workdir, exit_code=record.exit_code, output=output.combined_output, output_sha256=hashlib.sha256(output.combined_output.encode()).hexdigest()
            )
        return operations.ExecutableVerificationPolicy.successful_commands(bindings) if bindings else None, True

    def postchecks(self, *, author_test_seconds=60, delivery_seconds=30, replay=True, validation_scope="author_tests", recover_delivery=False):
        """主构建已冻结后独立计时；测试失败仍可观察构建重放，不吞主构建预算。"""
        if self.status != "primary_completed":
            raise PlanContractError("必须先确认主要构建")
        if validation_scope not in {"main_build", "author_tests"}:
            raise PlanContractError("未知构建验证范围")
        self.check_source()
        artifacts = self.primary["artifacts"]
        destinations = [Path(p["path"]).name for p in artifacts]
        if len(set(destinations)) != len(destinations):
            raise PlanContractError("主产物交付名称歧义")
        copies = {Path(p["path"]).name: p["path"] for p in artifacts}
        # ELF自身声明的SONAME是运行时依赖名称；只为已确认的主共享库建立精确副本。
        for artifact in artifacts:
            if artifact["kind"] != "shared_library":
                continue
            dynamic = subprocess.run(["readelf", "-d", str(self.root / artifact["path"])], capture_output=True, text=True, check=True, timeout=min(10, delivery_seconds))
            for name in re.findall(r"\(SONAME\).*?\[([^\]]+)\]", dynamic.stdout):
                if not name or PurePosixPath(name).name != name or name in {".", ".."}:
                    raise PlanContractError("共享库SONAME不能逃出交付目录")
                if name in copies and copies[name] != artifact["path"]:
                    raise PlanContractError("交付共享库SONAME歧义")
                copies[name] = artifact["path"]
        destinations = list(copies)
        command = "\n".join("cp -- " + shlex.quote(path) + " /artifacts/" + shlex.quote(name) for name, path in copies.items())
        stage = PlanStep(step_id="stage", role="artifact_stage", command=command, source="实际主组件观察", expected="精确暂存主产物")
        start = time.monotonic()
        staged, result = self._post_command(stage, delivery_seconds)
        actual = {p.name for p in Path(self._session.leadagent_artifacts_dir).iterdir() if p.is_file() and not p.is_symlink()}
        self.layers["delivery"] = "passed" if result.exit_code == 0 and actual == set(destinations) else "failed"
        self.timings["delivery_seconds"] = time.monotonic() - start
        tests = []
        start = time.monotonic()
        if validation_scope == "main_build":
            author_steps, selection = (), dict(route="not_required", reason="新主构建任务不要求完整作者测试")
        else:
            author_steps, selection = resolve_author_tests(self.root, self.reference)
        (self.directory / "author-test-selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n")
        if not author_steps:
            self.layers["author_tests"] = "not_required" if validation_scope == "main_build" else "not_applicable" if self.reference.tests_not_applicable_reason else "unobserved"
        else:
            self.layers["author_tests"] = "passed"
            for step in author_steps:
                remaining = int(author_test_seconds - (time.monotonic() - start))
                if remaining <= 0:
                    self.layers["author_tests"] = "timeout"
                    break
                record, output = self._post_command(step, remaining)
                passed = record.exit_code == 0 and all(v in output.combined_output for v in step.required_output)
                tests.append(dict(command_id=record.command_id, passed=passed, timed_out=record.timed_out))
                if not passed:
                    self.layers["author_tests"] = "timeout" if record.timed_out else "failed"
                    break
        self.timings["author_tests_seconds"] = time.monotonic() - start
        replayed_tests = self.layers["author_tests"] == "passed"
        if replay and self.layers["delivery"] == "passed":
            self._observe()
            selected = {self.completed[s.step_id] for s in self.plan.steps} | {staged.command_id}
            ids = [r.command_id for r in self._session.commands if r.command_id in selected]
            builds = [self.completed[s.step_id] for s in self.plan.steps if s.role == "build"]
            start = time.monotonic()
            attempt_count = len(self._session.replay_attempts)
            self.layers.update(clean_replay="not_started", final_verification_passed=False)
            try:
                policy, smoke_passed = self._executable_verification(author_test_seconds, native_only=validation_scope == "main_build")
                if smoke_passed:
                    kwargs = dict(executable_verification_policy=policy) if policy is not None else {}
                    verification_ids = {t["command_id"] for t in tests} if replayed_tests else set()
                    if policy is not None:
                        verification_ids.update(e.command_id for e in policy.commands_by_artifact.values())
                    ordered_checks = [r.command_id for r in self._session.commands if r.command_id in verification_ids]
                    operations.submit_build_result_impl(session=self._session, supporting_command_id=builds[-1], recipe_command_ids=ids, verification_command_ids=ordered_checks, **kwargs)
            finally:
                self._session = self._load()
                self._expected_frontier = self._frontier()
                attempts = self._session.replay_attempts[attempt_count:]
                self.layers["clean_replay"] = attempts[-1].status if attempts else "not_started"
                self.layers["final_verification_passed"] = bool(attempts and attempts[-1].status == "passed" and self._session.status == "verified")
                if not self.reference.executable_smokes and self._session.verification:
                    checks = [c for c in self._session.verification.checks if c.name.endswith("_smoke_test")]
                    self.layers["executable_smoke"] = "passed" if checks and all(c.passed for c in checks) else "failed" if checks else "not_applicable"
                self.timings["clean_replay_seconds"] = time.monotonic() - start
        self.check_source()
        self.timings["total_seconds_before_cleanup"] = self.clock() - self.started
        result = dict(
            layers=self.layers,
            timings=self.timings,
            primary=self.primary,
            author_test_records=tests,
            author_test_selection=selection,
            replayed_author_tests=replayed_tests and replay,
            session_status=self._session.status,
            replay_attempts=[asdict(a) for a in self._session.replay_attempts],
            validation_scope=validation_scope,
            verification_issue=getattr(self, "verification_issue", None),
        )
        (self.directory / f"postcheck-result-r{self.plan.revision}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        (self.directory / "postcheck-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        issue = result["verification_issue"]
        if recover_delivery and issue and issue["recoverable"]:
            self._request_handoff("delivery_execution_failed")
            if self.handoff:
                self.handoff["delivery_failure"] = issue
                self._persist()
                (self.directory / f"handoff-{self.handoff['handoff_id']}.json").write_text(json.dumps(self.handoff, ensure_ascii=False, indent=2) + "\n")
        return result
