"""Tests for Forge subagent availability and prompt exposure."""

from deerflow.agents.lead_agent import prompt as prompt_module
from deerflow.subagents import registry as registry_module


def test_get_available_subagent_names_exposes_registered_forge_agents() -> None:
    names = registry_module.get_available_subagent_names()

    assert names == registry_module.get_subagent_names()
    assert names == ["general-purpose", "bash", "compiler"]


def test_build_subagent_section_hides_bash_examples_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(prompt_module, "get_available_subagent_names", lambda: ["general-purpose"])

    section = prompt_module._build_subagent_section(3)

    assert "Not available in the current runtime" in section
    assert "AioSandboxProvider" not in section
    assert "prepare_compile_session" in section
    assert "clone_repository" in section
    assert "finalize_session" in section
    assert "host_read" in section


def test_build_subagent_section_includes_bash_when_available(monkeypatch) -> None:
    monkeypatch.setattr(prompt_module, "get_available_subagent_names", lambda: ["general-purpose", "bash", "compiler"])

    section = prompt_module._build_subagent_section(3)

    assert "For command execution (git, build, test, deploy operations)" in section
    assert "For isolated C/C++ build execution and post-build verification" in section
    assert "AioSandboxProvider" not in section
    assert "prepare_compile_session" in section
    assert "clone_repository" in section
    assert "finalize_session" in section
