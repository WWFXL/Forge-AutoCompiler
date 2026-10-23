#!/usr/bin/env python3
"""Provider停止后独立采集零模型首次失败即停基线，不冒充配对消融。"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import forge_build_recovery_ablation as ablation
from forge_typed_evidence import seal, write_json

base = ablation.base
IDENTITY = "cpp-build-tool-no-recovery-observation-v1"


def schedule():
    return [dict(project=name, method="no_recovery", repetition=1) for name in ablation.PROJECTS]


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0 or protocol["credentials_read"] is not False:
        raise base.PlanContractError("独立零模型基线身份或费用边界变化")
    if protocol["schedule"] != schedule() or protocol["stage_max_cost_usd"] != "0.00":
        raise base.PlanContractError("固定五项或零预算变化")
    ablation.validate({**protocol, "identity": ablation.IDENTITY, "schedule": ablation.schedule(), "stage_max_cost_usd": "5.00"})
    base.OperationWindow(protocol["deadline_utc"]).admit("new_slot", 3900)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = base.load(args.protocol)
    validate(protocol)
    if args.validate_only:
        print(json.dumps(dict(valid=True, provider_calls=0, credentials_read=False)))
        return 0
    subprocess.run(["bash", str(base.ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    write_json(root / "execution.json", dict(release=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()))
    rows, reason, complete = [], "initialization_not_completed", False
    try:
        reason = None
        for i, slot in enumerate(protocol["schedule"], 1):
            try:
                base.OperationWindow(protocol["deadline_utc"]).admit("new_slot", 3900)
            except base.PlanContractError:
                reason = "new_slot_time_reservation"
                break
            folder = root / f"slot-{i}"
            folder.mkdir()
            # 传入None；两处Agent入口均被消融策略在调用Provider前拒绝。
            row = ablation.run_slot(protocol=protocol, slot=slot, root=folder, model=None)
            rows.append(row)
            write_json(root / f"progress-{i}.json", row)
            if row["agent_usage"]["model_requests"] or row["agent_usage"]["unknown_usage_requests"]:
                raise base.PlanContractError("零模型实验触发了不应存在的模型路径")
            print(json.dumps(dict(slot=i, project=slot["project"], strict=row["strict_completed"], provider_calls=0, status=row.get("status"), error=row.get("error_message")), ensure_ascii=False), flush=True)
            if not row["cleanup"]["succeeded"]:
                reason = "cleanup_failure"
                break
        complete = True
    finally:
        write_json(root / "result.json", dict(identity=IDENTITY, kind=protocol["kind"], rows=rows, unobserved_schedule=protocol["schedule"][len(rows):], stop_reason=reason, lifecycle_complete=complete, provider_calls=0, credentials_read=False, known_estimated_cost_usd="0", unknown_usage_reservation_usd="0"))
        print(json.dumps(seal(root, protocol, base.ROOT)), flush=True)
    return 0 if complete and len(rows) == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
