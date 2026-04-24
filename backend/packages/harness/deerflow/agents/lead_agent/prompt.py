"""Lead-agent prompt helpers.

This file keeps the lead prompt lightweight. Detailed repository-compilation
workflow knowledge intentionally lives in the compiler subagent prompt instead
of the lead prompt, so non-compilation conversations are not polluted by a
large always-on build workflow description.
"""

import asyncio
import logging
import threading
from datetime import datetime
from functools import lru_cache

from deerflow.config.agents_config import load_agent_soul
from deerflow.skills import load_skills
from deerflow.skills.types import Skill
from deerflow.subagents import get_available_subagent_names

logger = logging.getLogger(__name__)

_ENABLED_SKILLS_REFRESH_WAIT_TIMEOUT_SECONDS = 5.0
_enabled_skills_lock = threading.Lock()
_enabled_skills_cache: list[Skill] | None = None
_enabled_skills_refresh_active = False
_enabled_skills_refresh_version = 0
_enabled_skills_refresh_event = threading.Event()


def _load_enabled_skills_sync() -> list[Skill]:
    return list(load_skills(enabled_only=True))


def _start_enabled_skills_refresh_thread() -> None:
    threading.Thread(
        target=_refresh_enabled_skills_cache_worker,
        name="deerflow-enabled-skills-loader",
        daemon=True,
    ).start()


def _refresh_enabled_skills_cache_worker() -> None:
    global _enabled_skills_cache, _enabled_skills_refresh_active

    while True:
        with _enabled_skills_lock:
            target_version = _enabled_skills_refresh_version

        try:
            skills = _load_enabled_skills_sync()
        except Exception:
            logger.exception("Failed to load enabled skills for prompt injection")
            skills = []

        with _enabled_skills_lock:
            if _enabled_skills_refresh_version == target_version:
                _enabled_skills_cache = skills
                _enabled_skills_refresh_active = False
                _enabled_skills_refresh_event.set()
                return

            _enabled_skills_cache = None


def _ensure_enabled_skills_cache() -> threading.Event:
    global _enabled_skills_refresh_active

    with _enabled_skills_lock:
        if _enabled_skills_cache is not None:
            _enabled_skills_refresh_event.set()
            return _enabled_skills_refresh_event
        if _enabled_skills_refresh_active:
            return _enabled_skills_refresh_event
        _enabled_skills_refresh_active = True
        _enabled_skills_refresh_event.clear()

    _start_enabled_skills_refresh_thread()
    return _enabled_skills_refresh_event


def _invalidate_enabled_skills_cache() -> threading.Event:
    global _enabled_skills_cache, _enabled_skills_refresh_active, _enabled_skills_refresh_version

    _get_cached_skills_prompt_section.cache_clear()
    with _enabled_skills_lock:
        _enabled_skills_cache = None
        _enabled_skills_refresh_version += 1
        _enabled_skills_refresh_event.clear()
        if _enabled_skills_refresh_active:
            return _enabled_skills_refresh_event
        _enabled_skills_refresh_active = True

    _start_enabled_skills_refresh_thread()
    return _enabled_skills_refresh_event


def prime_enabled_skills_cache() -> None:
    _ensure_enabled_skills_cache()


def warm_enabled_skills_cache(timeout_seconds: float = _ENABLED_SKILLS_REFRESH_WAIT_TIMEOUT_SECONDS) -> bool:
    if _ensure_enabled_skills_cache().wait(timeout=timeout_seconds):
        return True

    logger.warning("Timed out waiting %.1fs for enabled skills cache warm-up", timeout_seconds)
    return False


def _get_enabled_skills():
    with _enabled_skills_lock:
        cached = _enabled_skills_cache

    if cached is not None:
        return list(cached)

    _ensure_enabled_skills_cache()
    return []


def _skill_mutability_label(category: str) -> str:
    return "[custom, editable]" if category == "custom" else "[built-in]"


def clear_skills_system_prompt_cache() -> None:
    _invalidate_enabled_skills_cache()


async def refresh_skills_system_prompt_cache_async() -> None:
    await asyncio.to_thread(_invalidate_enabled_skills_cache().wait)


def _reset_skills_system_prompt_cache_state() -> None:
    global _enabled_skills_cache, _enabled_skills_refresh_active, _enabled_skills_refresh_version

    _get_cached_skills_prompt_section.cache_clear()
    with _enabled_skills_lock:
        _enabled_skills_cache = None
        _enabled_skills_refresh_active = False
        _enabled_skills_refresh_version = 0
        _enabled_skills_refresh_event.clear()


def _refresh_enabled_skills_cache() -> None:
    try:
        skills = _load_enabled_skills_sync()
    except Exception:
        logger.exception("Failed to load enabled skills for prompt injection")
        skills = []

    with _enabled_skills_lock:
        _enabled_skills_cache = skills
        _enabled_skills_refresh_active = False
        _enabled_skills_refresh_event.set()


def _build_skill_evolution_section(skill_evolution_enabled: bool) -> str:
    if not skill_evolution_enabled:
        return ""
    return """
## Skill Self-Evolution
After completing a task, consider creating or updating a skill when:
- The task required 5+ tool calls to resolve
- You overcame non-obvious errors or pitfalls
- The user corrected your approach and the corrected version worked
- You discovered a non-trivial, recurring workflow
If you used a skill and encountered issues not covered by it, patch it immediately.
Prefer patch over edit. Before creating a new skill, confirm with the user first.
Skip simple one-off tasks.
"""


def _build_subagent_section(max_concurrent: int) -> str:
    n = max_concurrent
    bash_available = "bash" in get_available_subagent_names()
    available_subagents = (
        "- **general-purpose**: For ANY non-trivial task - web research, code exploration, file operations, analysis, etc.\n"
        "- **bash**: For command execution (git, build, test, deploy operations)\n"
        "- **compiler**: For isolated C/C++ build execution and post-build verification inside a prepared compile container"
        if bash_available
        else "- **general-purpose**: For ANY non-trivial task - web research, code exploration, file operations, analysis, etc.\n"
        "- **bash**: Not available in the current sandbox configuration. Use direct file/web tools or switch to AioSandboxProvider for isolated shell access.\n"
        "- **compiler**: For isolated C/C++ build execution and post-build verification inside a prepared compile container"
    )
    direct_tool_examples = "prepare_workspace, identify_build_system, finalize_session, read_file, web_search, etc."
    direct_execution_example = (
        '# User asks: "Build this repository"\n'
        '# Thinking: I should treat the lead-agent compile task as living under /workspace/.compile-sessions/<thread_id>/<session_id>, use that path for my own inspection, then delegate build+verify execution to the compiler subagent.\n\n'
        'prepare_workspace(repo_url="https://example.com/repo.git")\n'
        'identify_build_system()\n'
        'task(description="build and verify repository", prompt="build the project, run post-build verification, and report structured results; note that any subagent-mentioned project directory is informational only and does not replace the lead-agent working root /workspace/.compile-sessions/<thread_id>/<session_id>", subagent_type="compiler")\n'
        'finalize_session()'
    )
    return f"""<subagent_system>
**🚀 SUBAGENT MODE ACTIVE - DECOMPOSE, DELEGATE, SYNTHESIZE**

You are running with subagent capabilities enabled. Your role is to be a **task orchestrator**:
1. **DECOMPOSE**: Break complex tasks into parallel sub-tasks
2. **DELEGATE**: Launch multiple subagents simultaneously using parallel `task` calls
3. **SYNTHESIZE**: Collect and integrate results into a coherent answer

**CORE PRINCIPLE: Complex tasks should be decomposed and distributed across multiple subagents for parallel execution.**

**⛔ HARD CONCURRENCY LIMIT: MAXIMUM {n} `task` CALLS PER RESPONSE. THIS IS NOT OPTIONAL.**
- Each response, you may include **at most {n}** `task` tool calls. Any excess calls are **silently discarded** by the system — you will lose that work.
- Before launching subagents, count them explicitly in your thinking.
- For repository compilation tasks, you must orchestrate the flow yourself: `prepare_workspace` → `identify_build_system` → `task(subagent_type="compiler")` → `finalize_session`.
- Lead-agent work for each compile task is anchored at `/workspace/.compile-sessions/<thread_id>/<session_id>`.
- If a compiler subagent reports that the project is located in some other directory, treat that as subagent-side informational output only; it does not redefine the lead agent's working directory.
- Do not reason about subagent working directories. Tool bindings already encapsulate the correct execution location.
- Do not use `run_compile_workflow` as the primary path for new compilation tasks.

**Available Subagents:**
{available_subagents}

✅ **USE Parallel Subagents (max {n} per turn) when:**
- Complex research questions requiring multiple sources
- Multi-aspect investigations across independent dimensions
- Large codebases requiring parallel analysis
- Repository build execution after infrastructure setup is complete

❌ **DO NOT use subagents when:**
- The task cannot be decomposed into meaningful sub-tasks
- The action is ultra-simple
- Clarification is required first
- The task is purely meta-conversation

**Recommended repository compilation pattern:**
```python
{direct_execution_example}
```

**Direct tool examples:** {direct_tool_examples}
</subagent_system>"""


SYSTEM_PROMPT_TEMPLATE = """
<role>
You are {agent_name}, an open-source compilation-focused agent.
</role>

{soul}
{memory_context}

<thinking_style>
- Think concisely and strategically about the user's request BEFORE taking action
- Break down the task: What is clear? What is ambiguous? What is missing?
- First determine whether the request is a repository compilation/build task, a compile-result analysis task, or a different kind of task
- **PRIORITY CHECK: If anything is unclear, missing, or has multiple interpretations, you MUST ask for clarification FIRST - do NOT proceed with work**
{subagent_thinking}- Never write down your full final answer or report in thinking process, but only outline
- CRITICAL: After thinking, you MUST provide your actual response to the user. Thinking is for planning, the response is for delivery.
- Your response must contain the actual answer, not just a reference to what you thought about
</thinking_style>

<clarification_system>
**WORKFLOW PRIORITY: CLARIFY → PLAN → ACT**
1. **FIRST**: Analyze the request in your thinking - identify what's unclear, missing, or ambiguous
2. **SECOND**: If clarification is needed, call `ask_clarification` tool IMMEDIATELY - do NOT start working
3. **THIRD**: Only after all clarifications are resolved, proceed with planning and execution
</clarification_system>

<compile_task_model>
- For remote repository compilation or build tasks, do not rely on the legacy one-shot workflow as the primary path
- Use the infrastructure-tool chain: `prepare_workspace`, `identify_build_system`, delegated `task(subagent_type="compiler")`, then `finalize_session`
- `prepare_workspace`, `identify_build_system`, and `finalize_session` are deterministic infrastructure tools running in the DeerFlow service container
- The DeerFlow service container is rooted at `/workspace`; each compile task should be treated as anchored at `/workspace/.compile-sessions/<thread_id>/<session_id>`
- Lead-agent repository inspection should use the compile-session directory under `/workspace/.compile-sessions/<thread_id>/<session_id>` and must not be re-anchored by subagent-reported paths
- The `compiler` subagent is responsible for build/dependency work and routine post-build verification; do not rely on the subagent's own directory descriptions for lead-agent reasoning
- Use generic file exploration only when it is clearly necessary for analysis and not a substitute for the infrastructure-tool chain
</compile_task_model>

<compile_path_model>
- For lead-agent reasoning, there is one authoritative working root per compile task: `/workspace/.compile-sessions/<thread_id>/<session_id>`
- Subagent output may mention other directories, but those do not redefine the lead-agent working root
- Treat tool-returned paths for logs, artifacts, repro files, and verification outputs as authoritative; do not guess paths when structured results are available
</compile_path_model>

{skills_section}

{deferred_tools_section}

{subagent_section}

<compile_analysis_behavior>
- For repository compilation tasks, first establish the compile workspace, then identify the build system, then delegate build execution to the `compiler` subagent, and always finalize the session afterward
- After compile tools or subagents return log, artifact, or verification paths, use those returned paths to inspect relevant files as needed
- Prefer targeted log reading over aimless directory traversal
- If a compiler subagent reports a project path like `/workspace/repo`, treat it as execution-side context only; do not let it replace the lead-agent compile-session root
- If compilation fails, inspect the most relevant returned logs before proposing fixes or retry strategies
- If compilation succeeds, treat the compiler subagent's structured verification result as the primary source for routine post-build validation
- Use returned verification summaries, artifact paths, and verification logs before considering any extra compiler-side execution
- Do not launch another compiler subagent for ordinary artifact checks when verification has already completed successfully
- Lead-agent verification is acceptance-oriented: decide whether the verified artifacts satisfy the user's stated goal
</compile_analysis_behavior>

<working_model>
- Lead-agent filesystem work for compile tasks always happens under `/workspace/.compile-sessions/<thread_id>/<session_id>`
- Subagent working directories do not matter for lead-agent reasoning because execution location is already encapsulated by the bound tools
- When summarizing results after subagent execution, distinguish between lead-agent session paths and any informational subagent-reported execution paths
{acp_section}
</working_model>

<critical_reminders>
- **Clarification First**: ALWAYS clarify unclear/missing/ambiguous requirements BEFORE starting work - never assume or guess
{subagent_reminder}- Skill First: Always load the relevant skill before starting **complex** tasks.
- Prefer compile-session tooling and compile-tool outputs over hard-coded directory assumptions
- Prefer compiler-subagent verification outputs over ad-hoc repeated verification work
- Never let a subagent-reported repository directory override the lead-agent compile-session root
- Clarity: Be direct and helpful, avoid unnecessary meta-commentary
- Language Consistency: Keep using the same language as user's
- Always Respond: Your thinking is internal. You MUST always provide a visible response to the user after thinking.
</critical_reminders>
"""


def _get_memory_context(agent_name: str | None = None) -> str:
    try:
        from deerflow.agents.memory import format_memory_for_injection, get_memory_data
        from deerflow.config.memory_config import get_memory_config

        config = get_memory_config()
        if not config.enabled or not config.injection_enabled:
            return ""

        memory_data = get_memory_data(agent_name)
        memory_content = format_memory_for_injection(memory_data, max_tokens=config.max_injection_tokens)

        if not memory_content.strip():
            return ""

        return f"""<memory>
{memory_content}
</memory>
"""
    except Exception as e:
        logger.error("Failed to load memory context: %s", e)
        return ""


@lru_cache(maxsize=32)
def _get_cached_skills_prompt_section(
    skill_signature: tuple[tuple[str, str, str, str], ...],
    available_skills_key: tuple[str, ...] | None,
    container_base_path: str,
    skill_evolution_section: str,
) -> str:
    filtered = [(name, description, category, location) for name, description, category, location in skill_signature if available_skills_key is None or name in available_skills_key]
    skills_list = ""
    if filtered:
        skill_items = "\n".join(
            f"    <skill>\n        <name>{name}</name>\n        <description>{description} {_skill_mutability_label(category)}</description>\n        <location>{location}</location>\n    </skill>"
            for name, description, category, location in filtered
        )
        skills_list = f"<available_skills>\n{skill_items}\n</available_skills>"
    return f"""<skill_system>
You have access to skills that provide optimized workflows for specific tasks. Each skill contains best practices, frameworks, and references to additional resources.

**Progressive Loading Pattern:**
1. When a user query matches a skill's use case, immediately call `read_file` on the skill's main file using the path attribute provided in the skill tag below
2. Read and understand the skill's workflow and instructions
3. The skill file contains references to external resources under the same folder
4. Load referenced resources only when needed during execution
5. Follow the skill's instructions precisely

**Skills are located at:** {container_base_path}
{skill_evolution_section}
{skills_list}

</skill_system>"""


def get_skills_prompt_section(available_skills: set[str] | None = None) -> str:
    skills = _get_enabled_skills()

    try:
        from deerflow.config import get_app_config

        config = get_app_config()
        container_base_path = config.skills.container_path
        skill_evolution_enabled = config.skill_evolution.enabled
    except Exception:
        container_base_path = "/mnt/skills"
        skill_evolution_enabled = False

    if not skills and not skill_evolution_enabled:
        return ""

    if available_skills is not None and not any(skill.name in available_skills for skill in skills):
        return ""

    skill_signature = tuple((skill.name, skill.description, skill.category, skill.get_container_file_path(container_base_path)) for skill in skills)
    available_key = tuple(sorted(available_skills)) if available_skills is not None else None
    if not skill_signature and available_key is not None:
        return ""
    skill_evolution_section = _build_skill_evolution_section(skill_evolution_enabled)
    return _get_cached_skills_prompt_section(skill_signature, available_key, container_base_path, skill_evolution_section)


def get_agent_soul(agent_name: str | None) -> str:
    soul = load_agent_soul(agent_name)
    if soul:
        return f"<soul>\n{soul}\n</soul>\n" if soul else ""
    return ""


def get_deferred_tools_prompt_section() -> str:
    from deerflow.tools.builtins.tool_search import get_deferred_registry

    try:
        from deerflow.config import get_app_config

        if not get_app_config().tool_search.enabled:
            return ""
    except Exception:
        return ""

    registry = get_deferred_registry()
    if not registry:
        return ""

    names = "\n".join(e.name for e in registry.entries)
    return f"<available-deferred-tools>\n{names}\n</available-deferred-tools>"


def _build_acp_section() -> str:
    try:
        from deerflow.config.acp_config import get_acp_agents

        agents = get_acp_agents()
        if not agents:
            return ""
    except Exception:
        return ""

    return (
        "\n**ACP Agent Tasks (invoke_acp_agent):**\n"
        "- ACP agents run in their own independent workspace\n"
        "- Do NOT assume compile-session paths exist inside ACP agent workspaces\n"
        "- ACP agent results are accessible at `/mnt/acp-workspace/`\n"
    )


def _build_custom_mounts_section() -> str:
    try:
        from deerflow.config.app_config import get_app_config

        mounts = get_app_config().custom_mounts
        if not mounts:
            return ""
    except Exception:
        return ""

    mount_lines = []
    for mount in mounts:
        source = getattr(mount, "source", None) or getattr(mount, "host_path", None)
        target = getattr(mount, "target", None) or getattr(mount, "container_path", None)
        if source and target:
            mount_lines.append(f"- `{target}` is mounted from `{source}`")

    if not mount_lines:
        return ""

    return "\n<custom_mounts>\n" + "\n".join(mount_lines) + "\n</custom_mounts>\n"


def apply_prompt_template(
    subagent_enabled: bool = False,
    max_concurrent_subagents: int = 1,
    agent_name: str | None = None,
    available_skills: set[str] | None = None,
) -> str:
    soul = get_agent_soul(agent_name)
    memory_context = _get_memory_context(agent_name)
    skills_section = get_skills_prompt_section(available_skills)
    deferred_tools_section = get_deferred_tools_prompt_section()
    acp_section = _build_acp_section()
    custom_mounts_section = _build_custom_mounts_section()

    subagent_section = ""
    subagent_thinking = ""
    subagent_reminder = ""
    if subagent_enabled:
        subagent_section = _build_subagent_section(max_concurrent_subagents)
        subagent_thinking = "- Consider whether any part of the task should be delegated to a subagent\n"
        subagent_reminder = "- Use compiler subagents for compile-container build+verify execution, not for routine lead-agent reasoning\n"

    return SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=agent_name or "lead-agent",
        soul=soul,
        memory_context=memory_context,
        skills_section=skills_section,
        deferred_tools_section=deferred_tools_section,
        subagent_section=subagent_section,
        subagent_thinking=subagent_thinking,
        subagent_reminder=subagent_reminder,
        acp_section=acp_section + custom_mounts_section,
    )
