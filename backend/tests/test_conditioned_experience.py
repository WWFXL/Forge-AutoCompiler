"""验证过程证据、逐条选择和未确认条件；不模拟模型效果。"""

import json

import pytest

from deerflow.compile.conditioned_experience import ConditionedBank, validate_process_extraction
from deerflow.compile.operations import infer_command_roles


def trace():
    return dict(source_id="s1", family="seed", build_system="cmake", commands=[dict(command_id="c1", exit_code=0)], process_observations=[dict(evidence_id="p1")], observed_validation=dict(tests="unobserved"))


def entry(**changes):
    return (
        dict(
            conditions=["作者声明测试"],
            stage="configure",
            state="test unavailable",
            action="enable author tests",
            outcome="effective",
            not_applicable=["无对应声明"],
            command_ids=["c1"],
            evidence_ids=["p1", "c1"],
            verification_scope="仅成功配置",
            failed_attempt=None,
            feedback="配置成功，测试未观察",
            observed_revision=None,
            applicability=dict(required_files=["CMakeLists.txt"], declaration_terms=["enable_testing"], error_markers=[]),
        )
        | changes
    )


def bank(entries, path=None):
    source = trace() | dict(retrieval_text="", raw_context={})
    return ConditionedBank([source], entries, {"target": dict(files=["CMakeLists.txt"], declarations=[dict(text="enable_testing()")])}, path)


def test_process_evidence_does_not_upgrade_unobserved():
    values = validate_process_extraction(dict(experiences=[entry()]), trace())
    assert values[0]["observed_validation"]["tests"] == "unobserved"
    with pytest.raises(ValueError, match="不存在"):
        validate_process_extraction(dict(experiences=[entry(evidence_ids=["invented"])]), trace())
    with pytest.raises(ValueError, match="实际成功"):
        validate_process_extraction(dict(experiences=[entry(command_ids=[])]), trace())


def test_selects_entry_not_entire_source_and_records_unknown(tmp_path):
    entries = validate_process_extraction(dict(experiences=[entry(), entry(applicability=dict(required_files=[], declaration_terms=["unknown_flag"], error_markers=[]))]), trace())
    path = tmp_path / "selection.jsonl"
    result = bank(entries, path).retrieve(build_system="cmake", family="target", stage="initial", text='{"handoff":{}}', mode="structured")
    assert len(result["items"]) == 1
    assert len(result["items"][0]["material"]) == 1
    rows = json.loads(path.read_text())["decisions"]
    assert rows[1]["checks"][0]["status"] == "unconfirmed"
    assert not rows[1]["selected"]


def test_failure_only_experience_requires_actual_current_feedback():
    entries = validate_process_extraction(dict(experiences=[entry(applicability=dict(required_files=[], declaration_terms=[], error_markers=["not found"]))]), trace())
    store = bank(entries)
    args = dict(build_system="cmake", family="target", stage="configure", mode="structured")
    assert not store.retrieve(**args, text='{"task":{"description":"not found"},"handoff":{}}')["items"]
    assert store.retrieve(**args, text='{"handoff":{"output":"dependency not found"}}')["items"]
    assert not store.retrieve(**(args | dict(stage="build")), text='{"handoff":{"output":"not found"}}')["items"]


@pytest.mark.parametrize(
    "command,expected",
    [
        ("command -v make; command -V cmake", set()),
        ("if ! command -v make; then apt-get update && apt-get install -y make; fi", {"dependency_setup"}),
        ("sh -c 'command -v autoreconf && command -v make || apt-get install -y automake'", {"dependency_setup"}),
        ("command -v make && make && autoreconf -fi", {"build", "configure"}),
        ("command make -v", {"build"}),
        ("if command -v make; then make; fi", {"build"}),
    ],
)
def test_probe_is_not_execution_but_compound_build_retained(command, expected):
    assert infer_command_roles(command) == expected
