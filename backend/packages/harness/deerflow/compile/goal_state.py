"""任务约束与实际配置的早期核对；不改变最终测试及交付裁判。"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.source_preparation import PREPARATION_ID, PreparedWorkflow
from deerflow.compile.unified_plan_equivalent import BuildActions, assemble_plan

FALSE_VALUES = {"", "0", "OFF", "NO", "FALSE", "N", "IGNORE", "NOTFOUND"}


def enabled(value: str) -> bool:
    return value.upper() not in FALSE_VALUES and not value.upper().endswith("-NOTFOUND")


@dataclass(frozen=True)
class ConfigurationGoal:
    cache_path: str
    key: str
    expected: bool
    verifier_sha256: str
    default: str | None = None


def configuration_goals(task) -> tuple[ConfigurationGoal, ...]:
    """只解释已公开固定任务中可静态确定的布尔要求，不执行验证脚本。

    当前支持原任务的 requirements 字面字典和显式静态库默认约束。
    不推断自然语言、版本范围或任意Python的语义；没有支持的表达式不造约束。
    """
    goals = {}
    for step in task.verification_steps:
        try:
            tokens = shlex.split(step.command)
        except ValueError:
            continue
        for index in range(len(tokens) - 2):
            if tokens[index : index + 2] not in (["python3", "-c"], ["python", "-c"]):
                continue
            try:
                tree = ast.parse(tokens[index + 2])
            except SyntaxError:
                continue
            # 只识别仓库既有的配置检查形式，避免把日志/依赖中的常量当成任务。
            paths = [
                n.args[0].value
                for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "Path"
                and len(n.args) == 1
                and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)
                and n.args[0].value.endswith("CMakeCache.txt")
            ]
            assignments = [n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "requirements"]
            if len(paths) != 1 or len(assignments) != 1:
                continue
            path = PurePosixPath(paths[0])
            if path.is_absolute() or ".." in path.parts or path.as_posix() != paths[0]:
                raise PlanContractError("任务配置路径必须位于仓库内")
            try:
                requirements = ast.literal_eval(assignments[0].value)
            except (ValueError, TypeError, SyntaxError):
                continue
            if not isinstance(requirements, dict) or not all(isinstance(k, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) and type(v) is bool for k, v in requirements.items()):
                continue
            digest = hashlib.sha256(step.command.encode()).hexdigest()
            items = [ConfigurationGoal(str(path), key, expected, digest) for key, expected in requirements.items()]
            # 原固定脚本只有 if True 下这个断言才要求默认静态库，不能解释 if False。
            for statement in tree.body:
                if isinstance(statement, ast.If) and isinstance(statement.test, ast.Constant) and statement.test.value is True:
                    for assertion in statement.body:
                        if isinstance(assertion, ast.Assert) and ast.dump(assertion.test) == ast.dump(ast.parse("not enabled(cache.get('BUILD_SHARED_LIBS','OFF'))", mode="eval").body):
                            items.append(ConfigurationGoal(str(path), "BUILD_SHARED_LIBS", False, digest, "OFF"))
            for goal in items:
                identity = (goal.cache_path, goal.key)
                if identity in goals and goals[identity].expected != goal.expected:
                    raise PlanContractError("任务配置要求相互矛盾")
                goals[identity] = goal
    return tuple(goals.values())


def _inside(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise PlanContractError("状态证据路径越出源码目录")
    return path


def declared_options(root: Path) -> set[str]:
    """只允许原作者声明的option；依赖探测变量绝不作为可修订开关。"""
    result = set()
    candidates = [root / "CMakeLists.txt", *(root / "cmake").rglob("*.cmake")]
    for candidate in candidates:
        if not candidate.is_file() or candidate.stat().st_size > 1_048_576:
            continue
        path = _inside(root, str(candidate.relative_to(root)))
        text = re.sub(r"#.*", "", path.read_text(errors="replace"))
        result.update(re.findall(r"(?i)\b(?:option|cmake_dependent_option)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)", text))
        if re.search(r"(?i)\binclude\s*\(\s*CTest\s*\)", text):
            result.add("BUILD_TESTING")
    return result


def observe_configuration(root: Path, goals: tuple[ConfigurationGoal, ...]) -> dict:
    """读取执行器刚生成的缓存，绑定文件哈希；缺证据保持unknown。"""
    rows, caches = [], {}
    for goal in goals:
        if goal.cache_path not in caches:
            path = _inside(root, goal.cache_path)
            cache, digest = {}, None
            if path.is_file() and path.stat().st_size <= 1_048_576:
                raw = path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                for line in raw.decode(errors="replace").splitlines():
                    match = re.fullmatch(r"([^#/:=][^:=]*):([^=]+)=(.*)", line)
                    if match:
                        cache[match[1]] = (match[2], match[3])
            caches[goal.cache_path] = (cache, digest)
        cache, digest = caches[goal.cache_path]
        actual = cache.get(goal.key, (None, goal.default))[1] if digest else None
        rows.append(
            {
                **asdict(goal),
                "actual": actual,
                "cache_type": cache.get(goal.key, (None, None))[0],
                "status": "unknown" if actual is None else "satisfied" if enabled(actual) == goal.expected else "violated",
                "evidence_sha256": digest,
                "source_directory": cache.get("CMAKE_HOME_DIRECTORY", (None, None))[1],
            }
        )
    statuses = {row["status"] for row in rows}
    status = "violated" if "violated" in statuses else "unknown" if not rows or "unknown" in statuses else "satisfied"
    return {"status": status, "goals": rows, "scope": "explicit_cmake_configuration_only"}


def direct_configuration_revision(task, current_plan, observation, source_root):
    """仅对同一根项目、同一缓存中已存在的BOOL开关追加一次配置修订。

    不改写任意Shell、不清空源码、不强设依赖探测结果。补充configure动作进入
    正式命令和重放配方，原失败命令保留。未知或多根配置交给原Agent。
    """
    # 修订只能消费当前任务和仍然相同的执行证据，不能消费模型自报配置。
    actual = observe_configuration(source_root, configuration_goals(task))
    previous = [{k: v for k, v in row.items() if k != "evidence_path"} for row in observation.get("goals", [])]
    if previous != actual["goals"]:
        return None
    rows = actual["goals"]
    bad = [row for row in rows if row["status"] != "satisfied"]
    if not bad or any(row["status"] != "violated" or row["cache_type"] != "BOOL" for row in bad):
        return None
    options = declared_options(source_root)
    if any(row["key"].startswith("HAVE_") or row["key"] not in options or row["source_directory"] != "/workspace/repo" for row in bad):
        return None
    cache_paths = {row["cache_path"] for row in rows}
    if len(cache_paths) != 1:
        return None
    build_directory = str(PurePosixPath("/workspace/repo") / PurePosixPath(next(iter(cache_paths))).parent)
    core = [s for s in current_plan.steps if s.role in ("dependency", "configure", "build") and s.step_id != PREPARATION_ID]
    position = next((i for i, step in enumerate(core) if step.role == "build"), None)
    if position is None:
        return None
    identifier = "goal-configure-" + str(current_plan.revision + 1)
    if any(step.step_id == identifier for step in current_plan.steps):
        return None
    flags = [f"-D{row['key']}:BOOL={'ON' if row['expected'] else 'OFF'}" for row in bad]
    from deerflow.compile.plan_workflow import PlanStep

    correction = PlanStep(
        step_id=identifier,
        role="configure",
        command=shlex.join(["cmake", "-S", "/workspace/repo", "-B", build_directory, *flags]),
        requires=tuple(s.step_id for s in core[:position]),
        source="原任务显式布尔约束、实际缓存及原作者option声明",
        expected="修正已观察的配置偏离，再执行受影响编译后缀",
    )
    core.insert(position, correction)
    core[position + 1] = core[position + 1].model_copy(update={"requires": tuple(dict.fromkeys((*core[position + 1].requires, identifier)))})
    reason = "状态选择：实际BOOL开关偏离显式任务要求，执行一次有界配置修订"
    plan = assemble_plan(task, BuildActions(reason=reason, steps=[s.model_dump() for s in core]), revision=current_plan.revision + 1)
    return plan, reason


class GoalStateWorkflow(PreparedWorkflow):
    """在最后configure后、首次build前核对不可被恢复删除的任务约束。"""

    def __init__(self, **kwargs):
        self.goals = configuration_goals(SimpleNamespace(verification_steps=tuple(s for s in kwargs["plan"].steps if s.role == "smoke")))
        self.goal_state = {"status": "unknown", "goals": [], "scope": "not_yet_observed"}
        self.goal_blocked = False
        super().__init__(**kwargs)

    def snapshot(self):
        return {**super().snapshot(), "configuration_state": self.goal_state}

    def apply_revision(self, **kwargs):
        super().apply_revision(**kwargs)
        # 新方案必须重新观测；旧配置冲突不能覆盖新依赖命令失败的真实原因。
        self.goal_blocked = False
        self.goal_state = {"status": "unknown", "goals": [], "scope": "revision_requires_fresh_observation"}
        self._persist()

    def _check_goals(self, step):
        if not self.goals:
            return True
        self.goal_state = {**observe_configuration(self.source_root, self.goals), "after_step_id": step.step_id, "revision": self.plan.revision, "command_frontier": self._expected_frontier}
        # 缓存随后会被重新配置覆盖，按内容保存观测时原字节，便于解释动作依据。
        evidence = self.manager.local_logs_dir(self._session) / "goal-state"
        evidence.mkdir(exist_ok=True)
        for name in {goal.cache_path for goal in self.goals}:
            rows = [row for row in self.goal_state["goals"] if row["cache_path"] == name]
            digest = rows[0]["evidence_sha256"]
            if digest:
                raw = _inside(self.source_root, name).read_bytes()
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise PlanContractError("观测期间配置证据变化")
                target = evidence / (digest + ".txt")
                if not target.exists():
                    with target.open("xb") as handle:
                        handle.write(raw)
                for row in rows:
                    row["evidence_path"] = "logs/goal-state/" + target.name
        self.manager.log_event(self._session, "goal_state.observed", **self.goal_state)
        self.goal_blocked = self.goal_state["status"] != "satisfied"
        return not self.goal_blocked

    def _execute(self, step):
        if step.role == "build" and not any(s.role == "build" and s.step_id in self.completed for s in self.plan.steps):
            if not self._check_goals(step):
                return False
        passed = super()._execute(step)
        last_configure = next((s.step_id for s in reversed(self.plan.steps) if s.role == "configure"), None)
        if passed and step.role == "configure" and step.step_id == last_configure:
            return self._check_goals(step)
        return passed

    def _request_handoff(self, reason, step=None):
        if self.goal_blocked:
            reason = "configuration_goal_" + self.goal_state["status"]
        super()._request_handoff(reason, step)
        if self.status == "needs_handoff":
            self.handoff["configuration_state"] = self.goal_state
            self.handoff["persistent_configuration_goals"] = [asdict(goal) for goal in self.goals]
            (self.directory / f"handoff-{self.handoff['handoff_id']}.json").write_text(json.dumps(self.handoff, ensure_ascii=False, indent=2) + "\n")
            self._persist()
        return self.snapshot()


def goal_state_planner(original):
    """直接修订最多一次；其余交接保留原Agent、全部费用和恢复预算。"""
    rule_used = False

    def planner(**kwargs):
        nonlocal rule_used
        handoff, current = kwargs.get("handoff"), kwargs.get("current_plan")
        if current is not None and (not handoff or handoff.get("plan_sha256") != current.fingerprint()):
            raise PlanContractError("配置状态交接与当前方案不匹配")
        if current is not None and handoff and not rule_used:
            revision = direct_configuration_revision(kwargs["task"], current, handoff.get("configuration_state", {}), kwargs["source_root"])
            if revision is not None:
                rule_used = True
                plan, reason = revision
                kwargs["meter"].ledger.append("goal_state.action", action="direct_configuration_revision", revision=plan.revision, observation=handoff["configuration_state"])
                kwargs["meter"].ledger.save(f"goal-rule-plan-{plan.revision}.json", plan.model_dump(mode="json"))
                return plan, reason
        kwargs["meter"].ledger.append("goal_state.action", action="agent", phase="recovery" if current else "initial")
        return original(**kwargs)

    return planner
