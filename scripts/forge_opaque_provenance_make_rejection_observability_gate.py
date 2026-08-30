#!/usr/bin/env python3
"""Issue #208 Make runtime-parity 拒绝的 R0 observable 版本层。"""

from __future__ import annotations

from typing import Any

import forge_opaque_provenance_make_runtime_parity_gate as make_parity
import forge_opaque_provenance_rejection_observability_gate as r0

from deerflow.compile.evidence import EvidenceError

OBSERVATION_EVENT = r0.OBSERVATION_EVENT
RejectionObservationRegistry = r0.RejectionObservationRegistry
ObservableRuntimeParityGateError = r0.ObservableRuntimeParityGateError

_MAKE_REJECTIONS = {
    "repair build must be a direct make or gmake invocation": (
        "repair_build_invocation_invalid",
        "repair_build",
    ),
    "repair build directory drifted from the frozen identity": (
        "repair_build_directory_drift",
        "repair_build",
    ),
    "repair build target drifted from the frozen identity": (
        "repair_build_target_drift",
        "repair_build",
    ),
    "repair build jobs drifted from the frozen identity": (
        "repair_build_arguments_invalid",
        "repair_build",
    ),
    "repair build contains non-preregistered arguments": (
        "repair_build_arguments_invalid",
        "repair_build",
    ),
}


def _observable_error(
    exc: make_parity.RuntimeParityGateError,
    *,
    action_hint: str,
) -> ObservableRuntimeParityGateError:
    metadata = _MAKE_REJECTIONS.get(str(exc))
    if metadata is not None:
        return ObservableRuntimeParityGateError(
            str(exc),
            classification=metadata[0],
            action_kind=metadata[1],
        )
    return r0._observable_gate_error(exc, action_hint=action_hint)


class ObservableRuntimeParityToolAdapter(make_parity.RuntimeParityToolAdapter):
    """在不修改 #194 的前提下翻译 Make gate 拒绝。"""

    def run(
        self,
        command: str,
        *,
        timeout_seconds: int = 300,
        workdir: str | None = None,
        command_role: str = "other",
    ) -> Any:
        try:
            return super().run(
                command,
                timeout_seconds=timeout_seconds,
                workdir=workdir,
                command_role=command_role,
            )
        except make_parity.RuntimeParityGateError as exc:
            raise _observable_error(
                exc,
                action_hint=r0._action_hint(command_role),
            ) from exc
        except EvidenceError as exc:
            if str(exc).startswith("Unsupported compile command role:"):
                raise ObservableRuntimeParityGateError(
                    "unsupported compile command role",
                    classification="invalid_command_role",
                    action_kind="command",
                ) from exc
            raise

    def submit(self, supporting_command_id: str | None = None) -> Any:
        try:
            return super().submit(supporting_command_id)
        except make_parity.RuntimeParityGateError as exc:
            raise _observable_error(exc, action_hint="submit") from exc
