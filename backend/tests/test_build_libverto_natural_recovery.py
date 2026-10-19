"""自然失败恢复必须先复现完整错误，且不改测试或交付义务。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_libverto_natural_recovery import NoProviderMeter, revise  # noqa: E402

from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402


def case():
    protocol = json.loads((Path(__file__).resolve().parents[2] / "benchmarks/analyses/cpp-build-libverto-natural-recovery-v1.json").read_text())
    plan = BuildPlan.model_validate(protocol["initial_plan"])
    handoff = {"plan_sha256": plan.fingerprint(), "reason": "step_failed_or_expectation_missing", "step_id": "check", "recent_commands": [{"command": "make check", "exit_code": 2, "timed_out": False}]}
    log = "# TOTAL: 6\n# PASS:  0\n# FAIL:  6\n" + "Assertion `(ctx = verto_default(MODULES[i], VERTO_EV_TYPE_NONE))' failed.\n" * 6
    return plan, handoff, log


def test_only_configure_command_and_revision_change():
    plan, h, log = case()
    revised = revise(plan, h, log, "BUILTIN_MODULE=''")
    before, after = plan.model_dump(), revised.model_dump()
    assert after["revision"] == 2
    after["revision"] = before["revision"]
    for original, changed in zip(before["steps"], after["steps"], strict=True):
        if original["step_id"] == "configure":
            assert changed["command"] == "./configure --enable-shared --enable-static"
            changed["command"], changed["source"] = original["command"], original["source"]
    assert before == after


@pytest.mark.parametrize("fault", ["stale", "timeout", "wrong_failure", "missing_assertions", "builtin"])
def test_missing_or_wrong_evidence_rejected(fault):
    plan, h, log = case()
    config = "BUILTIN_MODULE=''"
    if fault == "stale":
        h["plan_sha256"] = "old"
    elif fault == "timeout":
        h["recent_commands"][-1]["timed_out"] = True
    elif fault == "wrong_failure":
        h["step_id"] = "build"
    elif fault == "missing_assertions":
        log = "# TOTAL: 0"
    else:
        config = "BUILTIN_MODULE='glib'"
    with pytest.raises(PlanContractError):
        revise(plan, h, log, config)


def test_provider_request_forbidden_without_credentials():
    with pytest.raises(PlanContractError, match="禁止模型"):
        NoProviderMeter._before_request(None)
