"""generic原宿主模式与整批停止边界。"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_test_preparation_comparison_v3 as runner  # noqa: E402

from deerflow.compile.manager import CompileSessionManager  # noqa: E402


def test_generic_host_mode_preserves_original_unconfigured_identity(monkeypatch):
    monkeypatch.setenv("FORGE_HOST_UID", "1010")
    monkeypatch.setenv("FORGE_HOST_GID", "1010")
    with runner.execution_window((datetime.now(UTC) + timedelta(hours=2)).isoformat()):
        assert CompileSessionManager().host_identity is None
    assert CompileSessionManager().host_identity == (1010, 1010)


def test_operator_signal_stops_whole_batch(monkeypatch):
    monkeypatch.setattr(runner, "STOP_REQUESTED", False)
    with pytest.raises(runner.base.PlanContractError, match="operator_or_deadline_stop"):
        runner.request_stop(None, None)
    assert runner.STOP_REQUESTED
    assert runner.execute({"schedule": [{"project": "unused"}]}, None, None, []) == "operator_or_deadline_stop"
