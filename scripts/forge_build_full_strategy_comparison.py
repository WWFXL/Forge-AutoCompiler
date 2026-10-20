#!/usr/bin/env python3
"""为已通过完整门禁的三策略执行器绑定新授权，不改变任何策略行为。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import forge_build_full_strategy_runtime as runtime

from deerflow.compile.plan_workflow import PlanContractError

IDENTITY = "cpp-build-full-strategy-comparison-v1"
PARENT_PATH = "benchmarks/manifests/cpp-build-full-strategy-runtime-v2.json"
PARENT_SHA256 = "41097a102f9e623f0da808b6a930a04f613a4fd2a67743adb114b7197b28a959"
GATE_ROOT = Path("/home/yiwei/.codex/outputs/forge-full-strategy-gate-v2")
GATE_INVENTORY = "08286b1789beabeef814fda35d735da3575984a82d6489d189eb9ca9c13a841f"
GATE_AUDIT = Path("/home/yiwei/.codex/outputs/forge-three-strategy-session-2026-10-20/gate-v2-independent.json")
GATE_AUDIT_SHA256 = "aea07ebeca576416c13e283cae7d4ee9473eda3b563838815ddb8017ac745251"
DEADLINE = "2026-10-20T07:47:40Z"
ADDED_COMPONENTS = {
    "scripts/forge_build_full_strategy_comparison.py",
    "backend/tests/test_build_full_strategy_comparison.py",
    "benchmarks/preregistrations/cpp-build-full-strategy-comparison-v1.md",
}
ORIGINAL_REQUIRE_GATE = runtime.require_gate


def check_projection(protocol, parent):
    """新授权只准改变明确列出的外层元数据，不能趁续窗改变实验。"""
    if protocol["identity"] != IDENTITY or protocol["issue"] != 538 or protocol["deadline_utc"] != DEADLINE:
        raise PlanContractError("新实验身份或授权窗口不符")
    mutable = {"identity", "issue", "authorization", "deadline_utc", "components"}
    if {k: v for k, v in protocol.items() if k not in mutable} != {k: v for k, v in parent.items() if k not in mutable}:
        raise PlanContractError("新授权不得改变父协议的任务、顺序、模型、资源或验收")
    expected_keys = set(parent["components"]) | ADDED_COMPONENTS
    if set(protocol["components"]) != expected_keys or any(protocol["components"][k] != v for k, v in parent["components"].items()):
        raise PlanContractError("父门禁执行组件发生变化")


def require_gate(protocol_path, gate_root):
    """核验原完整门禁及独立审计；新截止不要求重跑相同工程实验。"""
    if gate_root.resolve() != GATE_ROOT.resolve():
        raise PlanContractError("只能使用已封存的完整v2门禁")
    parent_path = runtime.REPO_ROOT / PARENT_PATH
    if runtime.digest(parent_path) != PARENT_SHA256 or runtime.digest(GATE_AUDIT) != GATE_AUDIT_SHA256:
        raise PlanContractError("父协议或独立审计收据变化")
    ORIGINAL_REQUIRE_GATE(parent_path, gate_root)
    independent = json.loads(GATE_AUDIT.read_text())
    seal = json.loads((gate_root / "seal.json").read_text())
    if not independent["valid"] or not independent["gate_coverage_complete"] or independent["inventory_sha256"] != GATE_INVENTORY or seal["inventory_canonical_sha256"] != GATE_INVENTORY:
        raise PlanContractError("完整门禁或独立审计未闭合")


def validate(protocol):
    parent_path = runtime.REPO_ROOT / PARENT_PATH
    if runtime.digest(parent_path) != PARENT_SHA256:
        raise PlanContractError("父协议变化")
    parent = json.loads(parent_path.read_text())
    check_projection(protocol, parent)
    runtime.before_deadline(protocol["deadline_utc"], runtime.RESERVE)
    if runtime.digest(runtime.REPO_ROOT / runtime.DESIGN) != protocol["design_sha256"]:
        raise PlanContractError("科学设计变化")
    for name, expected in protocol["components"].items():
        source = (runtime.REPO_ROOT / name).resolve()
        if not source.is_relative_to(runtime.REPO_ROOT) or runtime.digest(source) != expected:
            raise PlanContractError(f"冻结组件变化：{name}")
    design = json.loads((runtime.REPO_ROOT / runtime.DESIGN).read_text())
    parents = {Path(design["role_evidence"]["root"]): design["role_evidence"]["inventory_sha256"]}
    for item in [*protocol["projects"], *protocol["gate_projects"]]:
        parents[Path(item["reference_root"])] = item["reference_inventory_sha256"]
        if runtime.digest(Path(item["source_archive"])) != item["task"]["source_archive_sha256"]:
            raise PlanContractError("固定源码归档变化")
    for root, expected in parents.items():
        if runtime.audit(root)["inventory_canonical_sha256"] != expected:
            raise PlanContractError("角色或参考证据变化")
    # 真实运行只向模型提供任务与源码；人工正确方案不加载到执行参数。
    return {}


def main():
    if "--qualify" in sys.argv:
        raise PlanContractError("本身份仅执行真实比较，工程门禁保持旧封存身份")
    runtime.IDENTITY = IDENTITY
    runtime.validate = validate
    runtime.require_gate = require_gate
    return runtime.main()


if __name__ == "__main__":
    raise SystemExit(main())
