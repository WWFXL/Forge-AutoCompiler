#!/usr/bin/env python3
"""沿原generic宿主模式执行；停止信号在槽结算后停止整批。"""

from __future__ import annotations

import json
import os
import signal
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

import forge_build_test_preparation_comparison_v2 as previous

base = previous.previous
IDENTITY = "cpp-build-test-preparation-comparison-v3"
ORIGINAL_VALIDATE = previous.validate
STOP_REQUESTED = False


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["host_ownership_mode"] != "original_generic_unconfigured":
        raise base.PlanContractError("新身份或generic宿主模式不符")
    ORIGINAL_VALIDATE({**candidate, "identity": previous.IDENTITY})


@contextmanager
def execution_window(deadline):
    # generic资格原本未设置host identity；容器仍使用原root/网络。
    with previous.qualified_execution_window(deadline), patch.dict(os.environ, {"FORGE_HOST_UID": "", "FORGE_HOST_GID": ""}):
        yield


def execute(protocol, root, model, rows):
    for index, slot in enumerate(protocol["schedule"], 1):
        if STOP_REQUESTED:
            return "operator_or_deadline_stop"
        try:
            base.OperationWindow(protocol["deadline_utc"]).admit("new_slot", 3900)
        except base.PlanContractError:
            return "new_slot_time_reservation"
        if sum(base.charges(rows)) + Decimal("3.00") > Decimal(protocol["stage_max_cost_usd"]):
            return "stage_cost_reservation"
        folder = root / f"slot-{index}"
        folder.mkdir()
        row = base.run_slot(protocol=protocol, slot=slot, root=folder, model=model)
        rows.append(row)
        base.write_json(root / f"progress-{index}.json", row)
        print(json.dumps(dict(slot=index, project=slot["project"], method=slot["method"], strict=row["strict_completed"], error=row.get("error_message"), usage=row["agent_usage"]), ensure_ascii=False), flush=True)
        if not row["cleanup"]["succeeded"] or row["agent_usage"]["unknown_usage_requests"]:
            return "cleanup_or_unknown_usage"
        if STOP_REQUESTED:
            return "operator_or_deadline_stop"
        for path in folder.glob("*/.compile-sessions/*/*/session.json"):
            if (base.load(path).get("error") or "").startswith("Host session ownership normalization failed"):
                return "host_finalize_environment_error"
        if Decimal(str(row["agent_usage"]["estimated_cost_usd_completed_responses"])) > Decimal("3.00"):
            return "cost_contract_violation"
        if any(json.loads(line)["event"] == "model.identity_mismatch" for p in folder.glob("*/agent/events.jsonl") for line in p.read_text().splitlines()):
            return "provider_identity_mismatch"
        if row.get("error_class") not in (None, "PlanContractError", "ValueError", "AgentWorkflowBudgetExceeded", "ValidationError", "StructuredOutputValidationError", "GraphRecursionError"):
            return "unexpected_runtime_error"
    return None


def request_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    raise base.PlanContractError("operator_or_deadline_stop")


def main():
    signal.signal(signal.SIGINT, request_stop)
    with patch.object(base, "validate", validate), patch.object(base, "execution_window", execution_window), patch.object(base, "PreparationMeter", previous.QualifiedPreparationMeter), patch.object(base, "execute", execute):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
