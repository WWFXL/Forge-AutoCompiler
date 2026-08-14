from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "forge_verifier_repair_canary_amendment_result.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-repair-pilot-canary-amendment.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


result = _load_module("forge_verifier_repair_canary_amendment_result_test", SCRIPT_PATH)


def test_result_adapter_uses_runtime_parent_without_changing_frozen_protocol(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    report = result.build_report(manifest, tmp_path)

    assert report["benchmark_id"] == "forge-verifier-driven-repair-pilot-canary-amendment"
    assert report["collection"]["observed_slots"] == 0
    assert report["result_adapter_version"] == result.RESULT_VERSION
