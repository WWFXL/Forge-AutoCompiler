"""独立开发接管资格保持原公共条件且不能取得全比较准入。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_full_strategy_fallback_gate import IDENTITY, REPO_ROOT, qualify_protocol  # noqa: E402


def test_single_case_keeps_original_resources_and_never_grants_live_admission():
    path = REPO_ROOT / "benchmarks/manifests/cpp-build-full-strategy-runtime-v1.json"
    parent = json.loads(path.read_text())
    child = qualify_protocol(parent, path)
    assert child["identity"] == IDENTITY and child["identity"] != parent["identity"]
    assert child["provider_calls"] == 0 and child["full_comparison_admission_permitted"] is False
    assert child["gate_schedule"] == [parent["gate_schedule"][-1]]
    for key in ("runtime", "provider", "deadline_utc", "gate_projects", "projects", "schedule", "authorization"):
        assert child[key] == parent[key]
    assert all(child["components"][key] == value for key, value in parent["components"].items())
