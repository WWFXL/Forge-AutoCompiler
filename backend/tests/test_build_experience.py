"""验证隔离、真实命令绑定和上下文边界，不模拟模型效果。"""

import pytest

from deerflow.compile.build_experience import ExperienceBank, query_state, validate_extraction


def source(name="seed", system="cmake"):
    return dict(
        source_id=name,
        family=name,
        build_system=system,
        retrieval_text="configure dependency BUILD_TESTING",
        commands=[dict(command_id="c1", role="configure", exit_code=0)],
        observed_validation=dict(full=False, tests="unobserved"),
        raw_context={"command": "cmake -DBUILD_TESTING=ON"},
    )


def entry():
    return dict(
        conditions=["项目声明测试开关"], stage="configure", state="测试目标未启用", action="读取作者声明，启用真实测试选项", outcome="effective", not_applicable=["无此开关"], command_ids=["c1"], verification_scope="仅配置成功，测试未观察"
    )


def test_evidence_binding_and_unobserved_retained():
    row = source()
    result = validate_extraction(dict(experiences=[entry()]), row)
    assert result[0]["observed_validation"]["tests"] == "unobserved"
    bad = entry() | dict(command_ids=["invented"])
    with pytest.raises(ValueError, match="不存在"):
        validate_extraction(dict(experiences=[bad]), row)


def test_same_family_and_other_system_excluded():
    sources = [source(), source("other"), source("make", "make")]
    bank = ExperienceBank(sources, [validate_extraction(dict(experiences=[entry()]), s)[0] for s in sources])
    for mode in ("raw", "structured"):
        result = bank.retrieve(build_system="cmake", family="seed", stage="configure", text="BUILD_TESTING", mode=mode)
        assert result["sources"] == ["other"]
    assert bank.retrieve(build_system="cmake", family="seed", stage="initial", text="", mode="none")["items"] == []


def test_payload_never_partially_truncates_commands():
    bank = ExperienceBank([source()], [])
    result = bank.retrieve(build_system="cmake", family="evaluation", stage="initial", text="", mode="raw", limit_bytes=10)
    assert result["items"] == []
    assert result["bytes"] == 0


def test_failed_commands_cannot_be_labeled_effective():
    row = source()
    row["commands"][0]["exit_code"] = 1
    with pytest.raises(ValueError, match="实际成功"):
        validate_extraction(dict(experiences=[entry()]), row)


def test_query_observes_only_current_handoff():
    from types import SimpleNamespace

    task = SimpleNamespace(build_system="cmake", model_dump=lambda **kw: {"build_system": "cmake"})
    initial = query_state(task, {"handoff": None})
    assert initial["stage"] == "initial"
    current = query_state(task, {"handoff": {"step_id": "cfg", "reason": "missing dependency"}, "current_plan": {"steps": [{"step_id": "cfg", "role": "configure"}]}})
    assert current["stage"] == "configure"
    assert "missing dependency" in current["text"]
