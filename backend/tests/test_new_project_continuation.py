"""续段只覆盖原未启动槽，方法及旧失败保持；不访问Provider或Docker。"""

import copy
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_new_project_continuation as continuation  # noqa: E402


def test_continuation_is_exact_unstarted_suffix_and_keeps_all_method_conditions():
    candidate = continuation.candidate_for()
    parent = continuation.base.load(continuation.parent.MANIFEST)
    assert candidate["identity"] != parent["identity"]
    assert candidate["schedule"] == parent["schedule"][18:]
    assert len(candidate["schedule"]) == 24
    assert Counter(row["method"] for row in candidate["schedule"]) == dict.fromkeys(continuation.system.METHODS, 8)
    assert candidate["continuation"]["excluded_parent_slots"] == list(range(1, 19))
    assert candidate["continuation"]["slot_mapping"] == [dict(slot=i, parent_slot=i + 18, **row) for i, row in enumerate(candidate["schedule"], 1)]
    changed = {"identity", "issue", "kind", "schedule", "parent_manifests", "components"}
    assert all(candidate[key] == value for key, value in parent.items() if key not in changed)
    assert all(candidate["components"][name] == value for name, value in parent["components"].items())
    assert not set(tuple(row.values()) for row in candidate["schedule"]) & set(tuple(row.values()) for row in parent["schedule"][:18])


def test_rejects_retrying_parent_interrupted_slot_before_runtime_access():
    candidate = copy.deepcopy(continuation.candidate_for())
    candidate["schedule"][0] = continuation.base.load(continuation.parent.MANIFEST)["schedule"][17]
    with pytest.raises(continuation.base.PlanContractError, match="续段身份"):
        continuation.validate(candidate)


def test_entry_dispatches_unchanged_three_system_executor_and_flash(monkeypatch):
    expected = ["entry", "--candidate", "frozen.json"]
    monkeypatch.setattr(sys, "argv", expected)
    monkeypatch.setattr(continuation.signal, "signal", lambda *args: None)

    def run():
        assert sys.argv == expected
        assert continuation.base.PROVIDER is continuation.system.flash.PROVIDER
        assert continuation.base.execute is continuation.system.execute
        assert continuation.base.validate is continuation.validate
        return 0

    monkeypatch.setattr(continuation.base, "main", run)
    assert continuation.main() == 0


def test_analysis_keeps_new_denominator_failure_cost_and_missing_time(tmp_path):
    schedule = continuation.candidate_for()["schedule"]
    method = schedule[0]["method"]
    row = dict(**schedule[0], strict_completed=False, agent_usage=dict(model_requests=2, estimated_cost_usd_completed_responses="0.02"), arm_total_wall_seconds=None)
    (tmp_path / "protocol.json").write_text(json.dumps(dict(schedule=schedule)))
    (tmp_path / "result.json").write_text(json.dumps(dict(identity=continuation.IDENTITY, rows=[row], unobserved_schedule=schedule[1:], stop_reason="operator_stop")))
    result = continuation.analyze(tmp_path)
    assert result["identity"] == continuation.IDENTITY
    assert result["summary"][method]["observed"] == 1
    assert result["summary"][method]["complete"] == 0
    assert result["summary"][method]["known_cost_usd"] == "0.02"
    assert result["summary"][method]["missing_timing"] == 1
    assert result["summary"][method]["unobserved"] == 7
    assert all(summary["planned"] == 8 for summary in result["summary"].values())
    assert result["unobserved_schedule"] == schedule[1:]
