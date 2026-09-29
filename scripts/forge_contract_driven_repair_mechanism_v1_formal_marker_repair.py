#!/usr/bin/env python3
"""为后续独立 identity 修复 formal runner marker 更新调用合同。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_contract_driven_repair_mechanism_v1_formal_runner as frozen_runner  # noqa: E402

FROZEN_RUNNER_PATH = (
    SCRIPT_ROOT / "forge_contract_driven_repair_mechanism_v1_formal_runner.py"
)
FROZEN_RUNNER_SHA256 = (
    "5bb1797d2a3a5a8c700ba8da5677b195d0c0db969498521df878f669c815e358"
)
REPAIR_SCHEMA_VERSION = "forge-contract-repair-formal-marker-repair-1.0.0"


class MarkerRepairError(RuntimeError):
    """Marker repair 绑定或调用合同无效。"""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_frozen_runner() -> None:
    if _file_sha256(FROZEN_RUNNER_PATH) != FROZEN_RUNNER_SHA256:
        raise MarkerRepairError("冻结 formal runner SHA-256 漂移")


_verify_frozen_runner()
_frozen_update_claimed_marker = frozen_runner._update_claimed_marker


def update_claimed_marker(path: Path, **updates: Any) -> dict[str, Any]:
    """把 frozen call sites 的 keyword updates 适配为原 helper 的 mapping。"""

    if not updates:
        raise MarkerRepairError("marker update 不得为空")
    return _frozen_update_claimed_marker(path, updates)


def install() -> None:
    """只在显式导入本模块的后续 runner 进程内安装 repair。"""

    frozen_runner._update_claimed_marker = update_claimed_marker


install()

# 后续独立 execution identity 只能显式导入这些入口；本模块不提供 batch CLI。
execute_arm = frozen_runner.execute_arm
execute_batch = frozen_runner.execute_batch
audit_batch = frozen_runner.audit_batch
build_report = frozen_runner.build_report


def validate() -> dict[str, Any]:
    _verify_frozen_runner()
    if frozen_runner._update_claimed_marker is not update_claimed_marker:
        raise MarkerRepairError("marker repair 未安装")
    return {
        "schema_version": REPAIR_SCHEMA_VERSION,
        "status": "marker_update_contract_repaired_for_future_identity",
        "frozen_runner_sha256": FROZEN_RUNNER_SHA256,
        "provider_calls": 0,
        "formal_attempts": 0,
        "formal_evidence_writes": 0,
    }


def main() -> int:
    print(json.dumps(validate(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
