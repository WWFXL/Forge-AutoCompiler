from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

SubagentModel = str | Literal["inherit"]


@dataclass(frozen=True)
class SubagentRuntimeProfile:
    use_thread_data_middleware: bool = True


@dataclass(frozen=True)
class SubagentConfig:
    name: str
    description: str
    system_prompt: str
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    model: SubagentModel = "inherit"
    max_turns: int | None = None
    timeout_seconds: int = 900
    runtime_profile: SubagentRuntimeProfile = field(default_factory=SubagentRuntimeProfile)

    def with_overrides(self, **kwargs) -> "SubagentConfig":
        return replace(self, **kwargs)
