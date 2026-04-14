from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from deerflow.models import create_chat_model
from deerflow.subagents.config import SubagentConfig
from deerflow.tools.builtins.compile_tools import run_compile_command


@dataclass
class BuildDecision:
    command: str | None
    stage: str
    rationale: str
    should_stop: bool = False


@dataclass
class BuildAgentInput:
    repo_url: str
    build_system: str | None
    task_description: str | None
    artifact_hint: str | None
    build_goal: str | None
    previous_attempts: list[dict[str, Any]]
    latest_failure_summary: str | None
    max_build_attempts: int


class BuildDecisionAgent:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name
        self.config = SubagentConfig(
            name="compile-build-agent",
            description="Workflow-internal build decision agent",
            system_prompt=self._system_prompt(),
            tools=["run_compile_command"],
            disallowed_tools=["task"],
            model="inherit",
            max_turns=12,
            timeout_seconds=900,
        )

    def _system_prompt(self) -> str:
        return """You are the build-stage decision agent inside a controlled compile workflow.

Your ONLY responsibility is to decide the next build-related action for the current repository inside the already-prepared compile session.

## You may do
- inspect build behavior by running shell commands through `run_compile_command`
- run configure/build/install-dependency/debug commands
- install missing packages when clearly needed for compilation
- iterate a small number of times based on observed failures

## You must NOT do
- prepare or create sessions
- clone repositories
- verify artifacts
- finalize sessions
- ask the user questions
- delegate to other agents

## Execution style
- Use `run_compile_command` as your controlled shell surface inside the compile container
- Keep commands purposeful; do not wander
- Prefer one meaningful command at a time
- If a command fails, use that evidence to decide the next step
- Avoid repeating the same ineffective command
- Stop when the build appears complete or when additional attempts are unlikely to help

## Final output format
Return ONLY valid JSON with this schema:
{
  "command": string | null,
  "stage": string,
  "rationale": string,
  "should_stop": boolean
}

Rules:
- No markdown
- No code fences
- No extra commentary
- `command` must be null only when `should_stop` is true
- `stage` should be one of: inspect, install, configure, build, test, stop
"""

    def next_decision(self, agent_input: BuildAgentInput) -> BuildDecision:
        model = create_chat_model(name=self.model_name, thinking_enabled=False)
        from langchain.agents import create_agent
        from deerflow.agents.middlewares.tool_error_handling_middleware import build_subagent_runtime_middlewares

        middlewares = build_subagent_runtime_middlewares(lazy_init=True)
        agent = create_agent(
            model=model,
            tools=[run_compile_command],
            middleware=middlewares,
            system_prompt=self.config.system_prompt,
        )

        payload = {
            "repo_url": agent_input.repo_url,
            "build_system": agent_input.build_system,
            "task_description": agent_input.task_description,
            "artifact_hint": agent_input.artifact_hint,
            "build_goal": agent_input.build_goal,
            "previous_attempts": agent_input.previous_attempts,
            "latest_failure_summary": agent_input.latest_failure_summary,
            "max_build_attempts": agent_input.max_build_attempts,
        }
        prompt = (
            "Decide the next build action for this compile workflow context. "
            "Use the tool if you need more evidence before deciding.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

        result = agent.invoke(
            {"messages": [("user", prompt)]},
            config={"recursion_limit": self.config.max_turns},
        )
        messages = result.get("messages", [])
        content = ""
        for message in reversed(messages):
            msg_content = getattr(message, "content", None)
            if isinstance(msg_content, str) and msg_content.strip():
                content = msg_content.strip()
                break
            if isinstance(msg_content, list):
                text_parts = []
                for item in msg_content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        text_parts.append(item["text"])
                if text_parts:
                    content = "\n".join(text_parts).strip()
                    break

        data = json.loads(content)
        return BuildDecision(
            command=data.get("command"),
            stage=data.get("stage", "build"),
            rationale=data.get("rationale", ""),
            should_stop=bool(data.get("should_stop", False)),
        )
