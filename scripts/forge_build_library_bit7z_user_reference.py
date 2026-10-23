#!/usr/bin/env python3
"""在镜像已有普通用户上下文执行原bit7z完整测试，原root失败保留。"""

from __future__ import annotations

import copy
import json
import shlex
from pathlib import Path
from unittest.mock import patch

import forge_build_library_elfio_qualification as runner
from forge_typed_evidence import audit, digest

from deerflow.compile.plan_cross_system import before_deadline

IDENTITY = "cpp-build-library-bit7z-user-reference-v1"


def ordinary_user_item(old):
    item = copy.deepcopy(next(p for p in old["projects"] if p["name"] == "bit7z"))
    context_check = shlex.quote(
        "import os,pwd,pathlib; "
        "assert os.geteuid()==1000; "
        "assert os.environ.get('HOME')==pwd.getpwuid(1000).pw_dir=='/home/ubuntu'; "
        "assert str(pathlib.Path(os.environ['HOME']).parent)!='/'; "
        "print('FORGE_BIT7Z_TEST_CONTEXT uid=1000 home=/home/ubuntu')"
    )
    prefix = (
        "install -d -o ubuntu -g ubuntu /home/ubuntu\n"
        "chown -R ubuntu:ubuntu /workspace/repo\n"
        f"runuser --user ubuntu -- python3 -c {context_check}\n"
        "runuser --user ubuntu -- "
    )
    for step in [*item["task"]["verification_steps"], *item["plan"]["steps"]]:
        if step["role"] == "smoke":
            step["command"] = prefix + step["command"]
            step["required_output"].append("FORGE_BIT7Z_TEST_CONTEXT uid=1000 home=/home/ubuntu")
    item["task_scope"] += "；仅作者测试以镜像已有ubuntu(uid1000、原/home/ubuntu)运行，不覆盖HOME变量；保持全部默认用例和权限测试，构建仍为原root"
    return item


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0:
        raise ValueError("独立环境资格身份或零模型边界变化")
    before_deadline(protocol["deadline_utc"], 3900)
    parent = Path(protocol["parent_raw"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("旧root失败证据变化")
    old = json.loads((parent / "protocol.json").read_text())
    if protocol["projects"] != [ordinary_user_item(old)]:
        raise ValueError("超出普通用户测试上下文修正范围")
    for key in ("plan_budget", "replay_timeout_seconds", "new_project_reserve_seconds", "deadline_utc"):
        if protocol[key] != old[key]:
            raise ValueError("原时间或资源变化")
    for name, expected in protocol["components"].items():
        if digest(runner.ROOT / name) != expected:
            raise ValueError("冻结组件变化：" + name)


def main():
    with patch.object(runner, "IDENTITY", IDENTITY), patch.object(runner, "validate", validate):
        return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
