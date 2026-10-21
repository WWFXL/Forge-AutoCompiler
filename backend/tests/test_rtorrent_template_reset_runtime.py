"""共同原执行/重放使用同一宿主身份，且不会污染冻结入口。"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_rtorrent_template_reset_gate as gate  # noqa: E402


def test_host_identity_extension_is_same_for_compile_and_replay():
    session = SimpleNamespace(parallel_jobs=2)
    runtime = gate.HostIdentityRuntime()
    with patch.object(gate.arm_module, "CompileDockerRuntime", gate.HostIdentityRuntime):
        flags = runtime._parallel_policy_flags(session)
    assert flags[:2] == ["--cpus", "2"]
    assert flags[-2:] == ["--user", f"{os.getuid()}:{os.getgid()}"]
    assert gate.arm_module.CompileDockerRuntime is gate.BaseRuntime


def test_run_wrapper_binds_identity_and_restores_frozen_module(tmp_path, monkeypatch):
    before = {k: os.environ.get(k) for k in ("FORGE_HOST_UID", "FORGE_HOST_GID")}

    def fake(spec, folder):
        assert gate.arm_module.CompileDockerRuntime is gate.HostIdentityRuntime
        assert os.environ["FORGE_HOST_UID"] == str(os.getuid())
        assert os.environ["FORGE_HOST_GID"] == str(os.getgid())
        return {"ok": True}

    monkeypatch.setattr(gate.original_gate, "run_slot", fake)
    assert gate.run_slot({}, tmp_path) == {"ok": True}
    assert gate.arm_module.CompileDockerRuntime is gate.BaseRuntime
    assert {k: os.environ.get(k) for k in before} == before
