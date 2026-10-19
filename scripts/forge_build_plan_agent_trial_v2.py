#!/usr/bin/env python3
"""v1 停止后的独立接线修复试运行；新授权、全新目录，保留 v1 原始失败。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "backend/packages/harness"))

import forge_build_plan_agent_trial as v1  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger, trial_budget  # noqa: E402
from deerflow.compile.plan_agent_v2 import PlanAgentMeterV2, PlanThinkingDeepSeek  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_inputs(protocol_path, archive_path, parent_root, authorization_path=None):
    protocol = json.loads(protocol_path.read_text())
    if protocol["identity"] != "cpp-build-plan-agent-trial-v2":
        raise PlanContractError("v2 身份不符")
    base_path = REPO_ROOT / "benchmarks/manifests/cpp-build-plan-agent-trial-v1-candidate.json"
    base = v1.validate_inputs(base_path, archive_path)
    if sha(base_path) != protocol["base_protocol_sha256"] or protocol["task"] != base["task"] or protocol["provider"] != base["provider"]:
        raise PlanContractError("v2 不得变更任务、模型或 v1 来源")
    limits = replace(trial_budget(), max_model_requests=11, max_recorded_tokens=100_000)
    if protocol["agent_budget"] != asdict(limits) or protocol["aggregate_cost_ceiling_usd"] != 2 or protocol["parent_token_reservation"] != 50_000:
        raise PlanContractError("不得扩大跨身份累计预算")
    seal = json.loads((parent_root / "seal.json").read_text())
    if sha(parent_root / "seal.json") != protocol["parent_seal_sha256"] or seal["unknown_usage_requests"] != 1 or seal["provider_attempted_requests"] != 1:
        raise PlanContractError("v1 停止证据不匹配")
    rows = json.loads((parent_root / "inventory.json").read_text())
    canonical = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if canonical != seal["inventory_canonical_sha256"]:
        raise PlanContractError("v1 inventory 已变化")
    for row in rows:
        if sha(parent_root / row["path"]) != row["sha256"]:
            raise PlanContractError("v1 原始证据已变化")
    for name, digest in protocol["components"].items():
        path = (REPO_ROOT / name).resolve()
        if not path.is_relative_to(REPO_ROOT) or sha(path) != digest:
            raise PlanContractError("v2 运行代码或协议已变化")
    if authorization_path is not None:
        authorization = json.loads(authorization_path.read_text())
        if authorization != {"identity": protocol["identity"], "protocol_sha256": sha(protocol_path), "decision": "approve_trial", "max_estimated_cost_usd": 2}:
            raise PlanContractError("v2 尚无匹配授权")
    return protocol


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--parent-evidence", type=Path, required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = validate_inputs(args.protocol, args.source_archive, args.parent_evidence, args.authorization)
    if args.validate_only:
        print(json.dumps({"identity": protocol["identity"], "valid": True, "provider_calls": 0}))
        return 0
    if args.authorization is None or args.output_root is None:
        parser.error("v2 需要独立明确授权和全新输出目录")
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    (root / "authorization.json").write_bytes(args.authorization.read_bytes())
    ledger = PlanAgentLedger(root / "agent")
    meter = PlanAgentMeterV2(ledger, accepted_models=tuple(protocol["provider"]["accepted_response_models"]), budget=replace(trial_budget(), max_model_requests=11, max_recorded_tokens=100_000))
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        (root / "result.json").write_text(json.dumps({"status": "stopped", "error_class": "MissingCredential", "agent_usage": meter.summary()}) + "\n")
        return 1
    model = PlanThinkingDeepSeek(model="deepseek-v4-pro", api_key=api_key, base_url="https://api.deepseek.com", max_tokens=8192, max_retries=0, timeout=120, extra_body={"thinking": {"type": "enabled"}})
    result = v1.execute_trial(protocol=protocol, archive_path=args.source_archive, root=root, model=model, meter=meter)
    print(json.dumps({"status": result["status"], "agent_usage": result["agent_usage"]}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
