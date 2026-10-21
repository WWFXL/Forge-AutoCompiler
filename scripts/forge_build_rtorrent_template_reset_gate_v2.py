#!/usr/bin/env python3
"""宿主用户下显式Git全局配置的实际模板重置资格v2；旧v1保持。"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]
import forge_build_rtorrent_arm as arm_module  # noqa: E402
import forge_build_rtorrent_template_gate as original_gate  # noqa: E402
from forge_build_rtorrent_reset_gate import reset_boundary, reset_recovery  # noqa: E402
from forge_typed_evidence import audit, seal, write_json  # noqa: E402

from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

IDENTITY = "cpp-build-rtorrent-actual-template-reset-gate-v2"


BaseRuntime = arm_module.CompileDockerRuntime


class HostIdentityRuntime(BaseRuntime):
    @staticmethod
    def _parallel_policy_flags(session):
        # compile和replay均调用同一扩展点，避免root生成的0600文件不可审计。
        return [*BaseRuntime._parallel_policy_flags(session), "--user", f"{os.getuid()}:{os.getgid()}", "--env", "GIT_CONFIG_GLOBAL=/tmp/forge-global.gitconfig"]


def validate(spec):
    if spec["identity"] != IDENTITY:
        raise PlanContractError("不是独立实际模板重置身份")
    failed = spec["failed_runtime_parent"]
    if audit(Path(failed["root"]))["inventory_canonical_sha256"] != failed["inventory_sha256"]:
        raise PlanContractError("失败运行时父证据变化")
    parent = Path(spec["reference_evidence"]["root"])
    original = json.loads((parent / "protocol.json").read_text())
    boundary = reset_boundary(original["file_boundary"])
    if spec["project"]["file_boundary"] != boundary.model_dump(mode="json") or spec["recovery_actions"] != reset_recovery(spec["reference"], boundary):
        raise PlanContractError("原40输出重置/脚本恢复变化")
    reset = Path(spec["reset_evidence"]["root"])
    if audit(reset)["inventory_canonical_sha256"] != spec["reset_evidence"]["inventory_sha256"] or not json.loads((reset / "result.json").read_text())["qualified"]:
        raise PlanContractError("生成顺序恢复资格变化")
    base = copy.deepcopy(spec)
    base["identity"] = original_gate.IDENTITY
    base["project"]["file_boundary"] = original_gate.task_boundary(original["file_boundary"]).model_dump(mode="json")
    base["recovery_actions"] = original_gate.recovery_actions(base["reference"])
    original_gate.validate(base)


def run_slot(spec, folder):
    with patch.object(arm_module, "CompileDockerRuntime", HostIdentityRuntime), patch.dict(os.environ, {"FORGE_HOST_UID": str(os.getuid()), "FORGE_HOST_GID": str(os.getgid())}):
        return original_gate.run_slot(spec, folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    spec = json.loads(args.protocol.read_text())
    validate(spec)
    before_deadline(spec["deadline_utc"], spec["reserve_seconds"])
    if args.validate_only:
        print(json.dumps(dict(valid=True, provider_calls=0)))
        return 0
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", spec)
    write_json(root / "execution.json", dict(release=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), provider_calls=0, runtime_user=f"{os.getuid()}:{os.getgid()}"))
    rows, reason = [], "initialization_not_completed"
    try:
        folder = root / "slot-1"
        folder.mkdir()
        row = {**run_slot(spec, folder), **spec["schedule"][0]}
        rows.append(row)
        reason = None if row["strict_completed"] else "qualification_failed"
        print(json.dumps(dict(strict=row["strict_completed"], error=row.get("error_message")), ensure_ascii=False), flush=True)
    finally:
        write_json(
            root / "result.json", dict(identity=IDENTITY, kind="zero_provider_actual_template_reset_qualification", provider_calls=0, credentials_read=False, rows=rows, unobserved_schedule=spec["schedule"][len(rows) :], stop_reason=reason)
        )
        print(json.dumps(seal(root, spec, ROOT)), flush=True)
    return 0 if rows and rows[0]["strict_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
