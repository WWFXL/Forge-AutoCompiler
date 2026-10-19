"""确保强基线只自动记账，不绕过原严格验收。"""

import json
from types import SimpleNamespace

from langchain_core.tools import tool

from deerflow.compile.plan_agent_canary import TOOL_PROMPT, ToolBuildService
from deerflow.compile.plan_agent_provenance import AUTOMATIC_PROMPT, automatic_submission_arguments, automatic_tools


def record(identifier, role, *, code=0, timeout=False):
    return SimpleNamespace(command_id=identifier, role=role, exit_code=code, timed_out=timeout)


def test_selects_latest_successful_build_and_ordered_stages_excluding_diagnostics_and_tests():
    session = SimpleNamespace(
        commands=[
            record("clone", "clone"),
            record("dep", "dependency"),
            record("old-build", "build"),
            record("failed", "configure", code=1),
            record("diag", "diagnostic"),
            record("cfg", "configure"),
            record("new-build", "build"),
            record("timeout", "build", timeout=True),
            record("tests", "smoke"),
            record("stage", "artifact_stage"),
        ]
    )
    assert automatic_submission_arguments(session) == {"supporting_command_id": "new-build", "recipe_command_ids": ["dep", "old-build", "cfg", "new-build", "stage"]}


def test_no_successful_build_cannot_invent_supporting_evidence():
    for rows in ([], [record("bad", "build", code=1)], [record("tests", "smoke")], [record("timeout", "build", timeout=True)]):
        assert automatic_submission_arguments(SimpleNamespace(commands=rows)) is None


def test_wrapper_delegates_unchanged_verifier_result_and_reads_current_session():
    delegated, events = [], []

    @tool
    def run_fixed_tests() -> str:
        """测试夹具。"""
        return "fixed-tests"

    @tool
    def submit_verified_build(supporting_command_id: str, recipe_command_ids: list[str]) -> str:
        """模拟原严格服务的拒绝，不允许wrapper改写为接受。"""
        delegated.append((supporting_command_id, recipe_command_ids))
        return json.dumps({"accepted": False, "reason": "固定完整测试尚未通过"}, ensure_ascii=False)

    session = SimpleNamespace(commands=[])
    service = SimpleNamespace(tools=lambda: [run_fixed_tests, submit_verified_build], current=lambda: session, meter=SimpleNamespace(ledger=SimpleNamespace(append=lambda *args, **kwargs: events.append((args, kwargs)))))
    wrapped = automatic_tools(service)
    assert wrapped[0] is run_fixed_tests
    assert not wrapped[1].args_schema.model_json_schema()["properties"]
    assert json.loads(wrapped[1].invoke({}))["accepted"] is False
    assert not delegated and not events
    session.commands = [record("build", "build"), record("smoke", "smoke"), record("stage", "artifact_stage")]
    response = json.loads(wrapped[1].invoke({}))
    assert response == {"accepted": False, "reason": "固定完整测试尚未通过"}
    assert delegated == [("build", ["build", "stage"])]
    assert events == [(("submission.provenance_selected",), {"observed_command_count": 3, "supporting_command_id": "build", "recipe_command_ids": ["build", "stage"]})]


def test_prompt_only_changes_submission_interface():
    old = "submit_verified_build提交成功构建ID及最小有序成功recipe，不能包含失败、diagnostic或smoke。"
    prefix, suffix = TOOL_PROMPT.split(old)
    assert AUTOMATIC_PROMPT.startswith(prefix) and AUTOMATIC_PROMPT.endswith(suffix)
    assert "无需参数" in AUTOMATIC_PROMPT


def test_real_service_still_rejects_missing_fixed_tests_and_wrong_artifact_set(tmp_path, monkeypatch):
    """通过真实服务的提交入口核对两项前置门禁，不能只验证假服务委托。"""
    from deerflow.compile import operations

    def unexpected_submit(**kwargs):
        raise AssertionError("前置门禁拒绝时不应进入replay")

    monkeypatch.setattr(operations, "submit_build_result_impl", unexpected_submit)
    session = SimpleNamespace(commands=[record("build", "build")], session_id="session", thread_id="thread", metadata_path=str(tmp_path / "session.json"))
    meter = SimpleNamespace(
        started_monotonic=0,
        tracker=SimpleNamespace(observe_elapsed=lambda value: None, remaining=lambda: SimpleNamespace(node_seconds=100)),
        ledger=SimpleNamespace(append=lambda *args, **kwargs: None),
    )
    service = ToolBuildService(
        task=SimpleNamespace(verification_steps=[SimpleNamespace(step_id="full-tests")], artifact_paths=["binary"]),
        session=session,
        manager=SimpleNamespace(load_session=lambda *args: session),
        source_root=tmp_path,
        frozen={},
        meter=meter,
    )
    submit = next(item for item in automatic_tools(service) if item.name == "submit_verified_build")
    assert json.loads(submit.invoke({})) == {"accepted": False, "reason": "固定完整测试尚未通过"}
    service.verifications["full-tests"] = "tests"
    assert json.loads(submit.invoke({})) == {"accepted": False, "reason": "精确交付集合不匹配"}
    assert not service.verified
