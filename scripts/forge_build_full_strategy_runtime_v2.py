#!/usr/bin/env python3
"""区分零Provider资格与真实请求准入；完整裁判及付费3900秒余量不变。"""

from __future__ import annotations

import sys
from decimal import Decimal

import forge_build_full_strategy_runtime as runtime

from deerflow.compile.plan_agent_v2 import PlanAgentMeterV2
from deerflow.compile.plan_cross_system import before_deadline
from deerflow.compile.plan_workflow import PlanContractError

IDENTITY = "cpp-build-full-strategy-runtime-v2"


class QualificationAwareMeter(runtime.StrategyMeter):
    """仅严格scripted-gate且零用量的请求采用工程门禁时限。"""

    def _before_request(self):
        if self.accepted_models != ("scripted-gate",):
            return super()._before_request()
        before_deadline(self.deadline, 120)
        if self.input_tokens or self.output_tokens or Decimal(str(self.cost_usd)) != 0:
            raise PlanContractError("零Provider资格出现非零用量，停止而不放宽准入")
        # 保留12请求、Token和步骤计数；跳过仅用于真实Provider的3900/1800秒预留。
        # 模型由原qualify路径显式构造Fake；响应仍只接受scripted-gate及零用量。
        return PlanAgentMeterV2._before_request(self)


def main():
    if "--qualify" in sys.argv:
        print("零Provider资格须在绝对截止前终止；本轮外层预留120秒清理。", flush=True)
    runtime.IDENTITY = IDENTITY
    runtime.StrategyMeter = QualificationAwareMeter
    return runtime.main()


if __name__ == "__main__":
    raise SystemExit(main())
