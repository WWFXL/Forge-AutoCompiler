from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
UPGRADE_SCRIPT = REPO_ROOT / "scripts" / "config-upgrade.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("uv") is None,
    reason="config upgrade integration tests require bash and uv",
)

WEB_TOOLS = [
    {"name": "web_search", "group": "web", "use": "custom.web:web_search"},
    {"name": "web_fetch", "group": "web", "use": "custom.web:web_fetch"},
    {"name": "image_search", "group": "web", "use": "custom.web:image_search"},
]
LEGACY_TOOLS = [
    {"name": "ls", "group": "file:read", "use": "deerflow.sandbox.tools:ls_tool"},
    {"name": "read_file", "group": "file:read", "use": "deerflow.sandbox.tools:read_file_tool"},
    {"name": "glob", "group": "file:read", "use": "deerflow.sandbox.tools:glob_tool"},
    {"name": "grep", "group": "file:read", "use": "deerflow.sandbox.tools:grep_tool"},
    {"name": "write_file", "group": "file:write", "use": "deerflow.sandbox.tools:write_file_tool"},
    {"name": "str_replace", "group": "file:write", "use": "deerflow.sandbox.tools:str_replace_tool"},
    {"name": "bash", "group": "bash", "use": "deerflow.sandbox.tools:bash_tool"},
]


def _run_upgrade(tmp_path: Path, config: dict) -> tuple[subprocess.CompletedProcess[str], Path]:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    env = os.environ.copy()
    env["DEER_FLOW_CONFIG_PATH"] = str(config_path)
    result = subprocess.run(
        ["bash", str(UPGRADE_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result, config_path


def test_v5_upgrade_removes_obsolete_runtime_and_orphaned_groups(tmp_path: Path) -> None:
    original = {
        "config_version": 5,
        "tool_groups": [{"name": "web"}, {"name": "file:read"}, {"name": "file:write"}, {"name": "bash"}],
        "tools": WEB_TOOLS + LEGACY_TOOLS,
        "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider", "allow_host_bash": False},
        "custom_field": {"preserve": True},
    }

    result, config_path = _run_upgrade(tmp_path, original)

    assert result.returncode == 0, result.stderr
    upgraded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert upgraded["config_version"] == 6
    assert upgraded["sandbox"] is None
    assert [tool["name"] for tool in upgraded["tools"]] == ["web_search", "web_fetch", "image_search"]
    assert [group["name"] for group in upgraded["tool_groups"]] == ["web"]
    assert upgraded["custom_field"] == {"preserve": True}

    backup = yaml.safe_load(config_path.with_suffix(".yaml.bak").read_text(encoding="utf-8"))
    assert backup == original

    first_upgrade = config_path.read_text(encoding="utf-8")
    second_env = os.environ.copy()
    second_env["DEER_FLOW_CONFIG_PATH"] = str(config_path)
    second = subprocess.run(
        ["bash", str(UPGRADE_SCRIPT)],
        cwd=REPO_ROOT,
        env=second_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert second.returncode == 0, second.stderr
    assert config_path.read_text(encoding="utf-8") == first_upgrade


def test_quoted_version_preserves_custom_provider_and_referenced_legacy_group(tmp_path: Path) -> None:
    custom_tool = {"name": "custom_reader", "group": "file:read", "use": "custom.tools:reader", "custom_option": "keep"}
    original = {
        "config_version": "5",
        "tool_groups": [{"name": "web"}, {"name": "file:read"}, {"name": "file:write"}, {"name": "bash"}],
        "tools": WEB_TOOLS + [LEGACY_TOOLS[1], custom_tool],
        "sandbox": {"use": "custom.sandbox:Provider", "custom_option": "keep"},
        "tool_search": {"enabled": False, "custom_option": "keep"},
    }

    result, config_path = _run_upgrade(tmp_path, original)

    assert result.returncode == 0, result.stderr
    upgraded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert upgraded["config_version"] == 6
    assert upgraded["sandbox"] == original["sandbox"]
    assert [tool["name"] for tool in upgraded["tools"]] == ["web_search", "web_fetch", "image_search", "custom_reader"]
    assert upgraded["tools"][-1]["custom_option"] == "keep"
    assert [group["name"] for group in upgraded["tool_groups"]] == ["web", "file:read"]
    assert upgraded["tool_search"]["custom_option"] == "keep"


def test_null_version_is_treated_as_pre_versioned_config(tmp_path: Path) -> None:
    result, config_path = _run_upgrade(
        tmp_path,
        {"config_version": None, "tools": [], "tool_groups": [], "sandbox": None, "custom_field": "keep"},
    )

    assert result.returncode == 0, result.stderr
    upgraded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert upgraded["config_version"] == 6
    assert upgraded["custom_field"] == "keep"


def test_invalid_version_fails_without_modifying_config(tmp_path: Path) -> None:
    original = {"config_version": "five", "tools": [], "sandbox": None}
    result, config_path = _run_upgrade(tmp_path, original)

    assert result.returncode == 2
    assert "config_version must be a non-negative integer" in result.stderr
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original
    assert not config_path.with_suffix(".yaml.bak").exists()
