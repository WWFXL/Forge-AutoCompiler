"""Built-in subagent configurations."""

from .bash_agent import BASH_AGENT_CONFIG
from .compiler_agent import COMPILER_AGENT_CONFIG
from .general_purpose import GENERAL_PURPOSE_CONFIG

__all__ = [
    "GENERAL_PURPOSE_CONFIG",
    "BASH_AGENT_CONFIG",
    "COMPILER_AGENT_CONFIG",
]

BUILTIN_SUBAGENTS = {
    "general-purpose": GENERAL_PURPOSE_CONFIG,
    "bash": BASH_AGENT_CONFIG,
    "compiler": COMPILER_AGENT_CONFIG,
}
