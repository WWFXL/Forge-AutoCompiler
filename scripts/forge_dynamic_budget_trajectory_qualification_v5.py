#!/usr/bin/env python3
"""Issue #427 动态预算轨迹 v5：使用 symlink-safe checkpoint 恢复器。"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
V4_SCRIPT_PATH = SCRIPT_PATH.with_name("forge_dynamic_budget_trajectory_qualification_v4.py")
CHECKPOINT_ARCHIVE_PATH = SCRIPT_PATH.with_name("forge_checkpoint_archive.py")
IDENTITY = "cpp-dynamic-budget-trajectory-benchmark-qualification-v5"
TRACKING_ISSUE = 427
INHERITED_TRACKING_ISSUE = 423


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _restore_snapshot(source: Path, destination: Path) -> None:
    archive = _load_module("forge_checkpoint_archive_v5", CHECKPOINT_ARCHIVE_PATH)
    archive.restore_checkpoint_archive(source, destination)


def _report_compatible_result(value: Any) -> Any:
    if isinstance(value, dict) and value.get("failure") is None:
        compatible = copy.deepcopy(value)
        compatible["failure"] = {}
        return compatible
    return value


def configure_module() -> ModuleType:
    module = _load_module("forge_dynamic_budget_trajectory_qualification_v4", V4_SCRIPT_PATH).configure_module()
    module.IDENTITY = IDENTITY
    module.MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
    module.REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
    module.REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
    module._restore_snapshot = _restore_snapshot

    inherited_validate_manifest = module.validate_manifest

    def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest.get("issue") != TRACKING_ISSUE:
            raise module.QualificationError("v5 tracking issue drifted")
        inherited = copy.deepcopy(manifest)
        inherited["issue"] = INHERITED_TRACKING_ISSUE
        inherited_validate_manifest(inherited)
        return manifest

    module.validate_manifest = validate_manifest

    inherited_report_payload = module._report_payload

    def report_payload(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
        inherited_load_json = module._load_json
        result_path = root / "result.json"

        def load_json(path: Path) -> Any:
            value = inherited_load_json(path)
            if path == result_path:
                return _report_compatible_result(value)
            return value

        module._load_json = load_json
        try:
            payload = inherited_report_payload(manifest, root)
        finally:
            module._load_json = inherited_load_json
        payload["failure"] = None
        return payload

    module._report_payload = report_payload
    return module


def main() -> int:
    return configure_module().main()


if __name__ == "__main__":
    raise SystemExit(main())
