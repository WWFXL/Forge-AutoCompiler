#!/usr/bin/env python3
"""原生完整轮次下的三策略完整构建资格；仅封闭脚本模型，无付费分支。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]

from forge_build_native_round import NativeRoundMeter, run_strategy  # noqa: E402
from forge_build_plan_predicate_gate import fake_model, reference_actions  # noqa: E402
from forge_build_rtorrent_common_gate import schedule  # noqa: E402
from forge_build_rtorrent_gate import tool_gate_model  # noqa: E402
from forge_build_unified_plan import METHODS  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from deerflow.compile.plan_agent_v2 import PlanAgentMeterV2  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

IDENTITY = "cpp-build-native-round-e2e-gate-v1"
WINDOW = ("2026-10-22T02:18:56+00:00", "2026-10-22T05:18:56+00:00")
TASK_KEYS = (
    "project",
    "reference",
    "recovery_actions",
    "exposure_record",
    "original_test_programs",
    "original_test_counts",
    "package_manifest_sha256",
)


class NativeGateModel(FakeMessagesListChatModel):
    """固定且用尽即停；不会循环脚本响应或调用任何Provider。"""

    served: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, *args, **kwargs):
        if self.served >= len(self.responses):
            raise PlanContractError("免费原生门禁固定响应已用尽，不自动重试")
        self.served += 1
        return super()._generate(*args, **kwargs)


def scripted_model(spec, method):
    if method == METHODS[2]:
        original = tool_gate_model(spec["reference"])
    elif method in METHODS[:2]:
        actions = spec["recovery_actions"] if method == METHODS[0] else reference_actions(spec["reference"]).model_dump(mode="json")
        original = fake_model([actions])
    else:
        raise PlanContractError("未知资格策略")
    prelude = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "零费用工程脚本：先只读配置入口，再提交固定资格方案或执行序列。"},
        tool_calls=[dict(name="read_source", args=dict(path="configure.ac", start_line=1), id="native-e2e-read")],
        usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0),
        response_metadata=dict(model_name="scripted-gate"),
    )
    return NativeGateModel(responses=[prelude, *original.responses])


class NativeE2EMeter(NativeRoundMeter):
    """免费真实构建使用有效工程时窗，不采用历史预算fixture。"""

    def _before_request(self):
        if self.accepted_models != ("scripted-gate",) or self.input_tokens or self.output_tokens or self.cost_usd or self.unknown_usage_requests:
            raise PlanContractError("免费门禁仅接纳封闭零用量脚本模型")
        before_deadline(self.deadline, 120)
        return PlanAgentMeterV2._before_request(self)

    def wrap_model_call(self, request, handler):
        if type(request.model) is not NativeGateModel:
            raise PlanContractError("免费端到端入口拒绝非固定脚本模型")
        return super().wrap_model_call(request, handler)

    def capture_response(self, response, request_sequence):
        super().capture_response(response, request_sequence)
        if self.input_tokens or self.output_tokens or self.cost_usd:
            raise PlanContractError("免费门禁响应出现非零用量，保留后停止")


def validate(spec):
    if (spec["identity"], spec["schedule"], spec["provider_calls"], spec["credentials_read"], spec["max_model_cost_usd"], spec["paid_authorization_qualified"]) != (IDENTITY, schedule(), 0, False, 0, False):
        raise PlanContractError("新原生端到端身份、分母或免费边界不符")
    if (spec["started_window_utc"], spec["deadline_utc"]) != WINDOW or spec["reserve_seconds"] != 2700 or spec["cleanup_timeout_seconds"] != 120:
        raise PlanContractError("独立免费工程时窗或预留变化")
    parent = Path(spec["parent_e2e"]["root"])
    if audit(parent)["inventory_canonical_sha256"] != spec["parent_e2e"]["inventory_sha256"]:
        raise PlanContractError("原完整共同资格证据变化")
    original = json.loads((parent / "protocol.json").read_text())
    result = json.loads((parent / "result.json").read_text())
    if len(result["rows"]) != 3 or result["unobserved_schedule"] or not all(r["strict_completed"] for r in result["rows"]):
        raise PlanContractError("参考共同三槽未闭合")
    if any(spec[key] != original[key] for key in TASK_KEYS):
        raise PlanContractError("完整原任务、脚本、测试、恢复或文件边界变化")
    gate = spec["native_material_gate"]
    material = Path(gate["root"])
    independent = Path(gate["independent_audit_path"])
    qualified = json.loads((material / "result.json").read_text())
    receipt = json.loads(independent.read_text())
    if audit(material)["inventory_canonical_sha256"] != gate["inventory_sha256"] or digest(independent) != gate["independent_audit_sha256"]:
        raise PlanContractError("原生材料资格或独立审计变化")
    if not qualified["qualified"] or not receipt["valid"] or receipt["cases"] != 55 or receipt["negative_cases"] != 3 or receipt["provider_calls"] != 0:
        raise PlanContractError("原生材料完整资格未通过")
    old_components = json.loads((material / "protocol.json").read_text())["components"]
    if any(spec["components"].get(k) != v for k, v in old_components.items()):
        raise PlanContractError("旧冻结组件被修改")
    if digest(Path(spec["project"]["source_archive"])) != spec["project"]["task"]["source_archive_sha256"]:
        raise PlanContractError("原源码归档变化")
    for name, expected in spec["components"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != expected:
            raise PlanContractError("新冻结组件变化：" + name)


def run_slot(spec, folder, slot, *, executor=run_strategy):
    started = time.monotonic()
    row = executor(
        method=slot["method"],
        item=spec["project"],
        protocol=spec,
        root=folder,
        model=scripted_model(spec, slot["method"]),
        meter_factory=NativeE2EMeter,
        qualification_reference=spec["reference"],
    )
    return {**row, **slot, "arm_total_wall_seconds": time.monotonic() - started}


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
        print(json.dumps(dict(valid=True, slots=3, provider_calls=0, paid_authorization_qualified=False)))
        return 0
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", spec)
    write_json(root / "execution.json", dict(release=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), provider_calls=0, paid_authorization_qualified=False))
    rows, reason = [], "initialization_not_completed"
    try:
        for i, slot in enumerate(spec["schedule"], 1):
            before_deadline(spec["deadline_utc"], spec["reserve_seconds"])
            folder = root / f"slot-{i}"
            folder.mkdir()
            row = run_slot(spec, folder, slot)
            rows.append(row)
            write_json(root / f"progress-{i}.json", row)
            print(json.dumps(dict(slot=i, method=slot["method"], strict=row["strict_completed"], error=row.get("error_message")), ensure_ascii=False), flush=True)
            usage = row["agent_usage"]
            if not row["strict_completed"] or not row["cleanup"]["succeeded"] or usage["recorded_tokens"] or usage["unknown_usage_requests"] or usage["model_requests"] != 2:
                reason = "qualification_failed"
                break
        else:
            reason = None
    except BaseException as exc:
        reason = type(exc).__name__
        raise
    finally:
        write_json(
            root / "result.json",
            dict(
                identity=IDENTITY, kind="zero_provider_native_e2e_qualification", provider_calls=0, credentials_read=False, paid_authorization_qualified=False, rows=rows, unobserved_schedule=spec["schedule"][len(rows) :], stop_reason=reason
            ),
        )
        print(json.dumps(seal(root, spec, ROOT)), flush=True)
    return 0 if reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
