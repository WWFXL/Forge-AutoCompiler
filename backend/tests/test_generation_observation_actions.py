"""真实Linux写入监测复现：旧拼接拒绝、新拆分通过、缺失观察仍拒绝。"""

import hashlib

import pytest

from deerflow.compile.generated_file_boundary import FileBoundary, guard_main
from deerflow.compile.generation_observation_actions import compile_generation_actions
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildAction, ObservedBuildActions, compile_action


def test_exact_generation_keeps_permission_and_all_path_checks(tmp_path):
    source = tmp_path / "input.txt"
    author_test = tmp_path / "author-test.txt"
    source.write_text("author input\n")
    author_test.write_text("author test\n")
    canonical = "printf 'generated\\n' > generated.txt && printf 'generator-ready\\n'"
    baseline = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, author_test)}
    boundary = FileBoundary(
        baseline=baseline,
        protected_inputs=("input.txt", "author-test.txt"),
        generations=(dict(command=canonical, inputs=("input.txt",), outputs={"generated.txt": hashlib.sha256(b"generated\n").hexdigest()}, evidence="最小回归的预声明生成关系"),),
    )
    # guard_main自身支持临时根；只在夹具中映射逻辑工作目录，不改变受测命令或监测器。
    physical = boundary.model_dump(mode="json")
    physical["generations"][0]["workdir"] = str(tmp_path)
    action = ObservedBuildAction(step_id="bootstrap", role="dependency", command=canonical, source="input.txt", expected="生成并观察", stdout_contains=("generator-ready",), files_exist=("generated.txt",))
    with pytest.raises(ValueError, match="生成文件被非声明命令写入"):
        guard_main(physical, compile_action(action).command, str(tmp_path), root_path=str(tmp_path))

    def actions(value):
        proposal = ObservedBuildActions(reason="组合回归", steps=[value, dict(step_id="build", role="build", command="true", source="input.txt", expected="占位", requires=["bootstrap"])])
        return compile_generation_actions(proposal, boundary).steps

    steps = actions(action)
    assert len(steps) == 3 and steps[0].command == canonical
    assert steps[0].required_output == ("generator-ready",)
    assert steps[1].step_id == "bootstrap" and steps[1].requires == (steps[0].step_id,)
    assert steps[2].requires == ("bootstrap",) and steps[2].step_id == "build"
    assert guard_main(physical, steps[0].command, str(tmp_path), root_path=str(tmp_path)) == 0
    assert guard_main(physical, steps[1].command, str(tmp_path), root_path=str(tmp_path)) == 0
    missing = actions(action.model_copy(update={"files_exist": ("generated.txt", "missing.txt")}))
    assert guard_main(physical, missing[0].command, str(tmp_path), root_path=str(tmp_path)) == 0
    assert guard_main(physical, missing[1].command, str(tmp_path), root_path=str(tmp_path)) == 86
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, author_test)} == baseline
