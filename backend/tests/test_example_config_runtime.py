from pathlib import Path

import yaml
from langchain.tools import BaseTool

from deerflow.reflection import resolve_variable

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_example_configured_tool_paths_resolve() -> None:
    config = yaml.safe_load((REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8"))

    for tool in config.get("tools", []):
        resolved = resolve_variable(tool["use"], BaseTool)
        assert resolved.name == tool["name"]


def test_example_disables_removed_general_sandbox() -> None:
    config = yaml.safe_load((REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8"))

    assert config.get("sandbox") is None
