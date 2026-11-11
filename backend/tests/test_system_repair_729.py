"""E54共同修复：实际Shell输出、依赖作用域、PO正文保护及恢复上下文。"""

import json

import pytest
from langchain_core.messages import HumanMessage
from test_common_verification_recipe import executable_workflow
from test_plan_agent import response
from test_simple_build import runner, simple_actions  # noqa: F401

from deerflow.compile.plan_workflow import PlanContractError, PlanStep
from deerflow.compile.simple_build_runtime import po_metadata_signature, source_inventory, source_unchanged, validate_phase_command
from deerflow.compile.simple_build_task import ExecutableSmoke, SimpleBuildActions, assemble_simple_plan


def test_native_nonzero_is_checked_and_original_code_is_visible(runner):  # noqa: F811
    w = executable_workflow(runner, "--version", "sample-v1")
    # 编译一个正常版本分支返回1的主程序，而非伪造命令记录。
    source = w.root / "sample.c"
    # 工作流baseline不能改变；独立测试程序由编译器参数定义返回行为。
    import subprocess

    subprocess.run(["cc", "-x", "c", "-o", str(w.root / "sample"), "-"], input='#include <stdio.h>\nint main(){puts("sample-v1");return 1;}', text=True, check=True)
    assert source.is_file()
    smoke = w.reference.executable_smokes[0].model_copy(update={"accepted_exit_codes": (1,)})
    smoke = smoke.model_copy(update={"step": smoke.step.model_copy(update={"command": "printf 'CODES\\n'; " + smoke.step.command})})
    w.reference = w.reference.model_copy(update={"executable_smokes": (smoke,)})
    # 暂存与真实检查；submit/replay在独立Docker工程构建中覆盖。
    w._post_command(PlanStep(step_id="copy", role="artifact_stage", command="cp sample /artifacts/sample", source="fixture", expected="暂存"), 10)
    policy, passed = w._executable_verification(10, native_only=True)
    assert passed
    evidence = policy.commands_by_artifact["sample"]
    assert '"exit_code": 1' in evidence.output and "CODES" in evidence.output
    policy.validate()
    # 同一输出但非预期退出码不能通过。
    bad = smoke.model_copy(update={"accepted_exit_codes": (2,)})
    w.reference = w.reference.model_copy(update={"executable_smokes": (bad,)})
    assert w._executable_verification(10, native_only=True) == (None, False)
    assert w.verification_issue["recoverable"] is False


@pytest.mark.parametrize("codes", [(), (-1,), (124,), (137,)])
def test_reference_cannot_accept_timeout_or_signal(codes):
    with pytest.raises(ValueError):
        ExecutableSmoke(artifact_name="x", accepted_exit_codes=codes, step=dict(step_id="v", role="smoke", command="x", source="作者", expected="版本", required_output=["version"]))


def test_dependency_toolchain_is_ordered_and_scoped():
    base = dict(source="README", expected="真实执行")
    steps = [dict(step_id="mkdir", role="dependency", command="mkdir -p /workspace/dependencies/gettext", **base)]
    for name, cmd in [("dep-config", "./configure --prefix=/workspace/dependencies/prefix"), ("dep-build", "make -j2"), ("dep-install", "make install")]:
        steps.append(dict(step_id=name, role="dependency", command=cmd, workdir="/workspace/dependencies/gettext", requires=[steps[-1]["step_id"]], **base))
    steps.append(dict(step_id="build", role="build", command="make", requires=["dep-install"], **base))
    from test_simple_build import task

    plan = assemble_simple_plan(task(), SimpleBuildActions(reason="构建源码依赖", steps=steps))
    for step in plan.steps:
        validate_phase_command(step)
    with pytest.raises(ValueError):
        PlanStep(**{**steps[1], "role": "configure"})
    with pytest.raises(PlanContractError):
        validate_phase_command(PlanStep(**{**steps[1], "command": "./configure && make"}))
    with pytest.raises(ValueError):
        PlanStep(**{**steps[1], "workdir": "/workspace/dependencies/../repo"})


PO = b'msgid ""\nmsgstr ""\n"POT-Creation-Date: 2020-01-01 00:00+0000\\n"\n"Language: lv\\n"\n"X-Bugs: Report bugs\\n"\n\nmsgid "hello"\nmsgstr "sveiki"\n'


def test_po_metadata_can_change_but_translation_cannot(tmp_path):
    p = tmp_path / "po/lv.po"
    p.parent.mkdir()
    p.write_bytes(PO)
    baseline = source_inventory(tmp_path)
    signature = {"po/lv.po": po_metadata_signature(PO)}
    changed = PO.replace(b"2020-01-01", b"2026-11-11").replace(b'"X-Bugs: Report bugs\\n"\n', b"").replace(b'"Language: lv\\n"\n', b'"X-Bugs: Report bugs\\n"\n"Language: lv\\n"\n')
    p.write_bytes(changed)
    source_unchanged(tmp_path, baseline, po_headers=signature)
    p.write_bytes(changed.replace(b"sveiki", b"altered"))
    with pytest.raises(PlanContractError):
        source_unchanged(tmp_path, baseline, po_headers=signature)
    p.write_bytes(changed.replace(b"Report bugs", b"other"))
    with pytest.raises(PlanContractError):
        source_unchanged(tmp_path, baseline, po_headers=signature)


def test_large_single_compacted_evidence_can_progress(tmp_path):
    from types import SimpleNamespace

    from deerflow.compile.plan_agent import PlanAgentLedger
    from deerflow.compile.simple_build_agents import SimpleBuildMeter
    from deerflow.compile.simple_planning_context import PlanningContext

    meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=("test-model",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: {})
    context = PlanningContext(dict(task={"goal": "unchanged"}, handoff={"recent_commands": [dict(command="make", output_tail="linker -fPIC\\n" * 4000, exit_code=1, log_path="logs/build.log")]}, source_packet=[]))

    class Request:
        messages = [HumanMessage(content="task"), HumanMessage(content="压缩证据" * 30000)]
        system_message = None
        model_settings = {}
        tools = []
        response_format = None

        def override(self, **kwargs):
            return SimpleNamespace(**kwargs, response_format=None)

    captured = []

    def handler(r):
        captured.extend(r.messages)
        return SimpleNamespace(result=[response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])

    context.request(meter, Request(), handler)
    packet = json.loads(captured[0].content)
    assert packet["task"]["goal"] == "unchanged"
    assert packet["handoff"]["recent_commands"][-1]["command"] == "make"
    assert "-fPIC" in packet["handoff"]["recent_commands"][-1]["output_tail"]
    assert (tmp_path / "agent/context-request-1-evidence.json").exists()
    assert meter.summary()["model_requests"] == 1


def test_po_policy_is_shared_by_workflow_and_primary_observation(runner):  # noqa: F811
    from test_simple_build import actions, workflow

    _, _, _, root = runner
    p = root / "po/lv.po"
    p.parent.mkdir()
    p.write_bytes(PO)
    w = workflow(runner, actions())
    p.write_bytes(PO.replace(b"2020-01-01", b"2026-11-11"))
    assert w.run()["status"] == "primary_completed"
    assert w.source_protection()["generated_metadata_changes"][0]["path"] == "po/lv.po"


def test_matching_version_output_with_wrong_code_does_not_loop_to_agent(runner):  # noqa: F811
    w = executable_workflow(runner)
    w._post_command(PlanStep(step_id="copy", role="artifact_stage", command="cp sample /artifacts/sample", source="fixture", expected="暂存"), 10)
    smoke = w.reference.executable_smokes[0]
    w.reference = w.reference.model_copy(update={"executable_smokes": (smoke.model_copy(update={"step": smoke.step.model_copy(update={"command": "/artifacts/sample -V; exit 1"})}),)})
    assert w._executable_verification(10, native_only=True) == (None, False)
    assert w.verification_issue["kind"] == "verification_contract_mismatch"
    assert w.verification_issue["recoverable"] is False
    assert w.layers["primary_build_completed"] is True
