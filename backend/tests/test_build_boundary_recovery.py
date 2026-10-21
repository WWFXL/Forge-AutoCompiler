"""恢复身份投影回归：修复可读身份与权威包装身份分离后的计量拒绝。"""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_boundary_arm_v2 import public_workflow_state  # noqa: E402
from forge_build_boundary_gate_v2 import validate  # noqa: E402

from deerflow.compile.generated_file_boundary import FileBoundary, guard_plan  # noqa: E402
from deerflow.compile.plan_handoff_context import project_handoff_packet  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanContractError  # noqa: E402
from deerflow.compile.source_preparation import paths_fingerprint, with_preparation  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def fixtures():
    protocol = json.loads((ROOT / "benchmarks/manifests/cpp-build-generated-file-boundary-gate-v1.json").read_text())
    boundary = FileBoundary.model_validate(protocol["project"]["file_boundary"])
    public = BuildPlan.model_validate(protocol["reference"])
    guarded = guard_plan(boundary, with_preparation(public, paths_fingerprint(boundary.baseline)))
    return boundary, public, guarded


def test_recovery_packet_binds_both_fingerprints_without_mutating_authority():
    boundary, public, guarded = fixtures()
    state = {"plan_sha256": guarded.fingerprint(), "handoff": {"plan_sha256": guarded.fingerprint(), "handoff_id": "h", "step_id": "build"}}
    before = copy.deepcopy(state)
    projected, current = public_workflow_state(boundary, guarded, state)
    active = {**state["handoff"], "guarded_plan_sha256": guarded.fingerprint(), "plan_sha256": current.fingerprint()}
    packet = project_handoff_packet({"state": projected, "handoff": active})
    assert current == public
    assert packet["state"]["plan_sha256"] == public.fingerprint()
    assert packet["state"]["handoff"]["guarded_plan_sha256"] == guarded.fingerprint()
    assert state == before


@pytest.mark.parametrize("field", ["state", "handoff"])
def test_bad_authoritative_identity_is_rejected(field):
    boundary, _, guarded = fixtures()
    state = {"plan_sha256": guarded.fingerprint(), "handoff": {"plan_sha256": guarded.fingerprint()}}
    (state if field == "state" else state["handoff"])["plan_sha256"] = "bad"
    with pytest.raises(PlanContractError, match="身份不一致"):
        public_workflow_state(boundary, guarded, state)


def test_reference_cannot_change_task_identity():
    protocol = json.loads((ROOT / "benchmarks/manifests/cpp-build-generated-file-boundary-gate-v1.json").read_text())
    protocol["identity"] = "cpp-build-generated-file-boundary-gate-v2"
    protocol["reference"]["commit_sha"] = "b" * 40
    with pytest.raises(PlanContractError, match="固定任务不一致"):
        validate(protocol)


def test_review_receipt_is_checked_before_formal_attempt(tmp_path):
    protocol = json.loads((ROOT / "benchmarks/manifests/cpp-build-generated-file-boundary-gate-v1.json").read_text())
    protocol["identity"] = "cpp-build-generated-file-boundary-gate-v2"
    receipt = tmp_path / "review.json"
    receipt.write_text("{}")
    protocol["source_review"]["path"] = str(receipt)
    protocol["source_review"]["sha256"] = "0" * 64
    with pytest.raises(PlanContractError, match="审阅收据变化"):
        validate(protocol)
