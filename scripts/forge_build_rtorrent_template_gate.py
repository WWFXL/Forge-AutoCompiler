#!/usr/bin/env python3
"""实际通用模板→真实失败→脚本恢复的独立零Provider资格。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]
from forge_build_plan_predicate_gate import fake_model, reference_actions  # noqa: E402
from forge_build_rtorrent_arm import run_arm  # noqa: E402
from forge_build_rtorrent_bootstrap_alias import alias_boundary  # noqa: E402
from forge_build_rtorrent_recovery_gate import make_project  # noqa: E402
from forge_build_rtorrent_recovery_meter import RecoveryQualificationMeter  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.generated_file_boundary import FileBoundary  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.staged_verification import boundary_tool_actions  # noqa: E402
from deerflow.compile.tool_plan import ToolPlanNeedsAgent  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import observed_planner, propose_observed  # noqa: E402

IDENTITY = "cpp-build-rtorrent-actual-template-gate-v1"


def schedule():
    return [dict(project="rtorrent", method="tool_plan_workflow", case="actual_template", repetition=1)]


def task_boundary(original):
    value = alias_boundary(original).model_dump(mode="json")
    value["new_directories"].append(".git")
    # 标准configure的诊断输出；原文件/测试/40个生成结果权限不变。
    value["new_files"].append("config.log")
    return FileBoundary.model_validate(value)


def recovery_actions(reference):
    value = reference_actions(reference).model_dump(mode="json")
    value["reason"] = "仅工程脚本：从已冻结完整参考恢复；不评价真实Agent推理。删除模板诊断日志，重走依赖及配置，不保留不适用的根目录配置。"
    first = value["steps"][0]
    first["requires"] = ["cleanup-template"]
    value["steps"].insert(0, dict(step_id="cleanup-template", role="dependency", command="rm -f -- config.log", source="本身份预声明的模板诊断日志", expected="清理模板的失败配置日志", workdir="/workspace/repo", requires=[]))
    return value


def actual_planner(boundary):
    def generator(task, root):
        try:
            return boundary_tool_actions(task, root, boundary)
        except ToolPlanNeedsAgent as exc:
            # 不允许脚本参考冒充初始模板；资格不能先拒答再直接提供人工方案。
            raise PlanContractError("实际模板未准入，本身份停止：" + str(exc)) from exc

    def recovery_only(**kwargs):
        if kwargs.get("current_plan") is None or not kwargs.get("handoff"):
            raise PlanContractError("仅在真实Workflow交接后允许脚本恢复")
        if kwargs["current_plan"].revision != 1:
            raise PlanContractError("本身份最多一次脚本恢复，不自动重试")
        return propose_observed(**kwargs)

    return observed_planner("tool", agent=recovery_only, generator=generator)


def run_slot(spec, folder, *, executor=run_arm):
    model = fake_model([spec["recovery_actions"]])
    return executor(
        item=spec["project"],
        arm="plan",
        protocol=spec,
        root=folder,
        model=model,
        reference=spec["reference"],
        meter_factory=RecoveryQualificationMeter,
        planner=actual_planner(FileBoundary.model_validate(spec["project"]["file_boundary"])),
        command_timeout_seconds=1200,
        replay_timeout_seconds=1200,
    )


def validate(spec):
    if (spec["identity"], spec["schedule"], spec["provider_calls"], spec["credentials_read"], spec["max_model_cost_usd"]) != (IDENTITY, schedule(), 0, False, 0):
        raise PlanContractError("固定身份/一次模板槽/零Provider边界变化")
    if spec["reserve_seconds"] != 2700 or spec["cleanup_timeout_seconds"] != 120:
        raise PlanContractError("执行资源/停止预留变化")
    parent = Path(spec["reference_evidence"]["root"])
    if audit(parent)["inventory_canonical_sha256"] != spec["reference_evidence"]["inventory_sha256"] or not json.loads((parent / "result.json").read_text())["qualified"]:
        raise PlanContractError("完整参考证据变化")
    alias = Path(spec["alias_evidence"]["root"])
    if audit(alias)["inventory_canonical_sha256"] != spec["alias_evidence"]["inventory_sha256"] or not json.loads((alias / "result.json").read_text())["qualified"]:
        raise PlanContractError("生成形式校准未闭合")
    original = json.loads((parent / "protocol.json").read_text())
    task, reference = make_project(original["plan"])
    if (task, reference, task_boundary(original["file_boundary"]).model_dump(mode="json"), recovery_actions(reference)) != (spec["project"]["task"], spec["reference"], spec["project"]["file_boundary"], spec["recovery_actions"]):
        raise PlanContractError("任务/完整测试/精确交付/生成边界/脚本动作变化")
    if digest(Path(spec["project"]["source_archive"])) != task["source_archive_sha256"]:
        raise PlanContractError("源码归档变化")
    for name, expected in spec["components"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != expected:
            raise PlanContractError("冻结组件变化：" + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    spec = json.loads(args.protocol.read_text())
    validate(spec)
    before_deadline(spec["deadline_utc"], spec["reserve_seconds"])
    if args.validate_only:
        print(json.dumps(dict(valid=True, slots=1, provider_calls=0)))
        return 0
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", spec)
    write_json(root / "execution.json", dict(release=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), provider_calls=0))
    rows, reason = [], "initialization_not_completed"
    try:
        folder = root / "slot-1"
        folder.mkdir()
        row = {**run_slot(spec, folder), **spec["schedule"][0]}
        rows.append(row)
        reason = None if row["strict_completed"] else "qualification_failed"
        print(json.dumps(dict(strict=row["strict_completed"], error=row.get("error_message")), ensure_ascii=False), flush=True)
    finally:
        write_json(
            root / "result.json", dict(identity=IDENTITY, kind="zero_provider_actual_template_qualification", provider_calls=0, credentials_read=False, rows=rows, unobserved_schedule=spec["schedule"][len(rows) :], stop_reason=reason)
        )
        print(json.dumps(seal(root, spec, ROOT)), flush=True)
    return 0 if rows and rows[0]["strict_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
