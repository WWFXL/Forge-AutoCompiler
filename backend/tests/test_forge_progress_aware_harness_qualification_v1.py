from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from langchain_core.messages import HumanMessage

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_progress_aware_harness_qualification_v1.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_progress_aware_harness_qualification_v1_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _progress_message(payload: dict) -> HumanMessage:
    return HumanMessage(content=("<authoritative_compile_progress>\n" + json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n</authoritative_compile_progress>"))


def test_manifest_and_plan_are_zero_provider_and_create_once() -> None:
    module = _load_module()
    manifest = module._manifest()
    manifest["components"] = {relative: module._file_sha256(REPO_ROOT / relative) for relative in module.COMPONENT_PATHS}
    module.validate_manifest(manifest)

    planned = module.plan(manifest)

    assert manifest["authorization"]["formal_attempts"] == 1
    assert planned["provider_requests"] == 0
    assert planned["credential_reads"] == 0
    assert planned["scripted_actions"] == [
        "configure",
        "build",
        "artifact_stage",
        "blocked_diagnostic_after_ready",
        "submit_from_progress_snapshot",
    ]


def test_script_model_submits_only_from_authoritative_snapshot() -> None:
    module = _load_module()
    task = module._manifest()["task"]
    model = module.ZeroProviderProgressModel(task=task, calls=4)
    target = task["target"]
    progress = {
        "candidate_ready": True,
        "successful_build_command_ids": ["command-build"],
        "recommended_recipe_command_ids": [
            "command-configure",
            "command-build",
            "command-stage",
        ],
        "recommended_target_mapping": {target["target_id"]: target["artifact_path"]},
    }

    generated = model._generate([_progress_message(progress)])
    tool_call = generated.generations[0].message.tool_calls[0]

    assert tool_call["name"] == "submit_candidate_v1"
    assert tool_call["args"]["supporting_command_ids"] == ["command-build"]
    assert tool_call["args"]["recipe_command_ids"] == [
        "command-configure",
        "command-build",
        "command-stage",
    ]
    assert tool_call["args"]["target_mapping"] == {"cxxopts-consumer": "bin/cxxopts-smoke"}


def test_qualification_requires_strict_endpoint_and_budget_conservation() -> None:
    module = _load_module()
    manifest = module._manifest()
    result = {
        "credential_reads": 0,
        "provider_requests": 0,
        "script_model_calls": 5,
        "event_summary": {
            "progress_snapshot_count": 5,
            "effective_compaction_count": 2,
            "ready_guard_rejections": 1,
            "candidate_prefreeze_verified": True,
            "candidate_submit_accepted": True,
        },
        "candidate_submitted": True,
        "strict_success": True,
        "layers": [{"layer": layer, "status": "passed"} for layer in ("S0", "S1", "S2", "S3", "S4", "S5")],
        "usage": {
            "model_requests": 5,
            "tool_calls": 5,
            "commands": 3,
            "agent_steps": 10,
        },
        "cleanup_succeeded": True,
        "managed_containers_after_cleanup": [],
        "parent_inventory_before": manifest["parent"]["inventory_canonical_sha256"],
        "parent_inventory_after": manifest["parent"]["inventory_canonical_sha256"],
    }

    passed = module._qualification(result, manifest)
    assert passed["passed"] is True
    assert passed["decision"] == "proceed_to_h0_h1_provider_comparison_design"

    result["usage"]["commands"] = 4
    failed = module._qualification(result, manifest)
    assert failed["passed"] is False
    assert failed["gates"]["budget_accounting"] is False
    assert failed["decision"] == "stop_before_h0_h1_provider_comparison"
