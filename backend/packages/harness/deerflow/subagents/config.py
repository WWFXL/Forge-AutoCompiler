from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

SubagentModel = str | Literal["inherit"]


@dataclass(frozen=True)
class SubagentRuntimeProfile:
    use_thread_data_middleware: bool = True
    use_sandbox_middleware: bool = True


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
    model_turn_limit: int | None = None
    graph_recursion_limit: int | None = None
    wall_clock_timeout_seconds: int | None = None
    post_build_reserve_seconds: int = 0

    def with_overrides(self, **kwargs) -> SubagentConfig:
        return replace(self, **kwargs)

    @property
    def effective_graph_recursion_limit(self) -> int | None:
        """Return the explicit graph budget, falling back to the legacy field."""
        return self.graph_recursion_limit if self.graph_recursion_limit is not None else self.max_turns

    @property
    def effective_wall_clock_timeout_seconds(self) -> int:
        """Return the explicit wall-clock budget, falling back to the legacy field."""
        return self.wall_clock_timeout_seconds or self.timeout_seconds

    @property
    def has_explicit_compiler_budgets(self) -> bool:
        return any(
            (
                self.model_turn_limit is not None,
                self.graph_recursion_limit is not None,
                self.wall_clock_timeout_seconds is not None,
                self.post_build_reserve_seconds > 0,
            )
        )
