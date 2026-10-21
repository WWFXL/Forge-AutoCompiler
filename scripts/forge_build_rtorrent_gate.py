#!/usr/bin/env python3
"""rtorrent三策略五槽零Provider资格；不存在付费执行或凭据读取分支。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]
from forge_build_auto_provenance_probe import automatic_gate_model  # noqa: E402
from forge_build_plan_predicate_gate import fake_model, reference_actions  # noqa: E402
from forge_build_referenced_meter import ReferencedQualificationMeter  # noqa: E402
from forge_build_rtorrent_arm import run_arm  # noqa: E402
from forge_build_unified_plan import METHODS  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.generated_file_boundary import FileBoundary  # noqa: E402
from deerflow.compile.plan_agent_provenance import run_tool_agent_automatic  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.staged_verification import StagedVerificationTask, boundary_tool_actions  # noqa: E402
from deerflow.compile.unified_plan_equivalent import assemble_plan  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import observed_planner  # noqa: E402

IDENTITY = "cpp-build-rtorrent-three-strategy-gate-v1"


def schedule():
    return [dict(project="rtorrent", method=m, case=c, repetition=1) for c, methods in (("normal", METHODS), ("controlled_recovery", METHODS[:2])) for m in methods]


def make_project(reference):
    value = copy.deepcopy(reference)
    value["plan_id"] = "rtorrent-common-staged-v1"
    steps = value["steps"]
    next(s for s in steps if s["step_id"] == "build-rtorrent")["step_id"] = "build"
    next(s for s in steps if s["role"] == "artifact_stage")["step_id"] = "stage"
    next(s for s in steps if s["step_id"] == "full-author-tests")["requires"] = ["stage"]
    task = {k: v for k, v in value.items() if k not in ("steps", "revision")}
    task["verification_steps"] = [s for s in steps if s["role"] == "smoke"]
    task = StagedVerificationTask.model_validate(task)
    from deerflow.compile.unified_plan_equivalent import BuildActions

    actions = BuildActions(reason="仅零Provider参考脚本；不进入真实Agent", steps=[s for s in steps if s["role"] in ("dependency", "configure", "build")])
    plan = assemble_plan(task, actions, revision=1)
    return task.model_dump(mode="json"), plan.model_dump(mode="json")


def tool_gate_model(reference):
    # run_fixed_tests一次执行所有固定smoke；两个验证步骤不能导致整套测试重复。
    value = copy.deepcopy(reference)
    seen = False
    steps = []
    for step in value["steps"]:
        if step["role"] == "smoke":
            if seen:
                continue
            seen = True
        steps.append(step)
    value["steps"] = steps
    return automatic_gate_model(value)


def run_slot(protocol, folder, slot, *, executor=run_arm):
    reference = protocol["reference"]
    good = reference_actions(reference).model_dump(mode="json")
    values = [good]
    if slot["case"] == "controlled_recovery":
        bad = copy.deepcopy(good)
        bad["steps"][-1]["command"] = "false"
        values = [bad, good]
    active = fake_model(values)
    boundary = FileBoundary.model_validate(protocol["project"]["file_boundary"])
    base = observed_planner("tool" if slot["method"] == METHODS[0] else "model", generator=lambda task, root: boundary_tool_actions(task, root, boundary))

    def planner(**kwargs):
        return base(**{**kwargs, "model": active})

    def tool_runner(**kwargs):
        return run_tool_agent_automatic(**{**kwargs, "model": tool_gate_model(reference)})

    row = executor(
        item=protocol["project"],
        arm="tool" if slot["method"] == METHODS[2] else "plan",
        protocol=protocol,
        root=folder,
        model=active,
        reference=reference,
        meter_factory=ReferencedQualificationMeter,
        planner=planner,
        tool_runner=tool_runner,
        command_timeout_seconds=1200,
        replay_timeout_seconds=1200,
    )
    return {**row, **slot}


def validate(spec):
    if spec["identity"] != IDENTITY or spec["schedule"] != schedule() or spec["provider_calls"] != 0 or spec["credentials_read"] is not False or spec["max_model_cost_usd"] != 0:
        raise PlanContractError("固定身份、顺序或零Provider边界变化")
    parent = Path(spec["reference_evidence"]["root"])
    if audit(parent)["inventory_canonical_sha256"] != spec["reference_evidence"]["inventory_sha256"] or not json.loads((parent / "result.json").read_text())["qualified"]:
        raise PlanContractError("参考资格未闭合或发生变化")
    original = json.loads((parent / "protocol.json").read_text())
    task, reference = make_project(original["plan"])
    if task != spec["project"]["task"] or reference != spec["reference"] or original["file_boundary"] != spec["project"]["file_boundary"]:
        raise PlanContractError("固定完整测试、共享装配、来源或文件边界变化")
    if digest(Path(spec["project"]["source_archive"])) != task["source_archive_sha256"]:
        raise PlanContractError("源码归档变化")
    receipt = ROOT / spec["exposure_record"]
    exposure = json.loads(receipt.read_text())
    if exposure["holdout"] is not False or exposure["family_group"] != ["rtorrent", "rakshasa-libtorrent"] or exposure["provider_outcomes_observed_before_freeze"] is not False:
        raise PlanContractError("项目族/暴露登记不符合资格范围")
    for name, expected in spec["components"].items():
        p = (ROOT / name).resolve()
        if not p.is_relative_to(ROOT) or digest(p) != expected:
            raise PlanContractError("冻结组件变化:" + name)


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
        print(json.dumps(dict(valid=True, slots=5, provider_calls=0)))
        return 0
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", spec)
    write_json(root / "execution.json", {"release": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "provider_calls": 0})
    rows, reason = [], None
    try:
        for i, slot in enumerate(spec["schedule"]):
            try:
                before_deadline(spec["deadline_utc"], spec["reserve_seconds"])
            except PlanContractError:
                reason = "deadline_reservation"
                break
            folder = root / f"slot-{i + 1}"
            folder.mkdir()
            row = run_slot(spec, folder, slot)
            rows.append(row)
            print(json.dumps({"slot": i + 1, "method": slot["method"], "case": slot["case"], "strict": row["strict_completed"], "error": row.get("error_message")}, ensure_ascii=False), flush=True)
            if not row["strict_completed"] or not row["cleanup"]["succeeded"] or row["agent_usage"]["recorded_tokens"] or row["agent_usage"]["unknown_usage_requests"]:
                reason = "qualification_failed"
                break
    except BaseException as exc:
        reason = type(exc).__name__
        raise
    finally:
        write_json(root / "result.json", dict(identity=IDENTITY, kind="zero_provider_engineering_qualification", provider_calls=0, credentials_read=False, rows=rows, unobserved_schedule=spec["schedule"][len(rows) :], stop_reason=reason))
        print(json.dumps(seal(root, spec, ROOT)), flush=True)
    return 0 if len(rows) == 5 and all(r["strict_completed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
