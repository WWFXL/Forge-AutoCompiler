"""非root共同准备使用容器临时Git配置，不更改主机用户目录。"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_template_reset_gate_v2 as gate  # noqa: E402


def test_runtime_sets_explicit_container_git_config_for_compile_and_replay():
    with patch.object(gate.arm_module, "CompileDockerRuntime", gate.HostIdentityRuntime):
        flags = gate.HostIdentityRuntime._parallel_policy_flags(SimpleNamespace(parallel_jobs=2))
    assert flags[-4:] == ["--user", f"{os.getuid()}:{os.getgid()}", "--env", "GIT_CONFIG_GLOBAL=/tmp/forge-global.gitconfig"]
    assert flags[:2] == ["--cpus", "2"]
    assert gate.arm_module.CompileDockerRuntime is gate.BaseRuntime
