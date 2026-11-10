#!/usr/bin/env python3
"""只读回放ggmorse原失败交接及工具响应，检验下一请求能否装入上下文。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from forge_simple_system import ROOT
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.simple_build_agents import SimpleBuildMeter
from deerflow.compile.simple_build_task import SimpleBuildAction, SimpleBuildPlan, propose_simple


class RecordedReadModel(FakeMessagesListChatModel):
    """仅输出已保存工具调用和脚本结尾；不访问Provider，不循环响应。"""

    position: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, *args, **kwargs):
        if self.position >= len(self.responses):
            raise RuntimeError("上下文回放已达到固定两响应上限")
        self.position += 1
        return super()._generate(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for name in ("slot-25-ggmorse-H0", "slot-26-ggmorse-R1"):
        source = args.historical_root / name
        files = sorted((source / "agent").glob("request-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
        request = json.loads(files[-1].read_text())
        packet = json.loads(request["messages"][0]["content"])
        session = next(source.glob(".compile-sessions/simple-system/*/session.json")).parent
        plan = SimpleBuildPlan.model_validate_json((session / "build-plan" / f"plan-{packet['current_plan']['revision']}.json").read_text())
        raw_path = source / "agent" / files[-1].name.replace("request-", "response-")
        original_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        raw = json.loads(raw_path.read_text())[0]
        # 原响应不改写；副本清零旧用量并标记脚本模型，避免把历史Token计为新增消费。
        reply = AIMessage(**{**raw, "usage_metadata": dict(input_tokens=0, output_tokens=0, total_tokens=0), "response_metadata": dict(model_name="zero-provider-script")})
        fields = set(SimpleBuildAction.model_fields)
        actions = dict(reason="工程上下文回放的脚本终止，不执行此方案", steps=[{k: v for k, v in s.model_dump().items() if k in fields} for s in plan.steps if not s.step_id.startswith("forge-")])
        final = AIMessage(
            content="", tool_calls=[dict(name="SimpleBuildActions", args=actions, id="context-replay-end")], usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0), response_metadata=dict(model_name="zero-provider-script")
        )
        output = args.output / name
        meter = SimpleBuildMeter(PlanAgentLedger(output), accepted_models=("zero-provider-script",), deadline="2099-01-01T00:00:00+00:00", packet=lambda: packet, maximum_cost_usd="0", pricing_by_model={"zero-provider-script": ("0", "0")})
        # 原请求包已经是工作集输出（含目录结果），不能再次当初始文件列表seed。
        meter.packet = lambda: packet
        model = RecordedReadModel(responses=[reply, final])
        propose_simple(model=model, task=plan.task, source_root=session / "workspace/repo", session_root=session, meter=meter, current_plan=plan, handoff=packet["handoff"], revision_validator=lambda _: None)
        sent = json.loads((output / "request-2.json").read_text())
        size = len(json.dumps({k: v for k, v in sent.items() if k != "tools"}, ensure_ascii=False).encode())
        assert size <= 49000 and model.position == 2 and not meter.summary()["unknown_usage_requests"]
        assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == original_sha
        rows.append(
            dict(slot=name, original_response=str(raw_path), original_response_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(), replay_body_bytes=size, scripted_responses=2, provider_calls=0, model_cost_usd=0, plan_execution=False)
        )
    (args.output / "summary.json").write_text(
        json.dumps(
            dict(identity="cpp-build-common-recovery-context-replay-v1", kind="zero_provider_context_only", root=str(ROOT), rows=rows, boundary="仅验证真实旧材料的序列化与容量；不验证Agent新决策、模型服务兼容性或ggmorse构建成功"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
