"""新身份的生成文件边界；独立于冻结的旧源码检查器。"""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import shlex
import zlib
from pathlib import Path, PurePosixPath
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deerflow.compile.plan_workflow import PlanContractError


class GenerationRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command: str = Field(min_length=1)
    workdir: str = "/workspace/repo"
    inputs: tuple[str, ...] = Field(min_length=1)
    outputs: dict[str, str] = Field(min_length=1)
    evidence: str = Field(min_length=1)


class FileBoundary(BaseModel):
    """默认保护全部原文件；输出权限由任务审阅者授予，Agent不能扩展。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline: dict[str, str] = Field(min_length=1)
    protected_inputs: tuple[str, ...] = Field(min_length=1)
    generations: tuple[GenerationRule, ...] = ()
    new_files: tuple[str, ...] = ()
    new_directories: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        outputs = {p for r in self.generations for p in r.outputs}
        names = [*self.baseline, *self.protected_inputs, *outputs, *self.new_files, *self.new_directories, *(p for r in self.generations for p in r.inputs)]
        for name in names:
            p = PurePosixPath(name)
            if not name or name != p.as_posix() or p.is_absolute() or ".." in p.parts or name == "." or "\\" in name or "\x00" in name:
                raise ValueError("文件边界必须是规范相对路径，不接受glob或父目录")
            if any(c in name for c in "*?[]"):
                raise ValueError("输出必须是精确路径，不能使用glob")
        for value in [*self.baseline.values(), *(v for r in self.generations for v in r.outputs.values())]:
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("文件指纹必须是SHA256")
        if not set(self.protected_inputs) <= self.baseline.keys() or set(self.protected_inputs) & outputs:
            raise ValueError("作者源码/测试/语义输入不得声明为生成输出")
        for rule in self.generations:
            if not set(rule.inputs) <= self.baseline.keys() or set(rule.inputs) & outputs:
                raise ValueError("生成关系必须来自受保护的原输入")
            if rule.workdir != "/workspace/repo":
                raise ValueError("当前生成命令限定仓库根目录")
        if len({(r.command, r.workdir) for r in self.generations}) != len(self.generations):
            raise ValueError("生成命令身份不能重复")
        for directory in self.new_directories:
            if any(p == directory or p.startswith(directory + "/") for p in [*self.baseline, *outputs]):
                raise ValueError("新输出目录不能覆盖原文件或精确生成路径")
        if set(self.new_files) & (self.baseline.keys() | outputs):
            raise ValueError("新文件权限不能覆盖原文件或生成关系")
        return self

    def fingerprint(self):
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    @property
    def protected(self):
        generated = {p for r in self.generations for p in r.outputs}
        return {p: h for p, h in self.baseline.items() if p not in generated}


def guard_main(policy, command, workdir, root_path="/workspace/repo"):
    """复制到显式recipe的stdlib执行器；Linux事件缺失或溢出时拒绝。"""
    import ctypes
    import hashlib
    import json
    import os
    import pathlib
    import stat
    import struct
    import subprocess

    root = pathlib.Path(root_path)
    if root.is_symlink() or root.resolve() != root:
        raise ValueError("仓库根必须为真实规范目录")
    baseline = policy["baseline"]
    rules = policy["generations"]
    outputs = {p for r in rules for p in r["outputs"]}
    protected = set(baseline) - outputs
    allowed = {p: {baseline[p]} if p in baseline else set() for p in outputs}
    for rule in rules:
        for p, h in rule["outputs"].items():
            allowed[p].add(h)
    active = next((r for r in rules if (r["command"], r["workdir"]) == (command, workdir)), None)

    def snapshot():
        rows = {}
        for directory, dirs, files in os.walk(root, followlinks=False):
            for name in dirs + files:
                path = pathlib.Path(directory) / name
                relative = path.relative_to(root).as_posix()
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode):
                    target = path.resolve(strict=True)
                    if relative in baseline or not target.is_relative_to(root) or not target.is_file() or target.relative_to(root).as_posix() in baseline:
                        raise ValueError("原文件/越界/保护输入别名链接:" + relative)
                    rows[relative] = "link:" + os.readlink(path)
                    continue
                if not stat.S_ISREG(mode) and not stat.S_ISDIR(mode):
                    raise ValueError("边界不接纳特殊文件:" + relative)
                if stat.S_ISREG(mode):
                    rows[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        for p in protected:
            if rows.get(p) != baseline[p]:
                raise ValueError("保护文件被修改/删除:" + p)
        for p in outputs & rows.keys():
            if rows[p] not in allowed[p]:
                raise ValueError("生成内容不属于预先核验的标准生成结果:" + p)
        for p in rows.keys() - baseline.keys() - outputs:
            if p not in policy["new_files"] and not any(p.startswith(d + "/") for d in policy["new_directories"]):
                raise ValueError("未声明的新文件:" + p)
            if p not in policy["new_files"] and pathlib.PurePosixPath(p).suffix.lower() in {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".sh", ".py"}:
                raise ValueError("新输出目录不能隐式授予源码/测试写权限:" + p)
        return rows

    # 必须在启动子进程之前安装监测。只监测原文件及其祖先目录，输出流量不进入队列。
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "inotify不可用")
    watches = {}
    watched = set(protected) | outputs
    directories = {"."} | {str(parent) for p in watched for parent in pathlib.PurePosixPath(p).parents}
    # MODIFY, ATTRIB, CLOSE_WRITE, MOVED_FROM/TO, CREATE, DELETE, DELETE_SELF, MOVE_SELF。
    mask = 0x2 | 0x4 | 0x8 | 0x40 | 0x80 | 0x100 | 0x200 | 0x400 | 0x800
    try:
        for directory in sorted(directories):
            path = root / directory
            if not path.is_dir() or path.is_symlink():
                raise ValueError("原文件祖先目录不存在或是链接:" + directory)
            wd = libc.inotify_add_watch(fd, os.fsencode(path), mask)
            if wd < 0:
                raise OSError(ctypes.get_errno(), "无法监测:" + directory)
            watches[wd] = directory
        before = snapshot()
        before_meta = {p: ((root / p).stat().st_ino, (root / p).stat().st_ctime_ns, (root / p).stat().st_mode) for p in protected}
        result = subprocess.run(["bash", "-c", "set -euo pipefail\n" + command], cwd=workdir, check=False)
        violations, generated_writes = set(), set()
        while True:
            try:
                events = os.read(fd, 1024 * 1024)
            except BlockingIOError:
                break
            if not events:
                break
            offset = 0
            while offset < len(events):
                wd, event, _, size = struct.unpack_from("iIII", events, offset)
                name = os.fsdecode(events[offset + 16 : offset + 16 + size].split(b"\0", 1)[0])
                offset += 16 + size
                if event & 0x4000 or wd not in watches:
                    raise ValueError("文件写入事件溢出或来源不明")
                parent = watches[wd]
                path = str(pathlib.PurePosixPath(parent) / name) if name else parent
                if path in watched or path in directories - {"."}:
                    if path in outputs:
                        generated_writes.add(path)
                    else:
                        violations.add(path)
        after = snapshot()
        for p in protected:
            st = (root / p).stat()
            if (st.st_ino, st.st_ctime_ns, st.st_mode) != before_meta[p]:
                violations.add(p)
        changed = {p for p in outputs if before.get(p) != after.get(p)} | generated_writes
        if violations:
            raise ValueError("检测到保护文件或祖先目录写入，即使内容已恢复:" + repr(sorted(violations)))
        if changed and (active is None or not changed <= active["outputs"].keys()):
            raise ValueError("生成文件被非声明命令写入:" + repr(sorted(changed)))
        if active and any(after.get(p) != h for p, h in active["outputs"].items()):
            raise ValueError("标准生成命令未产生声明结果")
        print(
            "FORGE_FILE_BOUNDARY="
            + json.dumps({"command_exit_code": result.returncode, "generated_changes": [{"path": p, "before": before.get(p), "after": after.get(p)} for p in sorted(changed)], "protected_count": len(protected)}, sort_keys=True),
            flush=True,
        )
        return result.returncode
    finally:
        os.close(fd)


PREFIX = "python3 -c "


def guarded_command(policy: FileBoundary, command: str, workdir: str) -> str:
    from deerflow.compile.operations import infer_command_roles
    from deerflow.tools.bound_compile_tools import _disables_strict_shell

    if _disables_strict_shell(command) or len(infer_command_roles(command)) > 1 or "/repro" in command:
        raise PlanContractError("原命令不能关闭严格Shell、混合阶段或访问/repro")
    payload = {"policy": policy.model_dump(mode="json"), "command": command, "workdir": workdir}
    encoded = base64.b64encode(zlib.compress(json.dumps(payload, ensure_ascii=False).encode())).decode()
    source = inspect.getsource(guard_main) + "\nimport base64,json,zlib\np=json.loads(zlib.decompress(base64.b64decode(" + repr(encoded) + ")))\nraise SystemExit(guard_main(**p))\n"
    return PREFIX + shlex.quote(source)


def guard_plan(policy, plan):
    return plan.model_copy(update={"steps": tuple(step.model_copy(update={"command": guarded_command(policy, step.command, step.workdir)}) for step in plan.steps)})


def original_command(policy, command):
    """只还原本实现按同一policy产生的命令，用于可读状态；记录/recipe仍保留原文。"""
    import ast

    parts = shlex.split(command)
    if len(parts) != 3 or parts[:2] != ["python3", "-c"]:
        raise PlanContractError("缺少共同文件边界包装")
    marker = "\np=json.loads(zlib.decompress(base64.b64decode("
    try:
        encoded = ast.literal_eval(parts[2].split(marker)[1].split(")))\nraise SystemExit")[0])
        payload = json.loads(zlib.decompress(base64.b64decode(encoded)))
        if payload["policy"] != policy.model_dump(mode="json") or guarded_command(policy, payload["command"], payload["workdir"]) != command:
            raise ValueError("包装身份变化")
        return payload["command"]
    except (ValueError, IndexError, KeyError) as exc:
        raise PlanContractError("文件边界包装与任务身份不符") from exc


def original_plan(policy, plan, *, strip_preparation=False):
    steps = tuple(step.model_copy(update={"command": original_command(policy, step.command)}) for step in plan.steps)
    if strip_preparation:
        steps = tuple(s for s in steps if s.step_id != "forge-source-prepare")
    return plan.model_copy(update={"steps": steps})


def file_hashes(root: Path):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file() and not p.is_symlink()}
