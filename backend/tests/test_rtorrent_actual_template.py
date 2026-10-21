"""实际模板来源、恢复准入和原测试不可替代性回归。"""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_template_gate as gate  # noqa: E402
from forge_build_plan_agent_canary import PlanAgentLedger  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402
from deerflow.compile.staged_verification import StagedVerificationTask  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions, assemble_observed  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    original = json.loads((ROOT / "benchmarks/manifests/cpp-build-rtorrent-reference-v5.json").read_text())
    task, reference = gate.make_project(original["plan"])
    return StagedVerificationTask.model_validate(task), reference, gate.task_boundary(original["file_boundary"])


def test_actual_template_never_consumes_reference_or_script_initially(tmp_path, monkeypatch):
    task, _, boundary = fixture()
    (tmp_path / "configure.ac").write_text("AC_INIT([sample],[1])")
    meter = SimpleNamespace(ledger=PlanAgentLedger(tmp_path / "ledger"))
    monkeypatch.setattr(gate, "propose_observed", lambda **kw: pytest.fail("初始模板不调用脚本Agent"))
    plan, _ = gate.actual_planner(boundary)(task=task, source_root=tmp_path, meter=meter, model=None)
    assert [(s.step_id, s.command) for s in plan.steps[:3]] == [("bootstrap", "autoreconf -fi"), ("configure", "sh ./configure"), ("build", "make -j2")]
    assert tuple(s for s in plan.steps if s.role == "smoke") == task.verification_steps
    assert (tmp_path / "ledger/tool-receipt.json").exists()
    assert not (tmp_path / "ledger/tool-abstention.json").exists()
    assert not (tmp_path / "configure").exists()


def test_ambiguous_template_stops_without_using_reference(tmp_path, monkeypatch):
    task, _, boundary = fixture()
    (tmp_path / "configure.ac").write_text("AC_INIT([x],[1])")
    (tmp_path / "CMakeLists.txt").write_text("project(x)")
    meter = SimpleNamespace(ledger=PlanAgentLedger(tmp_path / "ledger"))
    monkeypatch.setattr(gate, "propose_observed", lambda **kw: pytest.fail("不允许初始脚本回退"))
    with pytest.raises(PlanContractError, match="实际模板未准入"):
        gate.actual_planner(boundary)(task=task, source_root=tmp_path, meter=meter, model=None)


def test_recovery_fixture_keeps_every_original_test_and_declares_cleanup():
    task, reference, boundary = fixture()
    value = gate.recovery_actions(reference)
    plan = assemble_observed(task, ObservedBuildActions.model_validate(value), revision=2)
    assert plan.steps[0].command == "rm -f -- config.log"
    assert plan.steps[1].requires == ("cleanup-template",)
    assert tuple(s for s in plan.steps if s.role == "smoke") == task.verification_steps
    assert len(boundary.baseline) == 818
    assert len({p for r in boundary.generations for p in r.outputs}) == 40
    assert len(boundary.generations) == 4
    original = json.loads((ROOT / "benchmarks/manifests/cpp-build-rtorrent-reference-v5.json").read_text())
    expected = copy.deepcopy(original["file_boundary"])
    assert boundary.baseline == expected["baseline"]
    assert boundary.protected_inputs == tuple(expected["protected_inputs"])
    assert set(boundary.new_files) - set(expected["new_files"]) == {"config.log"}


def test_no_second_script_recovery(tmp_path, monkeypatch):
    task, reference, boundary = fixture()
    current = assemble_observed(task, ObservedBuildActions.model_validate(gate.recovery_actions(reference)), revision=2)
    meter = SimpleNamespace(ledger=PlanAgentLedger(tmp_path / "ledger"))
    monkeypatch.setattr(gate, "propose_observed", lambda **kw: pytest.fail("不允许第二次脚本恢复"))
    with pytest.raises(PlanContractError, match="最多一次"):
        gate.actual_planner(boundary)(task=task, source_root=tmp_path, meter=meter, model=None, current_plan=current, handoff={"plan_sha256": current.fingerprint(), "handoff_id": "actual"})
