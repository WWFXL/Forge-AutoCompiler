#!/usr/bin/env python3
"""共同初始与恢复材料编码后的独立三槽资格，不续跑v1。"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]
import forge_build_rtorrent_common_gate as previous  # noqa: E402
from forge_build_rtorrent_common_v2 import CommonQualificationMeterV2  # noqa: E402
from forge_typed_evidence import audit  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

IDENTITY = "cpp-build-rtorrent-common-entry-gate-v2"
OLD_VALIDATE = previous.validate


def validate(spec):
    if spec["identity"] != IDENTITY:
        raise PlanContractError("新共同编码资格身份不符")
    bound = spec["failed_common_gate"]
    root = Path(bound["root"])
    if audit(root)["inventory_canonical_sha256"] != bound["inventory_sha256"]:
        raise PlanContractError("v1失败证据变化")
    result = json.loads((root / "result.json").read_text())
    if len(result["rows"]) != 2 or result["rows"][0]["strict_completed"] is not True or result["rows"][1].get("error_message") != "当前状态材料超过50000字节，不调用Provider" or len(result["unobserved_schedule"]) != 1:
        raise PlanContractError("v1失败及未观察分母不符")
    base = copy.deepcopy(spec)
    base["identity"] = "cpp-build-rtorrent-common-entry-gate-v1"
    with patch.object(previous, "IDENTITY", base["identity"]):
        OLD_VALIDATE(base)


def main():
    with patch.object(previous, "IDENTITY", IDENTITY), patch.object(previous, "validate", validate), patch.object(previous, "CommonQualificationMeter", CommonQualificationMeterV2):
        return previous.main()


if __name__ == "__main__":
    raise SystemExit(main())
