#!/usr/bin/env python3
"""用户新授权的 rtorrent canary；旧候选、执行链和失败证据保持只读。"""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import forge_build_rtorrent_canary as previous

from deerflow.compile.plan_workflow import PlanContractError

IDENTITY = "cpp-build-rtorrent-common-canary-v2"
PROVIDER = previous.PROVIDER
# 每个请求同时消耗一个 step。这个技术计数上界严格大于 step 上界，
# 因而不会先于 step 预算限制请求；独立的请求授权上限为 null。
RUNTIME = {**previous.RUNTIME, "max_model_requests": previous.RUNTIME["max_agent_steps"] + 1}
REQUEST_POLICY = dict(independent_request_cap=None, automatic_retry=False, technical_request_ceiling="max_agent_steps + 1; nonbinding")
OLD_VALIDATE = previous.validate


class AuthorizedMeter(previous.CommonStrategyMeter):
    """只取消旧十二请求限制；Token、费用、工具、命令和时限保持。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker.limits = replace(self.tracker.limits, max_model_requests=RUNTIME["max_model_requests"])
        self.ledger.append("authorization.request_policy", **REQUEST_POLICY)


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["runtime"] != RUNTIME or candidate["request_policy"] != REQUEST_POLICY:
        raise PlanContractError("新身份、共同资源或不重试合同变化")
    if candidate["proposed_max_new_provider_cost_usd"] != 10 or candidate["proposed_runtime_hours"] != 4:
        raise PlanContractError("本轮预算和时窗须为10美元、4小时")
    if candidate["parent_candidate_sha256"] != "bcee5cad2a8f7bdc1a928925aa9cb9614665fa13fd5910b2af19e14bada0c4e8":
        raise PlanContractError("父候选身份变化")
    base = copy.deepcopy(candidate)
    base.update(identity="cpp-build-rtorrent-common-canary-v1", runtime=previous.RUNTIME, proposed_max_new_provider_cost_usd=5, proposed_runtime_hours=3)
    # 原校验器依然验证实际任务、三槽门禁、全部组件和源码归档。
    with patch.object(previous, "IDENTITY", base["identity"]), patch.object(previous, "RUNTIME", {**RUNTIME, "max_model_requests": 12}):
        base["runtime"] = previous.RUNTIME
        OLD_VALIDATE(base)


def validate_authorization(candidate_sha, authorization):
    if authorization.get("experiment_identity") != IDENTITY or authorization.get("candidate_sha256") != candidate_sha or authorization.get("user_authorized") is not True:
        raise PlanContractError("需要本轮用户授权与精确候选绑定")
    maximum = Decimal(str(authorization["max_new_provider_cost_usd"]))
    start, end = (datetime.fromisoformat(authorization[k]) for k in ("authorized_at_utc", "deadline_utc"))
    if not maximum.is_finite() or not Decimal(0) < maximum <= Decimal(10):
        raise PlanContractError("本轮新增模型费用最多10美元")
    if authorization.get("max_total_model_requests", "missing") is not None or authorization.get("automatic_retry") is not False:
        raise PlanContractError("用户授权请求次数不限、无自动重试")
    if start.tzinfo is None or end.tzinfo is None or start > datetime.now(UTC) or not 3900 <= (end - start).total_seconds() <= 14400:
        raise PlanContractError("有效授权窗口最多4小时，不能从启动时重新计时")
    previous.before_deadline(authorization["deadline_utc"], 3900)


def main():
    with (
        patch.object(previous, "IDENTITY", IDENTITY),
        patch.object(previous, "RUNTIME", RUNTIME),
        patch.object(previous, "validate", validate),
        patch.object(previous, "validate_authorization", validate_authorization),
        patch.object(previous, "CommonStrategyMeter", AuthorizedMeter),
    ):
        return previous.main()


if __name__ == "__main__":
    raise SystemExit(main())
