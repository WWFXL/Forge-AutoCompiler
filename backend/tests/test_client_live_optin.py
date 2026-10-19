"""只收集真实测试定义，验证默认回归不会因本地配置而调用 Provider。"""

import runpy
from pathlib import Path

import pytest

MODULE = Path(__file__).with_name("test_client_live.py")
CONFIG = MODULE.parents[2] / "config.yaml"


@pytest.mark.parametrize(
    ("optin", "ci", "config_exists", "reason"),
    [
        (None, None, True, "explicit FORGE_RUN_CLIENT_LIVE=1"),
        ("0", None, True, "explicit FORGE_RUN_CLIENT_LIVE=1"),
        ("1", "1", True, "skipped in CI"),
        ("1", None, False, "No config.yaml"),
        ("1", None, True, None),
    ],
)
def test_live_module_requires_explicit_optin_and_local_configuration(monkeypatch, optin, ci, config_exists, reason):
    for key, value in (("FORGE_RUN_CLIENT_LIVE", optin), ("CI", ci)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    original_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda path: config_exists if path == CONFIG else original_exists(path))
    # run_path 只定义测试与fixture，不执行客户端或模型请求。
    if reason:
        with pytest.raises(pytest.skip.Exception, match=reason):
            runpy.run_path(str(MODULE))
    else:
        module = runpy.run_path(str(MODULE))
        assert "TestLiveBasicChat" in module
