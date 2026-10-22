"""实际生产纠错携带原候选与错误；零Provider，不重复构建资格。"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_candidate_feedback_probe import PaidNativeMeter  # noqa: E402
from forge_build_rtorrent_fixed_contract import FixedVerifierRegistry  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.staged_verification import StagedVerificationTask
from deerflow.compile.unified_plan_equivalent_observed import propose_observed

COMMON = dict(response_metadata=dict(model_name="scripted-feedback"), usage_metadata=dict(input_tokens=0, output_tokens=0, total_tokens=0))


class GateModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def message(name, args, identifier):
    return AIMessage(content="", tool_calls=[dict(name=name, args=args, id=identifier)], **COMMON)


def test_production_correction_receives_exact_error_keeps_bound_and_new_recovery_resets(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    spec = json.loads((repo / "benchmarks/manifests/cpp-build-rtorrent-bounded-planning-canary-v1.json").read_text())
    task = StagedVerificationTask.model_validate(spec["project"]["task"])
    (tmp_path / "configure.ac").write_text("AC_INIT([fixture],[1])\n")
    packet = dict(task=task.model_dump(mode="json"), source_packet=[], current_plan=None, handoff=None)
    value = PaidNativeMeter(PlanAgentLedger(tmp_path / "agent"), registry=FixedVerifierRegistry(packet["task"]), accepted_models=("scripted-feedback",), deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(), packet=lambda: packet)
    build = dict(step_id="build", role="build", command="make -j2", source="configure.ac", expected="编译")
    invalid = dict(reason="生产结构拒绝负例", steps=[dict(build, step_id="dependency-build"), dict(build, step_id="main-configure", role="configure", requires=["dependency-build"]), dict(build, requires=["main-configure"])])
    corrected = dict(reason="按真实反馈修正", steps=[build])
    responses = [message("read_source", dict(path="configure.ac"), f"read-{i}") for i in range(8)]
    responses.extend([message("ObservedBuildActions", invalid, "invalid"), message("ObservedBuildActions", corrected, "corrected")])
    plan, _ = propose_observed(model=GateModel(responses=responses), task=task, source_root=tmp_path, session_root=tmp_path, meter=value)
    events = [json.loads(line) for line in (tmp_path / "agent/events.jsonl").read_text().splitlines()]
    rejection = next(e for e in events if e["event"] == "observed.proposal_rejected")
    request = json.loads((tmp_path / "agent/request-10.json").read_text())
    human = json.loads(request["messages"][0]["content"])
    rejected_candidate = human["rejected_candidate"]
    assert rejected_candidate["tool_call"]["args"] == invalid
    assert rejected_candidate["error_detail"] == rejection["detail"]
    assert rejected_candidate["status"] == "not_executed" and rejected_candidate["request_sequence"] == 9
    assert rejected_candidate["response_sha256"] == __import__("hashlib").sha256((tmp_path / "agent/response-9.json").read_bytes()).hexdigest()
    assert rejected_candidate == json.loads((tmp_path / "agent/rejected-candidate-context-10.json").read_text())
    assert "角色描述相对于本次主项目" in request["system_message"]["content"]
    assert human["agent_human_messages"][1].endswith(rejection["detail"])
    assert human["agent_human_messages"][1].startswith("上次建议结构/装配不合法")
    assert [s["function"]["name"] for s in request["tools"]] == ["ObservedBuildActions"]
    context = json.loads((tmp_path / "agent/agent-context-10.json").read_text())
    assert context["previous_model_requests_in_episode"] == 9 and context["submit_state"]
    assert context["human_messages"] == human["agent_human_messages"]
    assert plan.revision == 1

    handoff = dict(handoff_id="actual-new-recovery", plan_sha256=plan.fingerprint(), step_id="build", recent_commands=[dict(command="make -j2", role="build", workdir="/workspace/repo", exit_code=2, output_tail="actual build error")])
    packet.update(current_plan=plan.model_dump(mode="json"), handoff=handoff)
    changed = dict(reason="实际恢复", steps=[dict(build, command="make -j1")])
    recovery = GateModel(responses=[message("read_source", dict(path="configure.ac"), "new-recovery-read"), message("ObservedBuildActions", changed, "changed")])
    revised, _ = propose_observed(model=recovery, task=task, source_root=tmp_path, session_root=tmp_path, meter=value, current_plan=plan, handoff=handoff)
    next_request = json.loads((tmp_path / "agent/request-11.json").read_text())
    next_context = json.loads((tmp_path / "agent/agent-context-11.json").read_text())
    assert "read_source" in [s["function"]["name"] for s in next_request["tools"]]
    assert next_context["previous_model_requests_in_episode"] == 0 and not next_context["submit_state"]
    assert "command_failed" in json.loads(next_request["messages"][0]["content"])["agent_human_messages"][0]
    assert json.loads(next_request["messages"][0]["content"])["rejected_candidate"] is None
    assert revised.revision == 2 and value.summary()["model_requests"] == 12
    assert value.summary()["recorded_tokens"] == value.summary()["unknown_usage_requests"] == 0
