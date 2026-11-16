"""验证诊断证据选择及实际恢复接线；脚本回复不代表模型效果。"""

import json
from types import SimpleNamespace

import pytest
from test_plan_agent import ScriptedPlanModel, response
from test_recovery_environment import meter_at
from test_simple_build import actions, simple_actions, workflow

from deerflow.compile.dependency_diagnosis import DIAGNOSIS_PROMPT, DependencyDiagnosis, failure_gap
from deerflow.compile.recovery_diagnostic_memory import RecoveryDiagnosticMemory
from deerflow.compile.recovery_environment import RecoveryEnvironment
from deerflow.compile.simple_build_task import propose_simple

pytest_plugins = ["test_simple_build"]


def handoff(text):
    return dict(handoff_id="handoff1", step_id="configure", recent_commands=[dict(command_id="failed1", log_path="logs/failed1", role="configure", exit_code=1, output_tail=text)])


@pytest.mark.parametrize(
    "text,kind,item",
    [
        ("configure.ac:12: error: possibly undefined macro: LT_SYS_SAMPLE", "macro", "LT_SYS_SAMPLE"),
        ("main.c:1: fatal error: sample/header.hpp: No such file or directory", "header", "sample/header.hpp"),
        ("/bin/bash: line 1: flex: command not found", "command", "flex"),
        ("/usr/bin/ld: cannot find -lfoo", "library", "foo"),
        ("No package 'foo-1' found", "pkgconfig", "foo-1"),
    ],
)
def test_gap_keeps_failure_provenance_and_does_not_claim_missing_package(text, kind, item):
    gap = failure_gap(handoff(text))
    assert (gap["kind"], gap["item"]) == (kind, item)
    assert gap["fact"]["command_id"] == "failed1"
    assert "尚无证据" in gap["unresolved"][-1]
    assert "candidate" not in gap
    if kind == "macro":
        assert gap["component_hint"]["value"] == "libtool"
        assert "尚未核实" in gap["component_hint"]["basis"]


def test_unknown_ambiguous_and_diagnostic_failures_are_not_classified():
    assert failure_gap(handoff("make: No rule to make target 'missing'")) is None
    assert failure_gap(handoff("possibly undefined macro: AAA\npossibly undefined macro: BBB")) is None
    value = handoff("possibly undefined macro: LT_EXAMPLE")
    value["recent_commands"][0]["role"] = "diagnostic"
    assert failure_gap(value) is None


class QueryEnvironment:
    def __init__(self, *, index=True, limit=12):
        self.workflow = SimpleNamespace(handoff=handoff("possibly undefined macro: LT_EXAMPLE"))
        self.handoff_id = "handoff1"
        self.diagnostic_memory = RecoveryDiagnosticMemory()
        self.calls = []
        self.index, self.limit = index, limit
        self.meter = SimpleNamespace(ledger=SimpleNamespace(append=lambda *args, **kwargs: None))

    def execute(self, operation, query, **options):
        if len(self.calls) >= self.limit:
            return dict(status="budget_exhausted")
        self.calls.append((operation, query, options))
        result = dict(status="no_match_in_scope", command_id=f"q{len(self.calls)}", log_path=f"logs/q{len(self.calls)}")
        kind = options.get("kind")
        if kind == "package_search":
            result.update(status="ok" if self.index else "index_unavailable", output="different-dev - libtool development macros\n" if self.index else "", index_state=dict(packages="present" if self.index else "missing"))
        elif kind == "package":
            result.update(status="query_failed", installed=False)
        elif kind in {"package_description", "package_files", "search_paths"}:
            result.update(status="ok", output="real query output")
        return result


def test_preparation_collects_uninstalled_candidates_once_without_file_lookup_of_macro():
    environment = QueryEnvironment()
    diagnosis = DependencyDiagnosis(environment)
    diagnosis.prepare()
    diagnosis.prepare()
    assert len(environment.calls) == 3
    assert environment.calls[-1] == ("environment", "libtool", dict(kind="package_search"))
    assert not any(c[2].get("kind") == "package_file_search" for c in environment.calls)
    candidate = environment.diagnostic_memory.snapshot(environment.workflow.handoff)["candidates"][0]
    assert candidate["package"] == "different-dev" and candidate["command_id"] == "q3"
    assert not candidate["checks"]
    assert diagnosis.snapshot()["reminders"]


def test_candidate_verification_includes_installed_state_files_and_paths():
    environment = QueryEnvironment()
    diagnosis = DependencyDiagnosis(environment)
    diagnosis.prepare()
    result = diagnosis.diagnose("macro", "LT_EXAMPLE", candidate="different-dev")
    assert len(result["evidence"]) == 4 and len(environment.calls) == 7
    candidate = environment.diagnostic_memory.snapshot(environment.workflow.handoff)["candidates"][0]
    assert candidate["checks"]["package"]["installed"] is False
    assert candidate["checks"]["package_description"]["command_id"] == "q4"
    assert environment.calls[-1] == ("environment", "aclocal", dict(kind="search_paths"))


def test_missing_index_and_budget_do_not_become_negative_provider_evidence():
    environment = QueryEnvironment(index=False)
    diagnosis = DependencyDiagnosis(environment)
    diagnosis.prepare()
    assert not environment.diagnostic_memory.candidates
    assert any("不可用" in note for note in diagnosis.snapshot()["reminders"])
    limited = QueryEnvironment(limit=1)
    result = DependencyDiagnosis(limited).diagnose("macro", "LT_EXAMPLE", component="libtool")
    assert len(result["evidence"]) == 2 and result["evidence"][-1]["result"]["status"] == "budget_exhausted"
    assert len(limited.calls) == 1


def test_invalid_bundle_is_atomic_and_repeat_reminder_does_not_block():
    environment = QueryEnvironment()
    diagnosis = DependencyDiagnosis(environment)
    assert diagnosis.diagnose("macro", "LT_EXAMPLE", candidate="--option")["status"] == "invalid_query"
    assert not environment.calls
    diagnosis.diagnose("macro", "LT_EXAMPLE")
    diagnosis.diagnose("macro", "LT_EXAMPLE")
    assert len(environment.calls) == 4
    assert diagnosis.snapshot()["reminders"]


@pytest.mark.parametrize("kind,item,file", [("header", "foo/foo.h", "usr/include/foo/foo.h"), ("library", "foo", "libfoo.so"), ("pkgconfig", "foo", "foo.pc"), ("command", "flex", "flex")])
def test_file_provider_queries_use_files_not_symbols(kind, item, file):
    environment = QueryEnvironment()
    DependencyDiagnosis(environment).diagnose(kind, item)
    assert ("environment", file, dict(kind="package_file_search")) in environment.calls


def test_header_without_standard_path_match_expands_scope(monkeypatch):
    environment = QueryEnvironment()
    original = environment.execute

    def execute(operation, query, **options):
        result = original(operation, query, **options)
        result["status"] = "no_match_in_index"
        return result

    monkeypatch.setattr(environment, "execute", execute)
    DependencyDiagnosis(environment).diagnose("header", "custom.h")
    assert [call[1] for call in environment.calls] == ["usr/include/custom.h", "custom.h"]


def test_actual_graph_receives_prepared_evidence_and_tool_then_returns_to_workflow(runner, monkeypatch):
    w = workflow(runner, actions("make missing-target"))
    assert w.run()["status"] == "needs_handoff"
    # 合成缺宏日志用于接线；真实主项目仍是夹具，非libffi或模型效果。
    w.handoff["recent_commands"][-1]["output_tail"] = "possibly undefined macro: LT_EXAMPLE"
    meter = meter_at(w.root)
    service = RecoveryEnvironment(w, meter, diagnose_dependencies=True)
    controlled = QueryEnvironment()
    monkeypatch.setattr(service, "execute", controlled.execute)
    model = ScriptedPlanModel(responses=[response("diagnose_dependency", dict(kind="macro", item="LT_EXAMPLE", candidate="different-dev")), response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    revised, reason = propose_simple(model=model, task=w.plan.task, source_root=w.root, session_root=w.root, meter=meter, current_plan=w.plan, handoff=w.handoff, revision_validator=w.validate_revision, diagnostics=service)
    first = json.loads((w.root / "agent/request-1.json").read_text())
    packet = json.loads(first["messages"][0]["content"])
    assert packet["dependency_diagnosis"]["gap"]["item"] == "LT_EXAMPLE"
    assert packet["recovery_diagnostic_memory"]["candidates"][0]["package"] == "different-dev"
    assert DIAGNOSIS_PROMPT in first["system_message"]["content"]
    second = json.loads((w.root / "agent/request-2.json").read_text())
    candidate = json.loads(second["messages"][0]["content"])["recovery_diagnostic_memory"]["candidates"][0]
    assert candidate["checks"]["package"]["installed"] is False
    assert (w.root / "agent/dependency-diagnosis-request-2.json").is_file()
    w.apply_revision(handoff_id=w.handoff["handoff_id"], plan=revised, reason=reason)
    assert w.run()["status"] == "primary_completed"


def test_real_command_bundle_consumes_each_query_and_default_has_no_new_tool(runner):
    w = workflow(runner, actions("make missing-target"))
    w.run()
    meter = meter_at(w.root)
    old = RecoveryEnvironment(w, meter)
    assert len(old.tools()) == 2 and old.dependency_diagnosis is None
    new = RecoveryEnvironment(w, meter, diagnose_dependencies=True)
    assert len(new.tools()) == 3
    # 只执行两个查询后遇原额度；组合工具不能借一次调用绕过命令预算。
    w.budget = w.budget.model_copy(update={"max_commands": w.commands_used + 2})
    result = new.dependency_diagnosis.diagnose("command", "cc")
    assert new.calls == 2 and meter.tracker.snapshot().commands == 2
    assert result["evidence"][0]["result"]["status"] == "ok"
    assert result["evidence"][-1]["result"]["status"] == "budget_exhausted"
    assert w.status == "needs_handoff"


def test_new_recovery_stalls_remind_without_removing_tools(runner):
    w = workflow(runner, actions("make missing-target"))
    w.run()
    # 与正式布局一致，Agent账本位于源码树外，避免查询命中自己的新日志。
    meter = meter_at(w.root.parent)
    model = ScriptedPlanModel(responses=[*[response("search_build_files", dict(query="int sample", scope="project")) for _ in range(5)], response("SimpleBuildActions", simple_actions().model_dump(mode="json"))])
    propose_simple(model=model, task=w.plan.task, source_root=w.root, session_root=w.root, meter=meter, current_plan=w.plan, handoff=w.handoff, diagnostics=RecoveryEnvironment(w, meter, diagnose_dependencies=True))
    sent = json.loads((w.root.parent / "agent/request-6.json").read_text())
    packet = json.loads(sent["messages"][0]["content"])
    assert packet["planning_progress"]["consecutive_rounds_without_new_evidence"] >= 3
    assert "新问题" in packet["planning_progress"]["instruction"]
    assert any(tool["function"]["name"] == "diagnose_dependency" for tool in sent["tools"])
