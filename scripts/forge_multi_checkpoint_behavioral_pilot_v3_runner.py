#!/usr/bin/env python3
"""把 v3 冻结 schedule 映射为逐 case 运行计划；本版本禁止真实采集。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
PROTOCOL_PATH = SCRIPT_ROOT / "forge_multi_checkpoint_behavioral_pilot_v3_protocol.py"


class RunnerPlanError(RuntimeError):
    """未授权 runner 收到无效 pair 或真实执行请求。"""


def _load_protocol():
    name = "forge_multi_checkpoint_behavioral_pilot_v3_protocol_runner_dependency"
    spec = importlib.util.spec_from_file_location(name, PROTOCOL_PATH)
    if spec is None or spec.loader is None:
        raise RunnerPlanError("cannot load v3 protocol")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_protocol()
DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST


def _case_payload(case: Any) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "repository_url": case.repository_url,
        "commit_sha": case.commit_sha,
        "language": case.language,
        "build_system": case.build_system,
        "source_subdir": case.source_subdir,
        "build_targets": list(case.build_targets),
        "required_system_packages": list(case.required_system_packages),
        "cmake_arguments": list(case.cmake_arguments),
        "configure_arguments": list(case.configure_arguments),
        "artifact": {
            "build_output_relative_path": case.build_output_relative_path,
            "staged_relative_path": case.staged_relative_path,
            "artifact_type": case.artifact_type,
        },
        "commands": [{"role": role, "command": command} for role, command in case.commands],
    }


def build_pair_plan(manifest: dict[str, Any], pair_id: str, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    protocol.validate_manifest(manifest, repo_root)
    matches = [pair for pair in manifest["schedule"] if pair["pair_id"] == pair_id]
    if len(matches) != 1:
        raise RunnerPlanError(f"unknown pair: {pair_id}")
    pair = matches[0]
    case = protocol.case_definitions(manifest, repo_root)[pair["case_id"]]
    return {
        "pair_id": pair["pair_id"],
        "order": pair["order"],
        "case_pair_index": pair["case_pair_index"],
        "arm_order": pair["arm_order"],
        "case": _case_payload(case),
        "provider": manifest["provider"],
        "continuation": manifest["continuation"],
        "budget": {
            "recorded_tokens_per_arm": manifest["budget"]["recorded_tokens_per_arm"],
            "recorded_tokens_per_pair": manifest["budget"]["recorded_tokens_per_pair"],
        },
        "controlled_fault": manifest["scope"]["controlled_fault"],
        "runner_mode": manifest["execution"]["mode"],
        "provider_calls_authorized": manifest["authorization"]["provider_calls_authorized"],
    }


def build_pilot_plan(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    protocol.verify_frozen_components(manifest, repo_root)
    pairs = [build_pair_plan(manifest, pair["pair_id"], repo_root) for pair in manifest["schedule"]]
    return {
        "schema_version": manifest["schema_version"],
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "authorization": manifest["authorization"],
        "case_source": manifest["case_source"],
        "analysis": manifest["analysis"],
        "pair_count": len(pairs),
        "arm_count": sum(len(pair["arm_order"]) for pair in pairs),
        "maximum_recorded_tokens": manifest["budget"]["stage_maximum_recorded_tokens"],
        "pairs": pairs,
    }


def execute_collection(*_args: Any, **_kwargs: Any) -> None:
    raise RunnerPlanError("v3 protocol freeze does not authorize provider collection")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "plan", "show-pair"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pair-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "show-pair":
        if not args.pair_id:
            raise RunnerPlanError("show-pair requires --pair-id")
        result: Any = build_pair_plan(manifest, args.pair_id)
    else:
        result = build_pilot_plan(manifest)
        if args.command == "validate":
            result = {
                "manifest_sha256": result["manifest_sha256"],
                "pairs": result["pair_count"],
                "arms": result["arm_count"],
                "provider_calls": 0,
                "formal_attempts": 0,
                "model_tokens": 0,
            }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
