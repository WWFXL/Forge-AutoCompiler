"""只验证新单次入口及付费前门禁，不冒充模型构建效果。"""

import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
entry = importlib.import_module("forge_libffi_environment_autonomous")


def authorization(now):
    return dict(identity=entry.IDENTITY, maximum_cost_usd="1.00", user_authorized=True, deadline_utc=(now + timedelta(minutes=55)).isoformat())


@pytest.mark.parametrize(
    "change",
    [
        dict(identity="cpp-build-libffi-dependency-guidance-flash-v1"),
        dict(maximum_cost_usd="2.00"),
        dict(user_authorized=False),
        dict(user_authorized="true"),
        dict(deadline_utc="2020-01-01T00:00:00+00:00"),
        dict(deadline_utc="2099-01-01T00:00:00+00:00"),
        dict(deadline_utc="2026-11-16T12:00:00"),
    ],
)
def test_invalid_authorization_never_reaches_runtime_or_provider(tmp_path, monkeypatch, change):
    auth = authorization(datetime.now(UTC)) | change
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(auth))
    output = tmp_path / "formal-evidence"
    monkeypatch.setattr(sys, "argv", ["entry", "--authorization", str(path), "--output", str(output)])
    monkeypatch.setattr(entry, "material", lambda: (None, None, None, None))

    def forbidden(*args, **kwargs):
        pytest.fail("无有效授权不得访问Docker或创建Provider")

    monkeypatch.setattr(entry.subprocess, "run", forbidden)
    monkeypatch.setattr(entry, "PlanThinkingDeepSeek", forbidden)
    with pytest.raises(ValueError, match="授权"):
        entry.main()
    assert not output.exists()


def test_valid_single_run_authorization():
    now = datetime.now(UTC)
    entry.validate_authorization(authorization(now), now=now)


def test_default_cli_only_checks_material(monkeypatch, capsys):
    class Task:
        def model_dump(self, **kwargs):
            return {"name": "libffi"}

    monkeypatch.setattr(sys, "argv", ["entry"])
    monkeypatch.setattr(entry, "material", lambda: (Task(), None, None, None))

    def forbidden(*args, **kwargs):
        pytest.fail("默认入口不得创建Provider或检查Docker")

    monkeypatch.setattr(entry.subprocess, "run", forbidden)
    monkeypatch.setattr(entry, "PlanThinkingDeepSeek", forbidden)
    entry.main()
    result = json.loads(capsys.readouterr().out)
    assert result["identity"] == "cpp-build-libffi-environment-tools-flash-v1"
    assert result["provider_calls"] == 0 and result["credentials_read"] is False
