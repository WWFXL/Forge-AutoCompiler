"""只检查本次比较新增的任务、资源及时间适配，不调用Provider。"""

import copy
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_system_comparison as system  # noqa: E402


def test_all_original_tasks_kept_and_profile_check_added_separately():
    candidate = system.candidate_for()
    assert len(candidate["schedule"]) == 48
    assert Counter(row["method"] for row in candidate["schedule"]) == dict.fromkeys(system.METHODS, 16)
    parents = {i["name"]: i for name in system.PARENTS for i in system.base.load(system.ROOT / "benchmarks/manifests" / (name + ".json"))["projects"]}
    for item in candidate["projects"]:
        original = parents[item["name"]]
        steps = item["task"]["verification_steps"]
        assert steps[1:] == original["task"]["verification_steps"] if item["task"]["build_system"] == "cmake" else steps == original["task"]["verification_steps"]
        assert item["task"]["source_archive_sha256"] == original["task"]["source_archive_sha256"]
        assert item["task"]["artifact_paths"] == original["task"]["artifact_paths"]
        assert system.common_task(item)["task"] == item["task"]
    assert all(not row["holdout"] for row in candidate["exposure"])


def test_dockerfile_adaptation_keeps_agent_commands_and_is_idempotent():
    original = "FROM autocompiler:gcc13\nCOPY tinyxml2 /workspace/repo\nWORKDIR /workspace/repo\nRUN make -j2\n"
    effective = system.resource_dockerfile(original, "sha256:fixed")
    assert "RUN make -j2\n" in effective and "FROM sha256:fixed" in effective
    assert "CTEST_PARALLEL_LEVEL=2" in effective
    assert system.resource_dockerfile(effective, "sha256:fixed") == effective
    with pytest.raises(system.base.PlanContractError, match="固定镜像"):
        system.resource_dockerfile(original.replace("autocompiler:gcc13", "ubuntu:latest"), "sha256:fixed")


def test_native_requests_receive_full_task_and_identity_failure_still_costs(tmp_path, monkeypatch):
    task = dict(task=dict(verification_steps=[dict(command="actual complete fixed test")]))
    meter = system.CommonSDKMeter(tmp_path / "agent", 3, public_task=task, deadline="2099-01-01T00:00:00+00:00")
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50), model="unexpected", choices=[SimpleNamespace(finish_reason="stop")], model_dump=lambda **kw: {"usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    )
    captured = {}

    def call(**kwargs):
        captured.update(kwargs)
        return response

    with pytest.raises(system.cxx.StopPaid, match="身份"):
        meter.request(call, {"messages": [dict(role="user", content="native request")]})
    assert json.dumps(task, ensure_ascii=False) in captured["messages"][0]["content"]
    assert captured["messages"][1]["content"] == "native request"
    assert meter.summary()["estimated_cost_usd_completed_responses"] == "0.00009"
    assert meter.stopped


def test_unknown_native_usage_stops_without_retry(tmp_path):
    meter = system.CommonSDKMeter(tmp_path / "agent", 3, public_task={}, deadline="2099-01-01T00:00:00+00:00")

    def fail(**kwargs):
        raise TimeoutError("offline")

    with pytest.raises(TimeoutError):
        meter.request(fail, {})
    with pytest.raises(system.cxx.StopPaid):
        meter.request(fail, {})
    assert meter.requests == meter.unknown == 1


def test_execute_preserves_exception_usage_and_stops_batch(tmp_path, monkeypatch):
    protocol = dict(deadline_utc="2099-01-01T00:00:00+00:00", stage_max_cost_usd="10.00", schedule=[dict(project="tinyxml2", repetition=1, method=system.METHODS[0])] * 2)

    def fail(**kwargs):
        (kwargs["root"] / "tinyxml2-plan/agent").mkdir(parents=True)
        system.base.write_json(kwargs["root"] / "tinyxml2-plan/agent/usage.json", dict(model_requests=1, estimated_cost_usd_completed_responses="0.01", unknown_usage_requests=0))
        raise ValueError("after response")

    monkeypatch.setattr(system, "run_slot", fail)
    rows = []
    assert system.execute(protocol, tmp_path, None, rows) == "unknown_usage_provider_or_cleanup_stop"
    assert len(rows) == 1 and rows[0]["agent_usage"]["model_requests"] == 1
    assert not rows[0]["cleanup"]["succeeded"]


def test_slot_deadline_does_not_extend_global_window(tmp_path, monkeypatch):
    observed = {}
    slot = dict(project="tinyxml2", repetition=1, method=system.METHODS[0])
    item = next(i for i in system.candidate_for()["projects"] if i["name"] == slot["project"])
    protocol = dict(deadline_utc="2099-01-01T00:00:00+00:00", projects=[item])

    def run(selected, *args):
        observed.update(selected)
        return {}

    monkeypatch.setattr(system, "run_forge", run)
    system.run_slot(protocol=copy.deepcopy(protocol), slot=slot, root=tmp_path, model=None)
    assert 2600 < system.OperationWindow(observed["deadline_utc"]).remaining() <= 2700
    assert protocol["deadline_utc"] == "2099-01-01T00:00:00+00:00"
