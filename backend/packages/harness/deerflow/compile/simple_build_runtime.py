"""简洁任务的实际状态、主产物检查和分层执行；不改变旧完整验收语义。"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import stat
import subprocess
import time
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from deerflow.compile import operations
from deerflow.compile.plan_workflow import PlanContractError, PlanStep, PlanWorkflow, _digest
from deerflow.compile.schemas import BuildCommandRecord, CommandResult, utc_now_iso
from deerflow.compile.simple_author_tests import cmake_roots, resolve_author_tests
from deerflow.compile.simple_build_task import BuildReference, SimpleBuildPlan


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


def source_unchanged(root, baseline):
    for name, row in baseline.items():
        p = root / name
        try:
            s = p.lstat()
            actual = dict(sha256=None if p.is_symlink() else file_hash(p), link=os.readlink(p) if p.is_symlink() else None, mode=s.st_mode, inode=s.st_ino, ctime_ns=s.st_ctime_ns)
        except OSError as exc:
            raise PlanContractError("原源码/测试缺失：" + name) from exc
        if actual != row:
            raise PlanContractError("原源码/测试被修改：" + name)


def observe_configuration(root: Path, system: str) -> dict:
    """从实际Cache读取generator和源码，绝不固定要求Ninja。"""
    if system != "cmake" and not cmake_roots(root):
        return dict(status="not_applicable", reason="Make不强制配置；Autotools仅在实际configure后观察config.status", configurations=[])
    rows = []
    for p in sorted(root.rglob("CMakeCache.txt")):
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
    return PlanStep(step_id="forge-generated-reset", role="configure", command="python3 -c " + shlex.quote(script), source="系统：依赖/配置变化后清理原输入集合以外的生成文件", expected="物理清理与逻辑后缀失效分别记录")


def primary_artifacts(*, task, reference, root, baseline, deadline):
    """独立组件覆盖＋结构/平台/来源检查；路径定位不改变构建动作。"""
    if reference.task_sha256 != _digest(task.model_dump(mode="json")):
        raise PlanContractError("独立参考与公开任务身份不一致")
    source_unchanged(root, baseline)
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
        self.configuration = observe_configuration(self.root, kwargs["plan"].build_system)
        self.primary = None
        self.layers = dict(command_build_passed=None, primary_build_completed=None, delivery="unobserved", author_tests="unobserved", clean_replay="unobserved", full_completed=None)
        self.timings = {}
        super().__init__(**kwargs)
        if meter is not None:
            self.started = meter.started_monotonic
        if reference.task_sha256 != _digest(self.plan.task.model_dump(mode="json")):
            raise PlanContractError("独立参考不属于当前公开任务")
        (self.directory / "source-baseline.json").write_text(json.dumps(self.baseline, ensure_ascii=False, indent=2) + "\n")

    def snapshot(self):
        return {**super().snapshot(), "configuration_state": self.configuration, "layers": dict(self.layers)}

    def _validate_step(self, step):
        validate_phase_command(step)

    def _execute(self, step):
        source_unchanged(self.root, self.baseline)
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
        source_unchanged(self.root, self.baseline)
        if not passed:
            return False
        if step.role in {"configure", "build"} and step.step_id != "forge-generated-reset":
            if self.plan.build_system != "autotools" or self.configuration["status"] != "passed" or cmake_roots(self.root):
                self.configuration = observe_configuration(self.root, self.plan.build_system)
            if self.plan.build_system == "autotools" and operations._command_invokes(step.command, "configure") and not cmake_roots(self.root):
                relative = PurePosixPath(step.workdir).relative_to("/workspace/repo")
                self.configuration = dict(status="passed" if (self.root / relative / "config.status").is_file() and (self.root / relative / "Makefile").is_file() else "failed", directory=relative.as_posix())
            self.manager.log_event(self._session, "simple.configuration_observed", step_id=step.step_id, **self.configuration)
            if self.configuration["status"] not in {"passed", "not_applicable"}:
                self.completed.pop(step.step_id, None)
                return False
        return True

    def _request_handoff(self, reason, step=None):
        result = super()._request_handoff(reason, step)
        if self.handoff:
            self.handoff.update(configuration_state=self.configuration, primary_components=self.primary)
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
        with (self.directory / "primary-result.json").open("x") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self._persist()
        return self.snapshot()

    def apply_revision(self, *, handoff_id, plan, reason):
        plan = SimpleBuildPlan.model_validate(plan)
        if plan.task != self.plan.task:
            raise PlanContractError("修订不得改变公开任务或资源身份")
        old = [s for s in self.plan.steps if s.step_id != "forge-generated-reset"]
        new = [s for s in plan.steps if s.step_id != "forge-generated-reset"]
        before = [(s.role, s.command, s.workdir) for s in old if s.role in {"dependency", "configure"}]
        after = [(s.role, s.command, s.workdir) for s in new if s.role in {"dependency", "configure"}]
        if before != after:
            position = next((i for i, s in enumerate(new) if s.role != "dependency"), len(new))
            new.insert(position, generated_reset_step(self.baseline))
            plan = SimpleBuildPlan(task=plan.task, revision=plan.revision, steps=tuple(new))
        elif any(s.step_id == "forge-generated-reset" for s in self.plan.steps):
            position = next((i for i, s in enumerate(new) if s.role != "dependency"), len(new))
            new.insert(position, next(s for s in self.plan.steps if s.step_id == "forge-generated-reset"))
            plan = SimpleBuildPlan(task=plan.task, revision=plan.revision, steps=tuple(new))
        super().apply_revision(handoff_id=handoff_id, plan=plan, reason=reason)
        self.primary = None
        self.layers["command_build_passed"] = self.layers["primary_build_completed"] = None

    def _post_command(self, step, timeout):
        from deerflow.tools.bound_compile_tools import _disables_strict_shell

        if _disables_strict_shell(step.command):
            raise PlanContractError("后续检查也必须保持严格Shell")
        source_unchanged(self.root, self.baseline)
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
        source_unchanged(self.root, self.baseline)
        return record, result

    def postchecks(self, *, author_test_seconds=60, delivery_seconds=30, replay=True, validation_scope="author_tests"):
        """主构建已冻结后独立计时；测试失败仍可观察构建重放，不吞主构建预算。"""
        if self.status != "primary_completed":
            raise PlanContractError("必须先确认主要构建")
        if validation_scope not in {"main_build", "author_tests"}:
            raise PlanContractError("未知构建验证范围")
        source_unchanged(self.root, self.baseline)
        artifacts = self.primary["artifacts"]
        destinations = [Path(p["path"]).name for p in artifacts]
        if len(set(destinations)) != len(destinations):
            raise PlanContractError("主产物交付名称歧义")
        command = "\n".join("cp -- " + shlex.quote(p["path"]) + " /artifacts/" + shlex.quote(Path(p["path"]).name) for p in artifacts)
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
            ids = [self.completed[s.step_id] for s in self.plan.steps] + [staged.command_id]
            builds = [self.completed[s.step_id] for s in self.plan.steps if s.role == "build"]
            start = time.monotonic()
            operations.submit_build_result_impl(session=self._session, supporting_command_id=builds[-1], recipe_command_ids=ids, verification_command_ids=[t["command_id"] for t in tests] if replayed_tests else [])
            self._session = self._load()
            self._expected_frontier = self._frontier()
            attempts = self._session.replay_attempts
            self.layers["clean_replay"] = "passed" if attempts and attempts[-1].status == "passed" and self._session.status == "verified" else "failed"
            self.timings["clean_replay_seconds"] = time.monotonic() - start
        source_unchanged(self.root, self.baseline)
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
        )
        (self.directory / "postcheck-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result
