from types import SimpleNamespace

from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.types import Command

from deerflow.agents.middlewares import clarification_middleware as module


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        tool_call={
            "name": "ask_clarification",
            "id": "call-clarify-1",
            "args": {
                "question": "Which build option should I use?",
                "clarification_type": "approach_choice",
            },
        }
    )


def test_interactive_clarification_still_ends_the_turn(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "claim_experiment_clarification_auto_answer",
        lambda request: None,
    )

    result = module.ClarificationMiddleware()._handle_clarification(_request())

    assert isinstance(result, Command)
    assert result.goto == END
    assert "Which build option" in result.update["messages"][0].content


def test_experiment_clarification_uses_only_frozen_policy(monkeypatch) -> None:
    policy = SimpleNamespace(
        expected_repo_url="https://github.com/fmtlib/fmt",
        expected_commit_sha="1" * 40,
        expected_build_system="cmake",
        required_system_packages=("build-essential", "cmake"),
        cmake_arguments=("-DFMT_TEST=OFF", "-DBUILD_SHARED_LIBS=OFF"),
        configure_arguments=(),
    )
    monkeypatch.setattr(
        module,
        "claim_experiment_clarification_auto_answer",
        lambda request: policy,
    )

    result = module.ClarificationMiddleware()._handle_clarification(_request())

    assert isinstance(result, ToolMessage)
    assert result.name == "ask_clarification"
    assert result.tool_call_id == "call-clarify-1"
    assert policy.expected_repo_url in result.content
    assert policy.expected_commit_sha in result.content
    assert "-DFMT_TEST=OFF -DBUILD_SHARED_LIBS=OFF" in result.content
    assert "Which build option" not in result.content
