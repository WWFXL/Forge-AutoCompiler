#!/usr/bin/env python3
"""生成文件B共同入口的零Provider真实项目资格；不加载模型配置或凭据。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_boundary_arm_v2 import run_arm  # noqa: E402
from forge_build_cxx_cross_comparison import slot_runner as normal_slot  # noqa: E402
from forge_build_plan_predicate_gate import fake_model, reference_actions  # noqa: E402
from forge_build_referenced_meter import ReferencedQualificationMeter  # noqa: E402
from forge_build_unified_plan import METHODS  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.generated_file_boundary import FileBoundary  # noqa: E402
from deerflow.compile.plan_agent import PlanTask  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402
from deerflow.compile.task_selected_make_plan import selected_make_actions  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import observed_planner  # noqa: E402

IDENTITY = "cpp-build-generated-file-boundary-gate-v2"


def schedule():
    return [{"project": "libconfig", "method": m, "case": "normal", "repetition": 1} for m in METHODS] + [
        {
            "project": "libconfig",
            "method": m,
            "case": "controlled_recovery",
            "repetition": 1,
        }
        for m in METHODS[:2]
    ]


def make_project(reference, boundary):
    raw = copy.deepcopy(reference)
    raw["steps"] = [s for s in raw["steps"] if s["step_id"] != "forge-source-prepare"]
    raw["steps"][0]["command"] = boundary.generations[0].command
    task = {k: v for k, v in raw.items() if k not in ("steps", "revision")}
    task["verification_steps"] = [s for s in raw["steps"] if s["role"] == "smoke"]
    return task, raw


def run_slot(protocol, root, slot, *, executor=run_arm):
    item, reference = protocol["project"], protocol["reference"]
    if slot["case"] == "normal":
        return normal_slot(
            protocol=protocol,
            root=root,
            slot=slot,
            item=item,
            reference=reference,
            qualify=True,
            executor=executor,
        )
    good = reference_actions(reference).model_dump(mode="json")
    bad = copy.deepcopy(good)
    bad["steps"][-1]["command"] = "false"
    active = fake_model([bad, good])
    base = observed_planner(
        "tool" if slot["method"] == METHODS[0] else "model",
        generator=selected_make_actions,
    )

    def planner(**kwargs):
        return base(**{**kwargs, "model": active})

    row = executor(
        item=item,
        arm="plan",
        protocol=protocol,
        root=root,
        model=active,
        reference=reference,
        planner=planner,
        meter_factory=ReferencedQualificationMeter,
        command_timeout_seconds=600,
        replay_timeout_seconds=900,
    )
    return {**row, **slot}


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0 or protocol["credentials_read"] is not False or protocol["schedule"] != schedule():
        raise PlanContractError("资格身份/零模型边界/固定队列不符")
    boundary = FileBoundary.model_validate(protocol["project"]["file_boundary"])
    task = PlanTask.model_validate(protocol["project"]["task"])
    reference = BuildPlan.model_validate(protocol["reference"])
    if any(getattr(reference, key) != getattr(task, key) for key in type(task).model_fields if key != "verification_steps"):
        raise PlanContractError("参考方案与固定任务不一致")
    if tuple(s for s in reference.steps if s.role == "smoke") != task.verification_steps:
        raise PlanContractError("参考测试与固定任务不一致")
    review = protocol["source_review"]
    if digest(Path(review["path"])) != review["sha256"] or review["role"] != "seen_development_task_only":
        raise PlanContractError("生成关系审阅收据变化")
    if protocol["max_model_cost_usd"] != 0:
        raise PlanContractError("资格模型费用必须为零")
    if digest(Path(protocol["project"]["source_archive"])) != task.source_archive_sha256:
        raise PlanContractError("源码归档变化")
    if boundary.fingerprint() != protocol["file_boundary_sha256"]:
        raise PlanContractError("文件边界变化")
    for name, expected in protocol["components"].items():
        path = (REPO_ROOT / name).resolve()
        if not path.is_relative_to(REPO_ROOT) or digest(path) != expected:
            raise PlanContractError("运行组件变化:" + name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    before_deadline(protocol["deadline_utc"], 900)
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        check=True,
        timeout=30,
    )
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    rows, reason = [], None
    try:
        for index, slot in enumerate(protocol["schedule"]):
            before_deadline(protocol["deadline_utc"], 900)
            folder = root / f"slot-{index + 1}"
            folder.mkdir()
            row = run_slot(protocol, folder, slot)
            rows.append(row)
            print(
                json.dumps(
                    {
                        "slot": index + 1,
                        "method": slot["method"],
                        "case": slot["case"],
                        "strict": row["strict_completed"],
                        "status": row["status"],
                    }
                ),
                flush=True,
            )
            if not row["strict_completed"] or row["agent_usage"]["recorded_tokens"] != 0 or not row["cleanup"]["succeeded"]:
                reason = "qualification_failed"
                break
    except Exception as exc:
        reason = type(exc).__name__
        raise
    finally:
        write_json(
            root / "result.json",
            {
                "identity": IDENTITY,
                "kind": "zero_provider_engineering_qualification",
                "provider_calls": 0,
                "credentials_read": False,
                "rows": rows,
                "unobserved_schedule": protocol["schedule"][len(rows) :],
                "stop_reason": reason,
            },
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    audit(root)
    return 0 if len(rows) == 5 and all(r["strict_completed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
