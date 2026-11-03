"""迁移候选保留原事实，未核对条件不当作自动动作授权。"""

import copy
import json

from test_conditioned_experience import entry, trace

from deerflow.compile.conditioned_experience import validate_process_extraction
from deerflow.compile.transfer_action_experience import TransferActionBank


def store(terms, *, files=None, errors=None):
    entries = validate_process_extraction(dict(experiences=[entry(applicability=dict(required_files=["CMakeLists.txt", "source_test.cpp"], declaration_terms=terms, error_markers=errors or []))]), trace())
    bank = TransferActionBank([trace() | dict(retrieval_text="", raw_context={})], entries, {"target": dict(files=files or ["CMakeLists.txt"], declarations=[dict(text="add_test(NAME current_test COMMAND current_test)")])})
    return bank


def retrieve(bank, **changes):
    return bank.retrieve(**(dict(build_system="cmake", family="target", stage="initial", text='{"handoff":{}}', mode="structured") | changes))


def test_source_names_are_retained_without_claiming_current_applicability():
    bank = store(["add_test", "source_unittest"])
    before = copy.deepcopy(bank.entries)
    result = retrieve(bank)
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["material"][0]["source_applicability_examples"]["declaration_terms"] == ["add_test", "source_unittest"]
    assert "尚未证明适用" in item["remaining_conditions"]
    assert bank.entries == before
    assert result["bytes"] == len(json.dumps(item, ensure_ascii=False).encode())
    assert not retrieve(bank, family="seed")["items"]
    assert not retrieve(bank, build_system="make")["items"]
    assert not retrieve(bank, stage="build")["items"]


def test_missing_general_structure_abstains_and_errors_require_current_feedback():
    assert not retrieve(store(["find_package(source)"]))["items"]
    assert not retrieve(store(["add_test"], files=["README.md"]))["items"]
    bank = store(["add_test"], errors=["missing source_test"])
    assert not retrieve(bank, text='{"task":{"description":"missing source_test"},"handoff":{}}')["items"]
    assert retrieve(bank, text='{"handoff":{"message":"missing source_test"}}')["items"]
    assert not retrieve(bank, mode="none")["items"]


def test_new_scope_requires_authorization_before_seed_copy(tmp_path, monkeypatch):
    import forge_build_transfer_action_experience as runner

    monkeypatch.setattr(runner, "SESSION", tmp_path)
    monkeypatch.setattr(runner, "check_prepared", lambda: {})
    monkeypatch.setattr(runner.first, "check_prepared", lambda: {})
    import pytest

    with pytest.raises(FileNotFoundError):
        runner.run()
    assert list(tmp_path.iterdir()) == []
