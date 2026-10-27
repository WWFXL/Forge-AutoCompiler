#!/usr/bin/env python3
"""复用现有完整任务与恢复消融，以Flash独立采集论文结果。"""

from __future__ import annotations

import argparse
import copy
import signal
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_library_comparison_v2 as comparison
import forge_build_recovery_ablation as recovery

base, bounded = comparison.base, comparison.bounded
ROOT = base.ROOT
PARENTS = {
    "comparison": "cpp-build-library-strategy-comparison-v2",
    "recovery": "cpp-build-tool-recovery-ablation-v1",
}
IDENTITIES = {
    "comparison": "cpp-build-library-strategy-comparison-flash-v1",
    "recovery": "cpp-build-tool-recovery-ablation-flash-v1",
}
PROVIDER = {
    **base.PROVIDER,
    "model": "deepseek-flash",
    "accepted_response_models": ["DeepSeek-V4.1-Flash-1017", "deepseek-flash"],
}
PRICING = {
    "input_per_million_usd": "0.30",
    "output_per_million_usd": "1.20",
    "basis": "2026-10-27官方高峰、全部输入按缓存未命中估费；不是账单",
    "source": "https://api-docs.deepseek.com/quick_start/pricing",
}
PREREGISTRATION = "benchmarks/preregistrations/cpp-build-flash-paper-experiments-v1.md"


class FlashMeter(bounded.previous.QualifiedPreparationMeter):
    """沿用消息、请求、Token及恢复边界，仅使用本轮Flash价格。"""

    def capture_response(self, response, request_sequence):
        try:
            return super().capture_response(response, request_sequence)
        finally:
            # 父类先保存原响应用量；身份不符、截断等异常也不得漏计。
            self.cost_usd = float(
                (
                    Decimal(self.input_tokens)
                    * Decimal(PRICING["input_per_million_usd"])
                    + Decimal(self.output_tokens)
                    * Decimal(PRICING["output_per_million_usd"])
                )
                / 1_000_000
            )


def candidate_for(kind):
    parent_path = ROOT / "benchmarks/manifests" / (PARENTS[kind] + ".json")
    parent = base.load(parent_path)
    candidate = copy.deepcopy(parent)
    candidate.update(
        identity=IDENTITIES[kind],
        issue=626,
        provider=PROVIDER,
        pricing=PRICING,
        kind="complete_library_strategy_comparison_flash"
        if kind == "comparison"
        else "paired_tool_recovery_ablation_flash",
        flash_parent_manifest=dict(
            path=str(parent_path.relative_to(ROOT)), sha256=base.digest(parent_path)
        ),
        launch_state="new_identity_requires_current_authorization",
        interpretation_boundary="当前Flash条件下的已见任务结果；不与旧Pro批次合并估计效果，不作为模型能力比较。",
    )
    for name in ("scripts/forge_build_flash_paper_experiments.py", PREREGISTRATION):
        candidate["components"][name] = base.digest(ROOT / name)
    return candidate


def validate(candidate, kind):
    if candidate != candidate_for(kind):
        raise base.PlanContractError("Flash候选超出已固定模型/价格变更或原任务义务变化")
    for name, expected in candidate["components"].items():
        if base.digest(ROOT / name) != expected:
            raise base.PlanContractError("运行组件变化：" + name)
    for item in candidate["projects"]:
        if (
            base.digest(Path(item["source_archive"]))
            != item["task"]["source_archive_sha256"]
        ):
            raise base.PlanContractError("固定源码归档变化")
        base.PlanTask.model_validate(item["task"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--kind", required=True, choices=PARENTS)
    parser.add_argument("--freeze-only", action="store_true")
    args, remaining = parser.parse_known_args()
    if args.freeze_only:
        candidate = candidate_for(args.kind)
        path = ROOT / "benchmarks/manifests" / (IDENTITIES[args.kind] + ".json")
        base.write_json(path, candidate)
        validate(candidate, args.kind)
        print(path)
        return 0
    signal.signal(signal.SIGINT, bounded.request_stop)
    selected_runner = (
        comparison.previous.replication.run_slot
        if args.kind == "comparison"
        else recovery.run_slot
    )
    with (
        patch.object(sys, "argv", [sys.argv[0], *remaining]),
        patch.object(base, "PROVIDER", PROVIDER),
        patch.object(
            base, "validate", lambda candidate: validate(candidate, args.kind)
        ),
        patch.object(base, "execution_window", bounded.execution_window),
        patch.object(base, "PreparationMeter", FlashMeter),
        patch.object(base, "execute", bounded.execute),
        patch.object(base, "run_slot", selected_runner),
    ):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
