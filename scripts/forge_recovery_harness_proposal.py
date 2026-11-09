#!/usr/bin/env python3
"""一次历史恢复轨迹提案；本入口没有比较运行或论文更新命令。"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import forge_simple_comparison as shared
from forge_build_simple_task import save
from forge_typed_evidence import digest
from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.recovery_harness import RECOVERY_OPTIMIZER_PROMPT, RecoveryHarness, RecoveryHarnessProposal
from deerflow.compile.simple_build_task import SIMPLE_PROMPT

ROOT = shared.ROOT
IDENTITY = "cpp-build-offline-recovery-harness-proposal-v1"
EXPIRES = "2026-11-09T19:05:18+00:00"
SOURCES = (
    Path("/home/yiwei/.codex/outputs/forge-main-system-comparison-flash-v1"),
    Path("/home/yiwei/.codex/outputs/forge-offline-harness-round2-flash-v1/comparison"),
)


def load(path):
    return json.loads(path.read_text())


def excerpt(value, limit=1800):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return dict(text=text[:limit], truncated=len(text) > limit, original_characters=len(text))


def public_handoff(packet):
    """保留真实交接而不发送系统清理的超长受保护文件列表。"""
    handoff = packet.get("handoff", {})
    return dict(
        task=packet.get("task"),
        current_plan=packet.get("current_plan"),
        handoff={
            key: [{k: excerpt(v, 3000) if k in {"command", "output_tail"} else v for k, v in row.items() if k in {"command_id", "role", "command", "workdir", "exit_code", "output_tail", "log_sha256"}} for row in value]
            if key == "recent_commands"
            else value
            for key, value in handoff.items()
            if key in {"reason", "failed_step_id", "failed_role", "configuration", "recent_commands", "handoff_id", "plan_sha256"}
        },
    )


def corpus():
    episodes = []
    for batch in SOURCES:
        for folder in sorted(batch.glob("slot-*")):
            path = folder / "agent/events.jsonl"
            if not path.exists():
                continue
            events = [json.loads(line) for line in path.read_text().splitlines()]
            starts = [i for i, e in enumerate(events) if e["event"] == "agent.started"]
            for pos, start in enumerate(starts):
                entry = events[start]
                if not entry.get("recovery"):
                    continue
                end = starts[pos + 1] if pos + 1 < len(starts) else len(events)
                segment = events[start:end]
                seq = next(e["request_sequence"] for e in segment if e["event"] == "model.request_started")
                request_path = folder / "agent" / f"request-{seq}.json"
                request = load(request_path)
                packet = json.loads(request["messages"][0]["content"])
                revision = entry["revision"]
                prefix = f"{batch.parent.name if batch.name == 'comparison' else batch.name}:{folder.name}:r{revision}"
                evidence = [dict(evidence_id=prefix + ":handoff", kind="handoff", content=public_handoff(packet), source_path=str(request_path), source_sha256=digest(request_path))]
                tool_results = [(start + j + 1, e) for j, e in enumerate(segment) if e["event"] == "tool.completed"]
                selected = tool_results if len(tool_results) <= 8 else tool_results[:4] + tool_results[-4:]
                calls = [dict(tool=e["name"], arguments=e.get("args", {})) for e in segment if e["event"] == "tool.started"]
                frequencies = Counter(json.dumps(c, ensure_ascii=False, sort_keys=True) for c in calls)
                for index, e in selected:
                    evidence.append(dict(evidence_id=prefix + f":event-{index}", kind="tool_feedback", tool=e["name"], content=excerpt(e.get("result", {}).get("content", ""), 1600), source_path=str(path), source_sha256=digest(path)))
                action_path = folder / "agent" / f"simple-actions-{revision}.json"
                if action_path.exists():
                    evidence.append(dict(evidence_id=prefix + ":actions", kind="revised_actions", content=load(action_path), source_path=str(action_path), source_sha256=digest(action_path)))
                result_path = folder / "result.json"
                result = load(result_path)
                evidence.append(
                    dict(
                        evidence_id=prefix + ":outcome",
                        kind="arm_outcome_not_per_recovery_success",
                        content={k: result.get(k) for k in ("status", "layers", "timings", "agent_usage", "cleanup")},
                        source_path=str(result_path),
                        source_sha256=digest(result_path),
                    )
                )
                episodes.append(
                    dict(
                        trajectory_id=prefix,
                        project=packet["task"]["repository_url"].rsplit("/", 1)[-1],
                        repository_url=packet["task"]["repository_url"],
                        role="optimizer_development_recovery",
                        revision=revision,
                        requests=sum(e["event"] == "model.request_started" for e in segment),
                        tool_calls=len(calls),
                        read_frequencies=[dict(**json.loads(key), count=count) for key, count in frequencies.most_common()],
                        omitted_tool_feedback=len(tool_results) - len(selected),
                        evidence=evidence,
                    )
                )
    # 正常成功仅作行为边界参照，不计入恢复次数；按项目定位避免依赖旧槽顺序。
    for project in ("yaml-cpp", "libhydrogen", "libsodium"):
        folder = next(SOURCES[1].glob(f"slot-*-{project}-H0"))
        path = folder / "result.json"
        result = load(path)
        action = folder / "agent/simple-actions-1.json"
        prefix = f"control:{project}"
        episodes.append(
            dict(
                trajectory_id=prefix,
                repository_url=load(folder / "common-public-task.json")["repository_url"],
                role="normal_success_boundary",
                evidence=[
                    dict(evidence_id=prefix + ":actions", kind="initial_actions", content=load(action), source_path=str(action), source_sha256=digest(action)),
                    dict(evidence_id=prefix + ":outcome", kind="arm_outcome", content={k: result.get(k) for k in ("status", "layers", "agent_usage")}, source_path=str(path), source_sha256=digest(path)),
                ],
            )
        )
    return dict(
        format="offline-recovery-corpus-v1",
        episodes=episodes,
        holdout=False,
        selection="E50/E52全部可定位自然恢复，另三正常成功边界；不按成功或低费用筛恢复，不估异常发生率。",
        historical_context="旧运行底座不完全相同；共同观察、fse轻量验证、成功依赖保留已修复，不可计候选收益。结局是整槽观察，不能把后续成功视为每次局部恢复均成功。",
        historical_cost_is_new_charge=False,
    )


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    material = corpus()
    baseline = RecoveryHarness(name="H0_recovery", base_prompt_sha256=_digest(SIMPLE_PROMPT))
    save(output / "corpus.json", material)
    save(output / "baseline.json", baseline.model_dump(mode="json"))
    packet = dict(base_prompt=SIMPLE_PROMPT, baseline=baseline.model_dump(mode="json"), corpus=material)
    request = dict(system_prompt=RECOVERY_OPTIMIZER_PROMPT, packet=packet)
    size = len(json.dumps(request, ensure_ascii=False).encode())
    if size > 400000:
        raise PlanContractError("提案材料超过预留，禁止Provider调用")
    save(output / "request.json", request)
    scope = dict(
        identity=IDENTITY,
        issue=709,
        phase="proposal_only_await_user_review",
        started_at="2026-11-09T15:05:18+00:00",
        deadline=EXPIRES,
        maximum_cost_usd="1.00",
        maximum_requests=1,
        maximum_output_tokens=8192,
        request_bytes=size,
        requested_model="gpt-6-astra",
        accepted_response_models=["gpt-5.6", "gpt-6-astra"],
        price_per_million_input_and_output_usd="1.00",
        authorization="用户在单次提案1美元及先审核计划之后明确：好的开始执行。",
        automatic_retry=False,
        comparisons_authorized=False,
        thesis_update_authorized=False,
        request_sha256=digest(output / "request.json"),
        base_prompt_sha256=baseline.base_prompt_sha256,
        components={p: digest(ROOT / p) for p in ("scripts/forge_recovery_harness_proposal.py", "backend/packages/harness/deerflow/compile/recovery_harness.py", "backend/packages/harness/deerflow/compile/simple_build_task.py")},
    )
    save(output / "scope.json", scope)
    return scope


def generate(output, model):
    """仅一次调用；失败响应和已知费用优先落盘，不重试、不比较。"""
    scope = load(output / "scope.json")
    if scope["identity"] != IDENTITY or digest(output / "request.json") != scope["request_sha256"]:
        raise PlanContractError("提案身份或请求材料变化")
    if datetime.now(UTC) >= datetime.fromisoformat(scope["deadline"]):
        raise PlanContractError("本轮提案时窗已结束")
    for path, expected in scope["components"].items():
        if digest(ROOT / path) != expected:
            raise PlanContractError("准备后组件变化：" + path)
    marker = output / "request-started.json"
    with marker.open("x") as stream:
        json.dump(dict(identity=IDENTITY, started_at=datetime.now(UTC).isoformat(), maximum_cost_usd="1.00", retry=False), stream)
    started = time.monotonic()
    known = False
    try:
        request = load(output / "request.json")
        response = model.invoke([SystemMessage(content=request["system_prompt"]), HumanMessage(content=json.dumps(request["packet"], ensure_ascii=False))])
        save(output / "response.json", response.model_dump(mode="json"))
        usage = response.usage_metadata
        if not usage or any(not isinstance(usage.get(k), int) or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
            raise PlanContractError("未知用量，停止付费")
        cost = Decimal(usage["input_tokens"] + usage["output_tokens"]) / Decimal(1000000)
        actual = response.response_metadata.get("model_name") or response.response_metadata.get("model")
        save(output / "usage.json", dict(**usage, estimated_cost_usd_completed_responses=str(cost), requested_model=scope["requested_model"], response_model=actual, seconds=time.monotonic() - started, actual_backend_confirmed=False))
        known = True
        if actual not in scope["accepted_response_models"] or cost > Decimal(scope["maximum_cost_usd"]):
            raise PlanContractError("模型标识或费用超出本轮边界")
        proposal = RecoveryHarnessProposal.model_validate_json(response.text)
        candidate = proposal.materialize(RecoveryHarness.model_validate(load(output / "baseline.json")), load(output / "corpus.json"))
        save(output / "proposal.json", proposal.model_dump(mode="json"))
        save(output / "candidate.json", candidate.model_dump(mode="json"))
        (output / "prompt-before.txt").write_text(SIMPLE_PROMPT)
        (output / "prompt-after.txt").write_text(candidate.prompt(SIMPLE_PROMPT))
        save(
            output / "completed.json",
            dict(identity=IDENTITY, state="no_change" if proposal.no_change else "awaiting_user_candidate_review", candidate_sha256=candidate.fingerprint(), comparisons_started=0, thesis_updated=False, estimated_cost_usd=str(cost)),
        )
        return candidate
    except Exception as error:
        save(output / "failure.json", dict(identity=IDENTITY, category=type(error).__name__, unknown_usage=not known, automatic_retry=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "propose"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorized-identity")
    args = parser.parse_args()
    if args.mode == "prepare":
        print(json.dumps(prepare(args.output), ensure_ascii=False))
        return
    # 核验授权、窗口及一次性标记后才读取既有RichLab凭据；不读取DeepSeek。
    scope = load(args.output / "scope.json")
    if args.authorized_identity != IDENTITY or scope["identity"] != IDENTITY or scope["maximum_cost_usd"] != "1.00" or datetime.now(UTC) >= datetime.fromisoformat(scope["deadline"]) or (args.output / "request-started.json").exists():
        raise PlanContractError("缺少本轮有效一次性提案授权")
    import tomllib

    from forge_planner_model_comparison import RichLabPlanner

    config = tomllib.loads(Path("/home/yiwei/.codex/config.toml").read_text())
    endpoint = config["model_providers"][config["model_provider"]]["base_url"]
    key = load(Path("/home/yiwei/.codex/auth.json"))["OPENAI_API_KEY"]
    model = RichLabPlanner(model="gpt-6-astra", api_key=key, base_url=endpoint, use_responses_api=True, max_tokens=8192, max_retries=0, timeout=240, reasoning_effort="low", store=False)
    result = generate(args.output, model)
    print(json.dumps(dict(state="awaiting_user_candidate_review", candidate_sha256=result.fingerprint(), comparisons_started=0), ensure_ascii=False))


if __name__ == "__main__":
    main()
