#!/usr/bin/env python3
"""执行修复报告字段后的混合链路零 Provider Docker 资格 v2。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_hybrid_workflow_qualification as v1  # noqa: E402

IDENTITY = "cpp-jev-hybrid-workflow-qualification-v2"
v1.IDENTITY = IDENTITY
v1.MANIFEST_PATH = v1.REPO_ROOT / "benchmarks" / "manifests" / f"{IDENTITY}.json"
v1.REPORT_JSON_PATH = v1.REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.json"
v1.REPORT_MARKDOWN_PATH = v1.REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.md"
v1.FAILURE_JSON_PATH = v1.REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}-failure.json"
v1.FAILURE_MARKDOWN_PATH = v1.REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}-failure.md"


class CaseHarness(v1.CaseHarness):
    """保持 v1 执行合同，只修复 replay 状态的取证字段。"""

    def cleanup(self, *, failed: bool) -> dict[str, Any]:
        if self.session is None:
            return {"succeeded": True, "removed": True, "status": "not_created"}
        current = self._current()
        finalized, cleanup = v1.cleanup_and_finalize_compile_session_impl(
            session=current,
            interrupted_status="failed" if failed and current.status != "verified" else None,
            error="Hybrid workflow qualification failed." if failed else None,
        )
        latest_replay_status = finalized.replay_attempts[-1].status if finalized.replay_attempts else None
        return {
            "succeeded": cleanup.succeeded,
            "removed": cleanup.removed,
            "status": finalized.status,
            "session_id": finalized.session_id,
            "thread_id": finalized.thread_id,
            "session_path": str(Path(finalized.metadata_path).relative_to(v1.REPO_ROOT)),
            "replay_status": latest_replay_status,
        }


v1.CaseHarness = CaseHarness


if __name__ == "__main__":
    raise SystemExit(v1.main())
