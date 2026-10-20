"""共同源码索引、既有权威前缀及任务功能检查的真实本地回归。"""

import shlex
import subprocess
from types import SimpleNamespace

import pytest
from test_plan_workflow import make_plan

from deerflow.compile.build_task_checks import cmake_configuration_command, ctest_execution_command
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.source_preparation import PREPARATION_ID, PreparedWorkflow, index_check_command, paths_fingerprint, preparation_step, with_preparation


def shell(command, cwd):
    return subprocess.run(["bash", "-euo", "pipefail", "-c", command], cwd=cwd, capture_output=True, text=True)


def test_index_requires_exact_original_paths_and_no_fake_commit(tmp_path):
    (tmp_path / "a.cc").write_text("int main(){}\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "--force", "--all"], check=True)
    expected = paths_fingerprint(["a.cc"])
    assert shell(index_check_command(expected), tmp_path).returncode == 0
    (tmp_path / "extra").write_text("新增索引项必须被拒绝")
    subprocess.run(["git", "-C", str(tmp_path), "add", "extra"], check=True)
    assert shell(index_check_command(expected), tmp_path).returncode != 0
    subprocess.run(["git", "-C", str(tmp_path), "rm", "--cached", "extra"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=gate", "-c", "user.email=gate@example.invalid", "commit", "-qm", "夹具伪commit拒绝检查"], check=True)
    assert shell(index_check_command(expected), tmp_path).returncode != 0


def test_preparation_is_reserved_and_source_root_is_exact():
    expected = "1" * 64
    plan = with_preparation(make_plan(), expected)
    assert plan.steps[0] == preparation_step(expected)
    assert "safe.directory','/workspace/repo'" in shlex.split(plan.steps[0].command)[2]
    assert "safe.directory','*'" not in shlex.split(plan.steps[0].command)[2]
    with pytest.raises(PlanContractError, match="覆盖"):
        with_preparation(plan, expected)


def test_prepared_workflow_binds_existing_success_without_reexecuting(monkeypatch):
    plan = with_preparation(make_plan(), "1" * 64)
    step = plan.steps[0]
    record = SimpleNamespace(command_id="prepared", command=step.command, role=step.role, workdir=step.workdir, exit_code=0, timed_out=False)

    def initialize(self, **kwargs):
        self.plan = kwargs["plan"]
        self._session = SimpleNamespace(commands=[record])
        self.completed = {}
        self.commands_used = 0

    monkeypatch.setattr("deerflow.compile.source_preparation.CanaryWorkflow.__init__", initialize)
    monkeypatch.setattr(PreparedWorkflow, "_persist", lambda self: None)
    workflow = PreparedWorkflow(plan=plan, preparation_command_id="prepared")
    assert workflow.completed == {PREPARATION_ID: "prepared"}
    assert workflow.commands_used == 1
    record.exit_code = 1
    with pytest.raises(PlanContractError, match="记录与方案不符"):
        PreparedWorkflow(plan=plan, preparation_command_id="prepared")


@pytest.mark.parametrize("kind,value", [("BOOL", "OFF"), ("UNINITIALIZED", "OFF"), ("STRING", "FALSE"), ("STRING", "0")])
def test_cmake_accepts_equivalent_false_cache_values(tmp_path, kind, value):
    (tmp_path / "build").mkdir()
    (tmp_path / "build/CMakeCache.txt").write_text(f"BUILD_SHARED_LIBS:{kind}={value}\nTESTS:BOOL=ON\n")
    assert shell(cmake_configuration_command({"TESTS": True}), tmp_path).returncode == 0


@pytest.mark.parametrize("cache", ["TESTS:BOOL=OFF\n", "TESTS:BOOL=ON\nBUILD_SHARED_LIBS:BOOL=ON\n", ""])
def test_cmake_rejects_disabled_tests_shared_or_missing_requirement(tmp_path, cache):
    (tmp_path / "build").mkdir()
    (tmp_path / "build/CMakeCache.txt").write_text(cache)
    assert shell(cmake_configuration_command({"TESTS": True}), tmp_path).returncode != 0


@pytest.mark.parametrize("case,passed", [('<testcase name="a" status="run"/>', True), ('<testcase name="a"><skipped/></testcase>', False), ('<testcase name="a"><failure/></testcase>', False), ("", False)])
def test_ctest_summary_cannot_hide_skip_failure_or_empty_suite(tmp_path, case, passed):
    xml = tmp_path / "ctest.xml"
    xml.write_text("<testsuite>" + case + "</testsuite>")
    tokens = shlex.split(ctest_execution_command(1))
    script = tokens[2].replace("/workspace/forge-ctest.xml", str(xml))
    result = subprocess.run(["python3", "-c", script], capture_output=True, text=True)
    assert (result.returncode == 0) is passed
