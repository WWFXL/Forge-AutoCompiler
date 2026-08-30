"""Issue #214 R3 Make jobs profile 的 opt-in Ubuntu 原生 Docker 门禁。"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DOCKER_ENABLED = os.getenv("FORGE_RUN_OPAQUE_PROVENANCE_R3_MAKE_LIFECYCLE_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_OPAQUE_PROVENANCE_R3_MAKE_LIFECYCLE_DOCKER=1 in WSL Ubuntu",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


gate = _load_module(
    "forge_opaque_provenance_r3_make_lifecycle_gate_docker_adapter",
    SCRIPTS_DIR / "forge_opaque_provenance_r3_make_lifecycle_gate.py",
)
legacy = _load_module(
    "forge_opaque_provenance_make_lifecycle_gate_docker_orchestration",
    REPO_ROOT / gate.LEGACY_DOCKER_TEST_PATH,
)


@pytest.mark.parametrize("profile_id", tuple(gate.PROFILES))
def test_r3_make_jobs_profile_real_lifecycle(
    profile_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate.validate_gate_contract()
    monkeypatch.setattr(legacy, "adapter", gate.build_docker_adapter(profile_id))

    legacy.test_real_make_parent_treatment_replay_and_cleanup(tmp_path, monkeypatch)
