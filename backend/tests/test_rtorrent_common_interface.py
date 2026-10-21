"""完整固定验证、共享装配、CLI身份与保守模板升级的接口回归。"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_gate as gate  # noqa: E402
from forge_build_plan_predicate_gate import reference_actions  # noqa: E402

from deerflow.compile.generated_file_boundary import FileBoundary, guarded_command  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.staged_verification import StagedVerificationTask, boundary_tool_actions, submit_fixed_delivery  # noqa: E402
from deerflow.compile.tool_plan import ToolPlanNeedsAgent  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import assemble_observed  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    spec = json.loads((ROOT / "benchmarks/manifests/cpp-build-rtorrent-reference-v5.json").read_text())
    raw, plan = gate.make_project(spec["plan"])
    return StagedVerificationTask.model_validate(raw), plan, FileBoundary.model_validate(spec["file_boundary"])


def test_shared_assembly_keeps_every_fixed_test_after_common_stage():
    task, reference, _ = fixture()
    plan = assemble_observed(task, reference_actions(reference), revision=1)
    assert plan.model_dump(mode="json") == reference
    assert [s.step_id for s in plan.steps[-3:]] == ["stage", "full-author-tests", "delivery-cli"]
    assert tuple(s for s in plan.steps if s.role == "smoke") == task.verification_steps
    assert plan.steps[-3].requires == ("build",)


def test_reference_changes_only_step_bindings_not_author_test_or_cli_commands():
    task, _, _ = fixture()
    original = json.loads((ROOT / "benchmarks/manifests/cpp-build-rtorrent-reference-v5.json").read_text())
    smokes = [s for s in original["plan"]["steps"] if s["role"] == "smoke"]
    assert [(s.command, s.required_output) for s in task.verification_steps] == [(s["command"], tuple(s["required_output"])) for s in smokes]
    assert sum(sum(counts.values()) for counts in original["original_test_counts"].values()) == 323


def test_undeclared_template_bootstrap_abstains_without_receiving_reference(tmp_path):
    task, _, boundary = fixture()
    (tmp_path / "configure.ac").write_text("AC_INIT([x],[1])")
    with pytest.raises(ToolPlanNeedsAgent, match="预声明生成关系"):
        boundary_tool_actions(task, tmp_path, boundary)
    assert list(tmp_path.iterdir()) == [tmp_path / "configure.ac"]


def test_strong_script_executes_full_fixed_tests_once():
    _, reference, _ = fixture()
    model = gate.tool_gate_model(reference)
    calls = model.responses[0].tool_calls
    assert sum(c["name"] == "run_fixed_tests" for c in calls) == 1
    assert calls[-1]["name"] == "submit_verified_build" and calls[-1]["args"] == {}
    assert sum(c["name"] == "run_build_command" and c["args"]["command_role"] == "artifact_stage" for c in calls) == 1


def submission_fixture(tmp_path):
    task, _, boundary = fixture()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for name in task.artifact_paths:
        (artifacts / name).write_bytes(b"placeholder: underlying strict verifier owns ELF/replay")
    records = []
    for i, step in enumerate(task.verification_steps):
        path = tmp_path / f"v{i}.log"
        path.write_text("\n".join(step.required_output))
        records.append(SimpleNamespace(command_id=f"v{i}", command=guarded_command(boundary, step.command, step.workdir), workdir=step.workdir, role="smoke", exit_code=0, timed_out=False, log_path=str(path)))
    session = SimpleNamespace(commands=records, metadata_path=str(tmp_path / "session.json"))
    return dict(task=task, boundary=boundary, session=session, supporting_command_id="build", recipe_command_ids=["build", "stage"], verification_command_ids=[r.command_id for r in records])


def test_shared_submission_retains_full_verify_but_binds_only_independent_cli(tmp_path, monkeypatch):
    args, seen = submission_fixture(tmp_path), {}
    from deerflow.compile import operations

    monkeypatch.setattr(operations, "submit_build_result_impl", lambda **kw: seen.update(kw) or "submitted")
    assert submit_fixed_delivery(**args) == "submitted"
    assert seen["verification_command_ids"] == ["v0", "v1"]
    policy = seen["executable_verification_policy"]
    assert set(policy.commands_by_artifact) == {"rtorrent"}
    assert policy.commands_by_artifact["rtorrent"].command_id == "v1"


@pytest.mark.parametrize("bad", ["missing", "duplicate", "failed", "timeout", "changed-command", "missing-marker", "extra-artifact"])
def test_invalid_test_or_delivery_evidence_never_reaches_underlying_submit(tmp_path, monkeypatch, bad):
    args = submission_fixture(tmp_path)
    if bad == "missing":
        args["verification_command_ids"] = ["v1"]
    elif bad == "duplicate":
        args["verification_command_ids"] = ["v1", "v1"]
    elif bad == "failed":
        args["session"].commands[0].exit_code = 1
    elif bad == "timeout":
        args["session"].commands[0].timed_out = True
    elif bad == "changed-command":
        args["session"].commands[0].command = guarded_command(args["boundary"], "true", "/workspace/repo")
    elif bad == "missing-marker":
        Path(args["session"].commands[0].log_path).write_text("no tests")
    else:
        (tmp_path / "artifacts/extra").write_text("extra")
    from deerflow.compile import operations

    monkeypatch.setattr(operations, "submit_build_result_impl", lambda **kw: pytest.fail("无效证据不能触发真实提交"))
    with pytest.raises(PlanContractError):
        submit_fixed_delivery(**args)


def test_recovery_keeps_task_and_changes_build_only():
    task, reference, _ = fixture()
    good = reference_actions(reference)
    value = good.model_dump(mode="json")
    value["steps"][-1]["command"] = "false"
    from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions

    bad = assemble_observed(task, ObservedBuildActions.model_validate(value), revision=1)
    revised = assemble_observed(task, good, revision=2)
    assert bad.steps[:-4] == revised.steps[:-4]
    assert bad.steps[-4].command == "false"
    assert revised.steps[-3:] == bad.steps[-3:]
    assert [r["method"] for r in gate.schedule()[:3]] == list(gate.METHODS)
    assert [r["method"] for r in gate.schedule()[3:]] == list(gate.METHODS[:2])
