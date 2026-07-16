import threading
from types import SimpleNamespace

import anyio

from deerflow.agents.lead_agent import prompt as prompt_module
from deerflow.skills.types import Skill
from deerflow.tools.tools import COMPILE_TOOLS


def test_compile_tools_register_split_session_flow():
    assert [tool.name for tool in COMPILE_TOOLS] == [
        "prepare_compile_session",
        "clone_repository",
        "identify_build_system",
        "finalize_session",
    ]


def test_lead_prompt_uses_registered_compile_workflow(monkeypatch):
    monkeypatch.setattr(prompt_module, "get_available_subagent_names", lambda: ["general-purpose", "compiler"])

    subagent_section = prompt_module._build_subagent_section(3)
    workflow = [
        "prepare_compile_session",
        "clone_repository",
        "identify_build_system",
        'task(subagent_type="compiler")',
        "finalize_session",
    ]

    assert "prepare_workspace" not in subagent_section
    assert "prepare_workspace" not in prompt_module.SYSTEM_PROMPT_TEMPLATE
    for prompt_text in (subagent_section, prompt_module.SYSTEM_PROMPT_TEMPLATE):
        positions = [prompt_text.index(tool_name) for tool_name in workflow]
        assert positions == sorted(positions)


def test_build_custom_mounts_section_returns_empty_when_no_mounts(monkeypatch):
    config = SimpleNamespace(custom_mounts=[])
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: config)

    assert prompt_module._build_custom_mounts_section() == ""


def test_build_custom_mounts_section_lists_configured_mounts(monkeypatch):
    mounts = [
        SimpleNamespace(source="/host/shared", target="/home/user/shared"),
        SimpleNamespace(host_path="/host/reference", container_path="/mnt/reference"),
    ]
    config = SimpleNamespace(custom_mounts=mounts)
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: config)

    section = prompt_module._build_custom_mounts_section()

    assert "<custom_mounts>" in section
    assert "`/home/user/shared` is mounted from `/host/shared`" in section
    assert "`/mnt/reference` is mounted from `/host/reference`" in section


def test_apply_prompt_template_includes_custom_mounts(monkeypatch):
    mounts = [SimpleNamespace(source="/host/shared", target="/home/user/shared")]
    config = SimpleNamespace(custom_mounts=mounts)
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: config)
    monkeypatch.setattr(prompt_module, "get_skills_prompt_section", lambda available_skills=None: "")
    monkeypatch.setattr(prompt_module, "get_deferred_tools_prompt_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_get_memory_context", lambda agent_name=None: "")
    monkeypatch.setattr(prompt_module, "get_agent_soul", lambda agent_name=None: "")

    prompt = prompt_module.apply_prompt_template()

    assert "`/home/user/shared` is mounted from `/host/shared`" in prompt
    assert "<custom_mounts>" in prompt


def test_refresh_skills_system_prompt_cache_async_reloads_immediately(monkeypatch, tmp_path):
    def make_skill(name: str) -> Skill:
        skill_dir = tmp_path / name
        return Skill(
            name=name,
            description=f"Description for {name}",
            license="MIT",
            skill_dir=skill_dir,
            skill_file=skill_dir / "SKILL.md",
            relative_path=skill_dir.relative_to(tmp_path),
            category="custom",
            enabled=True,
        )

    state = {"skills": [make_skill("first-skill")]}
    monkeypatch.setattr(prompt_module, "load_skills", lambda enabled_only=True: list(state["skills"]))
    prompt_module._reset_skills_system_prompt_cache_state()

    try:
        prompt_module.warm_enabled_skills_cache()
        assert [skill.name for skill in prompt_module._get_enabled_skills()] == ["first-skill"]

        state["skills"] = [make_skill("second-skill")]
        anyio.run(prompt_module.refresh_skills_system_prompt_cache_async)

        assert [skill.name for skill in prompt_module._get_enabled_skills()] == ["second-skill"]
    finally:
        prompt_module._reset_skills_system_prompt_cache_state()


def test_clear_cache_does_not_spawn_parallel_refresh_workers(monkeypatch, tmp_path):
    started = threading.Event()
    release = threading.Event()
    active_loads = 0
    max_active_loads = 0
    call_count = 0
    lock = threading.Lock()

    def make_skill(name: str) -> Skill:
        skill_dir = tmp_path / name
        return Skill(
            name=name,
            description=f"Description for {name}",
            license="MIT",
            skill_dir=skill_dir,
            skill_file=skill_dir / "SKILL.md",
            relative_path=skill_dir.relative_to(tmp_path),
            category="custom",
            enabled=True,
        )

    def fake_load_skills(enabled_only=True):
        nonlocal active_loads, max_active_loads, call_count
        with lock:
            active_loads += 1
            max_active_loads = max(max_active_loads, active_loads)
            call_count += 1
            current_call = call_count

        started.set()
        if current_call == 1:
            release.wait(timeout=5)

        with lock:
            active_loads -= 1

        return [make_skill(f"skill-{current_call}")]

    monkeypatch.setattr(prompt_module, "load_skills", fake_load_skills)
    prompt_module._reset_skills_system_prompt_cache_state()

    try:
        prompt_module.clear_skills_system_prompt_cache()
        assert started.wait(timeout=5)

        prompt_module.clear_skills_system_prompt_cache()
        release.set()
        prompt_module.warm_enabled_skills_cache()

        assert max_active_loads == 1
        assert [skill.name for skill in prompt_module._get_enabled_skills()] == ["skill-2"]
    finally:
        release.set()
        prompt_module._reset_skills_system_prompt_cache_state()


def test_warm_enabled_skills_cache_logs_on_timeout(monkeypatch, caplog):
    event = threading.Event()
    monkeypatch.setattr(prompt_module, "_ensure_enabled_skills_cache", lambda: event)

    with caplog.at_level("WARNING"):
        warmed = prompt_module.warm_enabled_skills_cache(timeout_seconds=0.01)

    assert warmed is False
    assert "Timed out waiting" in caplog.text
