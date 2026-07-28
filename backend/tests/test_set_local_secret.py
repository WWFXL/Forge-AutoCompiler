from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "set_local_secret.py"
SPEC = importlib.util.spec_from_file_location("set_local_secret", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
set_local_secret = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(set_local_secret)


def test_update_env_replaces_once_and_normalizes_lf(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"OTHER=value\r\nDEEPSEEK_API_KEY=old\r\nDEEPSEEK_API_KEY=duplicate\r\n")

    set_local_secret.update_env(env_file, "DEEPSEEK_API_KEY", "sk-new_value")

    payload = env_file.read_bytes()
    assert payload == b"OTHER=value\nDEEPSEEK_API_KEY=sk-new_value\n"


def test_update_env_appends_without_exposing_other_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=private\n", encoding="utf-8")

    set_local_secret.update_env(env_file, "DEEPSEEK_API_KEY", "sk-new")

    assert env_file.read_text(encoding="utf-8") == "OTHER=private\n\nDEEPSEEK_API_KEY=sk-new\n"


def test_update_env_accepts_loopback_proxy_without_credentials(tmp_path):
    env_file = tmp_path / ".env"

    set_local_secret.update_env(env_file, "FORGE_MODEL_PROXY_UPSTREAM", "http://127.0.0.1:7897")

    assert env_file.read_text(encoding="utf-8") == "FORGE_MODEL_PROXY_UPSTREAM=http://127.0.0.1:7897\n"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("UNSUPPORTED", "sk-valid"),
        ("DEEPSEEK_API_KEY", "plain-text"),
        ("DEEPSEEK_API_KEY", "sk-value\nSECOND=leak"),
        ("FORGE_MODEL_PROXY_UPSTREAM", "http://192.168.1.2:7897"),
        ("FORGE_MODEL_PROXY_UPSTREAM", "http://user:password@127.0.0.1:7897"),
    ],
)
def test_update_env_rejects_unsafe_name_or_value(tmp_path, name, value):
    with pytest.raises(set_local_secret.SecretError):
        set_local_secret.update_env(tmp_path / ".env", name, value)
