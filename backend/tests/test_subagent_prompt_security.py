"""Tests for subagent registry and prompt exposure."""

from deerflow.agents.lead_agent import prompt as prompt_module
from deerflow.subagents import registry as registry_module


def test_get_available_subagent_names_exposes_registered_forge_agents() -> None:
    names = registry_module.get_available_subagent_names()

    assert names == registry_module.get_subagent_names()
    assert names == ["general-purpose", "bash", "compiler"]


def test_build_subagent_section_lists_registered_forge_agents() -> None:
    section = prompt_module._build_subagent_section(3)

    assert "For command execution (git, build, test, deploy operations)" in section
    assert "For isolated C/C++ build execution and post-build verification" in section
    assert 'task(description="build and verify repository"' in section
    assert "prepare_workspace, identify_build_system, finalize_session" in section
    assert "Not available in the current sandbox configuration" not in section
