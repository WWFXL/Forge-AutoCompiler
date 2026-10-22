#!/usr/bin/env python3
"""恢复已资格的普通项目依赖权限；独立重采，旧诊断与中断费用完整保留。"""

from __future__ import annotations

import os
import signal
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch

import forge_build_test_preparation_comparison as previous
from deerflow.compile import operations
from deerflow.compile.docker_runtime import CompileDockerRuntime
from deerflow.compile.operation_window import OperationWindow
from deerflow.compile.plan_workflow import PlanContractError

IDENTITY = "cpp-build-test-preparation-comparison-v2"
DEPENDENCY_RUNTIME = dict(
    qualification_authority="original_generic_root_network_reference",
    user="image_default_root",
    network="compile_network_wwf_v1",
    package_manager_install_permitted=True,
    correct_reference_injected=False,
)
ORIGINAL_VALIDATE = previous.validate


def validate(candidate):
    if (
        candidate["identity"] != IDENTITY
        or candidate["dependency_runtime"] != DEPENDENCY_RUNTIME
    ):
        raise PlanContractError("新身份或已资格依赖权限不符")
    ORIGINAL_VALIDATE({**candidate, "identity": previous.COMPARISON})


class QualifiedPreparationMeter(previous.PreparationMeter):
    def __init__(self, *args, **kwargs):
        original = kwargs.pop("packet")
        super().__init__(
            *args,
            packet=lambda: {**original(), "dependency_runtime": DEPENDENCY_RUNTIME},
            **kwargs,
        )
        self.ledger.append("qualified_dependency.policy", **DEPENDENCY_RUNTIME)

    def wrap_model_call(self, request, handler):
        try:
            return super().wrap_model_call(request, handler)
        except BaseException:
            # 取消同样需要为已发但没有完整用量的请求保留费用。
            if (
                self._request_sequence
                and self._request_sequence not in self.known_usage_requests
            ):
                self.unknown_usage_requests.add(self._request_sequence)
            raise


@contextmanager
def qualified_execution_window(deadline):
    window = OperationWindow(deadline)

    class QualifiedRuntime(CompileDockerRuntime):
        def __init__(self, *, manager, config):
            if config.network != DEPENDENCY_RUNTIME["network"]:
                raise PlanContractError("普通项目必须沿原合格网络入口，不另行切换")
            super().__init__(
                manager=manager, config=replace(config, cleanup_timeout_seconds=120)
            )

        def exec(
            self,
            session,
            command,
            workdir=None,
            timeout_seconds=600,
            log_path=None,
            strict_shell=False,
        ):
            bounded = window.command_timeout(timeout_seconds)
            self.manager.log_event(
                session,
                "operation_window.command",
                requested_seconds=timeout_seconds,
                admitted_seconds=bounded,
                deadline_utc=deadline,
            )
            return super().exec(
                session,
                command,
                workdir=workdir,
                timeout_seconds=bounded,
                log_path=log_path,
                strict_shell=strict_shell,
            )

    original_replay = operations.verify_clean_replay_impl

    def replay(**kwargs):
        maximum = (
            kwargs.get("timeout_seconds")
            or operations.get_compile_services().runtime.config.replay_timeout_seconds
        )
        kwargs["timeout_seconds"] = window.replay(maximum)
        return original_replay(**kwargs)

    with (
        patch.object(
            previous.prepared_module, "CompileDockerRuntime", QualifiedRuntime
        ),
        patch.object(operations, "verify_clean_replay_impl", replay),
        patch.dict(
            os.environ,
            {"FORGE_HOST_UID": str(os.getuid()), "FORGE_HOST_GID": str(os.getgid())},
        ),
    ):
        yield


def main():
    def stop(signum, frame):
        raise PlanContractError("operator_or_deadline_stop")

    signal.signal(signal.SIGINT, stop)
    with (
        patch.object(previous, "validate", validate),
        patch.object(previous, "execution_window", qualified_execution_window),
        patch.object(previous, "PreparationMeter", QualifiedPreparationMeter),
    ):
        return previous.main()


if __name__ == "__main__":
    raise SystemExit(main())
