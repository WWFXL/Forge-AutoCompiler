#!/usr/bin/env python3
"""独立三槽共同入口/实际请求材料资格；全程零 Provider、无付费分支。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]
from forge_build_plan_predicate_gate import fake_model, reference_actions  # noqa: E402
from forge_build_rtorrent_common import CommonQualificationMeter, run_strategy  # noqa: E402
from forge_build_rtorrent_gate import tool_gate_model  # noqa: E402
from forge_build_unified_plan import METHODS  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

IDENTITY = "cpp-build-rtorrent-common-entry-gate-v1"


def schedule():
    return [dict(project="rtorrent", method=method, case="actual_template_recovery" if method == METHODS[0] else "normal", repetition=1) for method in METHODS]


def validate(spec):
    if (spec["identity"], spec["schedule"], spec["provider_calls"], spec["credentials_read"], spec["max_model_cost_usd"]) != (IDENTITY, schedule(), 0, False, 0):
        raise PlanContractError("共同资格身份/顺序/零费用边界变化")
    if (spec["started_window_utc"], spec["deadline_utc"], spec["reserve_seconds"], spec["cleanup_timeout_seconds"]) != ("2026-10-21T13:40:00+00:00", "2026-10-21T16:40:00+00:00", 2700, 120):
        raise PlanContractError("共同资格时窗/停止预留变化")
    parent = Path(spec["template_evidence"]["root"])
    if audit(parent)["inventory_canonical_sha256"] != spec["template_evidence"]["inventory_sha256"]:
        raise PlanContractError("完整实际模板资格证据变化")
    result = json.loads((parent / "result.json").read_text())
    if len(result["rows"]) != 1 or not result["rows"][0]["strict_completed"] or result["unobserved_schedule"]:
        raise PlanContractError("实际模板恢复尚未严格闭合")
    original = json.loads((parent / "protocol.json").read_text())
    for key in ("project", "reference", "recovery_actions", "exposure_record", "original_test_programs", "original_test_counts", "package_manifest_sha256"):
        if spec[key] != original[key]:
            raise PlanContractError("共同任务/完整原测试/材料/生成规则变化：" + key)
    if digest(Path(spec["project"]["source_archive"])) != spec["project"]["task"]["source_archive_sha256"]:
        raise PlanContractError("源归档变化")
    for name, expected in spec["components"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != expected:
            raise PlanContractError("冻结组件变化：" + name)


def run_slot(spec, folder, slot):
    if slot["method"] == METHODS[2]:
        model = tool_gate_model(spec["reference"])
    else:
        actions = spec["recovery_actions"] if slot["method"] == METHODS[0] else reference_actions(spec["reference"]).model_dump(mode="json")
        model = fake_model([actions])
    started = time.monotonic()
    row = run_strategy(method=slot["method"], item=spec["project"], protocol=spec, root=folder, model=model, meter_factory=CommonQualificationMeter, qualification_reference=spec["reference"])
    return {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}


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
        print(json.dumps(dict(valid=True, slots=3, provider_calls=0)))
        return 0
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", spec)
    write_json(root / "execution.json", dict(release=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), provider_calls=0))
    rows, reason = [], "initialization_not_completed"
    try:
        for i, slot in enumerate(spec["schedule"], 1):
            before_deadline(spec["deadline_utc"], spec["reserve_seconds"])
            folder = root / f"slot-{i}"
            folder.mkdir()
            row = run_slot(spec, folder, slot)
            rows.append(row)
            write_json(root / f"progress-{i}.json", row)
            print(json.dumps(dict(slot=i, method=slot["method"], strict=row["strict_completed"], error=row.get("error_message")), ensure_ascii=False), flush=True)
            if not row["strict_completed"] or not row["cleanup"]["succeeded"] or row["agent_usage"]["recorded_tokens"] or row["agent_usage"]["unknown_usage_requests"]:
                reason = "qualification_failed"
                break
        else:
            reason = None
    except BaseException as exc:
        reason = type(exc).__name__
        raise
    finally:
        write_json(root / "result.json", dict(identity=IDENTITY, kind="zero_provider_common_entry_qualification", provider_calls=0, credentials_read=False, rows=rows, unobserved_schedule=spec["schedule"][len(rows) :], stop_reason=reason))
        print(json.dumps(seal(root, spec, ROOT)), flush=True)
    return 0 if len(rows) == 3 and all(r["strict_completed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
