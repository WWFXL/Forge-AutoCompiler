"""固定比较的调度、费用停止和独立测试定位；不使用真实Provider。"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_simple_comparison as comparison  # noqa: E402


def authorization(now=None):
    now = now or datetime.now(UTC)
    return dict(
        identity=comparison.IDENTITY,
        candidate_sha256="a" * 64,
        user_reply="授权10美元、8小时，按48次协议执行",
        authorized_at_utc=now.isoformat(),
        deadline_utc=(now + timedelta(hours=8)).isoformat(),
        maximum_cost_usd="10",
        automatic_retry=False,
    )


def protocol():
    return dict(identity=comparison.IDENTITY, schedule=comparison.schedule(), projects=[dict(name=n) for n in comparison.PROJECTS])


def row(**kwargs):
    return dict(
        agent_usage=dict(model_requests=1, estimated_cost_usd_completed_responses="0.01", unknown_usage_requests=kwargs.pop("unknown", 0)),
        cleanup=dict(succeeded=True),
        layers=dict(primary_build_completed=kwargs.pop("primary", True), full_completed=kwargs.pop("full", True)),
        **kwargs,
    )


def test_schedule_has_paired_denominators_and_balanced_positions_and_predecessors():
    slots = comparison.schedule()
    assert len(slots) == 48
    assert set(Counter((s["project"], s["repetition"]) for s in slots).values()) == {4}
    positions, predecessors = Counter(), Counter()
    for i in range(0, 48, 4):
        group = slots[i : i + 4]
        assert {s["method"] for s in group} == set(comparison.METHODS)
        positions.update((s["method"], p) for p, s in enumerate(group))
        predecessors.update((a["method"], b["method"]) for a, b in zip(group, group[1:]))
    assert set(positions.values()) == {3}
    assert len(predecessors) == 12 and set(predecessors.values()) == {3}


def test_authorization_rejects_expired_wrong_identity_and_implicit_retry():
    now = datetime.now(UTC)
    good = authorization(now - timedelta(seconds=1))
    comparison.validate_authorization(good, "a" * 64, now=now)
    for bad in [good | dict(identity="old"), good | dict(deadline_utc=(now - timedelta(seconds=1)).isoformat()), good | dict(maximum_cost_usd="11"), good | dict(automatic_retry=True), good | dict(candidate_sha256="b" * 64)]:
        with pytest.raises(comparison.PlanContractError):
            comparison.validate_authorization(bad, "a" * 64, now=now)


def test_all_48_dispatches_keep_natural_failure_without_retry_and_count_failed_cost(tmp_path):
    calls = []

    def executor(**kwargs):
        calls.append(kwargs)
        return row(primary=len(calls) != 2, full=len(calls) != 2)

    result = comparison.execute(protocol(), tmp_path / "run", authorization(), executor)
    assert len(calls) == 48 and result["unobserved"] == []
    assert result["closed_slot_cost_usd"] == "0.48" and result["rows"][1]["layers"]["primary_build_completed"] is False
    assert len({c["folder"] for c in calls}) == 48
    assert not any("recipe" in c for c in calls)


@pytest.mark.parametrize("failure,reason", [(dict(unknown=1), "unknown_usage"), (dict(cleanup=dict(succeeded=False)), "cleanup_failure")])
def test_unknown_or_cleanup_failure_stops_whole_batch_and_retains_remaining_denominator(tmp_path, failure, reason):
    def executor(**kwargs):
        return row(**failure) if "cleanup" not in failure else row() | failure

    result = comparison.execute(protocol(), tmp_path / "run", authorization(), executor)
    assert result["completed_slots"] == 1 and len(result["unobserved"]) == 47
    assert result["stop_reason"] == reason


def test_model_identity_mismatch_stops_with_known_usage(tmp_path):
    folder = tmp_path / "slot"
    (folder / "agent").mkdir(parents=True)
    (folder / "agent/request-001.response.json").write_text(json.dumps(dict(model="other-model")))
    assert comparison.global_stop(row(), folder) == "model_identity_mismatch"


def test_missing_cost_is_not_silently_zero():
    with pytest.raises(comparison.PlanContractError):
        comparison.usage(dict(agent_usage={}))


def test_paid_dispatch_uses_same_flash_and_routes_experience_only_to_its_arm(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import openai

    models, calls = [], []
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-test-placeholder")
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: pytest.fail("不可请求Provider")))))
    monkeypatch.setattr(comparison, "PlanThinkingDeepSeek", lambda **kw: models.append(kw) or object())
    monkeypatch.setattr(comparison, "run_simple_system", lambda **kw: calls.append(kw) or row())
    monkeypatch.setattr(comparison, "run_native_cxx", lambda **kw: calls.append(kw) or row())
    fixture = comparison.load(comparison.FIXTURE)
    bank = tmp_path / "seed-bank.json"
    bank.write_text(json.dumps(dict(sources=[], entries=[])))
    p = protocol() | dict(projects=fixture["projects"], experience=dict(path=str(bank)), baseline=dict(path=str(comparison.BASELINE)))
    execute = comparison.paid_executor(p)
    result = comparison.execute(p, tmp_path / "run", authorization(), execute)
    assert result["completed_slots"] == 48 and len(models) == 36
    assert all(m["model"] == "deepseek-flash" and m["max_retries"] == 0 for m in models)
    assert sum(c.get("bank") is not None for c in calls) == 12
    assert sum("completion_call" in c for c in calls) == 12
    assert all("recipe" not in c for c in calls)


def test_shared_cost_limits_next_slot_and_exception_does_not_claim_billing_complete(tmp_path):
    caps = []

    def executor(**kwargs):
        caps.append(kwargs["available"])
        return row() | dict(agent_usage=dict(model_requests=1, estimated_cost_usd_completed_responses=str(kwargs["available"]), unknown_usage_requests=0))

    result = comparison.execute(protocol(), tmp_path / "budget", authorization() | dict(maximum_cost_usd="1.05"), executor)
    assert len(caps) == 1 and result["stop_reason"] == "shared_budget" and result["billing_complete"]

    def broken(**kwargs):
        raise RuntimeError("已开始但未闭合")

    with pytest.raises(RuntimeError):
        comparison.execute(protocol(), tmp_path / "interrupted", authorization(), broken)
    partial = comparison.load(tmp_path / "interrupted/result.json")
    assert partial["unclosed_slot"]["slot"] == 1 and partial["billing_complete"] is False and len(partial["unobserved"]) == 48


def test_cmake_author_tests_follow_actual_nonstandard_build_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "CMakeLists.txt").write_text('cmake_minimum_required(VERSION 3.16)\nproject(sample C)\nenable_testing()\nadd_test(NAME original COMMAND "${CMAKE_COMMAND}" -E true)\n')
    build = source / "author-output"
    subprocess.run(["cmake", "-S", str(source), "-B", str(build)], check=True, capture_output=True)
    fixture = comparison.load(comparison.FIXTURE)
    command = fixture["projects"][0]["reference"]["author_tests"][0]["command"].replace("/workspace/repo", str(source))
    result = subprocess.run(["bash", "-euo", "pipefail", "-c", command], cwd=source, capture_output=True, text=True)
    assert result.returncode == 0 and "100% tests passed" in result.stdout
    assert not (source / "build").exists()
