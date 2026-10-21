"""输出清理范围、固定SHA和完整原测试的约束。"""

import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_reset_gate as reset  # noqa: E402
from forge_build_rtorrent_recovery_gate import make_project  # noqa: E402

from deerflow.compile.staged_verification import StagedVerificationTask  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions, assemble_observed  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    original = json.loads((ROOT / "benchmarks/manifests/cpp-build-rtorrent-reference-v5.json").read_text())
    task, reference = make_project(original["plan"])
    return original, StagedVerificationTask.model_validate(task), reference, reset.reset_boundary(original["file_boundary"])


def test_reset_can_delete_only_original_exact_generated_outputs():
    original, _, _, boundary = fixture()
    command = boundary.generations[-1].command
    tokens = shlex.split(command.splitlines()[0])
    assert tokens[:3] == ["rm", "-f", "--"]
    outputs = {p: h for r in original["file_boundary"]["generations"] for p, h in r["outputs"].items()}
    assert len(tokens[3:]) == 40 and set(tokens[3:]) == set(outputs)
    assert not set(tokens[3:]) & set(boundary.protected_inputs)
    assert boundary.generations[-1].outputs == outputs
    assert command.splitlines()[1:] == ["(cd vendor-libtorrent && autoreconf -ivf)", "autoreconf -ivf"]
    assert boundary.baseline == original["file_boundary"]["baseline"]


def test_recovery_retains_complete_tests_and_build_recipe_after_reset():
    _, task, reference, boundary = fixture()
    actions = ObservedBuildActions.model_validate(reset.reset_recovery(reference, boundary))
    plan = assemble_observed(task, actions, revision=2)
    assert [s.step_id for s in plan.steps[:3]] == ["cleanup-template", "bootstrap-reset", "configure-libtorrent"]
    assert plan.steps[2].requires == ("bootstrap-reset",)
    assert tuple(s for s in plan.steps if s.role == "smoke") == task.verification_steps
    assert plan.artifact_paths == ("rtorrent", "libtorrent.so.53")
