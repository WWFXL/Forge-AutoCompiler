"""普通项目复用原依赖权限，并在请求取消时显式保留未知用量。"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_test_preparation_comparison import PreparationMeter  # noqa: E402
from forge_build_test_preparation_comparison_v2 import QualifiedPreparationMeter, qualified_execution_window  # noqa: E402

from deerflow.compile.docker_runtime import RuntimeConfig  # noqa: E402


def test_generic_dependency_permissions_match_reference():
    import forge_build_prepared_arm as prepared

    with qualified_execution_window((datetime.now(UTC) + timedelta(hours=2)).isoformat()):
        runtime = prepared.CompileDockerRuntime(manager=object(), config=RuntimeConfig())
        assert runtime.config.network == "compile_network_wwf_v1"
        flags = runtime._parallel_policy_flags(SimpleNamespace(parallel_jobs=2))
        assert "--user" not in flags and "--cpus" in flags


def test_cancelled_started_request_keeps_unknown_reservation(monkeypatch):
    value = object.__new__(QualifiedPreparationMeter)
    value._request_sequence = 8
    value.known_usage_requests = set(range(1, 8))
    value.unknown_usage_requests = set()

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(PreparationMeter, "wrap_model_call", interrupted)
    with pytest.raises(KeyboardInterrupt):
        value.wrap_model_call(None, None)
    assert value.unknown_usage_requests == {8}
