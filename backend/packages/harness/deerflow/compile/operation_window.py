"""按操作检查剩余时间；请求准入不承担整条构建链的最坏耗时。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from deerflow.compile.plan_workflow import PlanContractError


@dataclass(frozen=True)
class OperationWindow:
    deadline: str
    request_reserve_seconds: int = 600
    cleanup_reserve_seconds: int = 300

    def remaining(self, now: datetime | None = None) -> float:
        end = datetime.fromisoformat(self.deadline)
        if end.tzinfo is None:
            raise PlanContractError("运行截止必须带时区")
        return (end - (now or datetime.now(UTC))).total_seconds()

    def admit(self, operation: str, required_seconds: int, *, now: datetime | None = None) -> None:
        if required_seconds <= 0 or self.remaining(now) < required_seconds:
            raise PlanContractError(f"operation_window:{operation}剩余时间不足")

    def request(self, *, now: datetime | None = None) -> None:
        self.admit("model_request", self.request_reserve_seconds, now=now)

    def command_timeout(self, maximum: int, *, now: datetime | None = None) -> int:
        seconds = min(maximum, int(self.remaining(now)) - self.cleanup_reserve_seconds)
        if seconds <= 0:
            raise PlanContractError("operation_window:command保留清理时间")
        return seconds

    def replay(self, maximum: int, *, now: datetime | None = None) -> int:
        # 重放要有完整执行预算，不能缩短后把失败误称产物不可复现。
        self.admit("clean_replay", maximum + self.cleanup_reserve_seconds, now=now)
        return maximum
