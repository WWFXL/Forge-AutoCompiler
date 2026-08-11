from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

from deerflow.compile.evidence import AttemptBudgetExceeded

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "scripts" / "forge_formal_collection_v2_runner.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_module("forge_formal_collection_v4_lifecycle_test", RUNNER_PATH)


def test_work_deadline_cancels_active_agent_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_cancelled = asyncio.Event()
    enforced: list[tuple[str, str]] = []

    class SlowClient:
        async def astream(self, _message: str, *, thread_id: str):
            del thread_id
            try:
                await asyncio.sleep(60)
                yield None
            except asyncio.CancelledError:
                stream_cancelled.set()
                raise

    monkeypatch.setattr(
        runner,
        "remaining_experiment_work_seconds",
        lambda _thread_id: 0.01,
    )

    def reject(thread_id: str, checkpoint: str):
        enforced.append((thread_id, checkpoint))
        raise AttemptBudgetExceeded(checkpoint, "attempt_budget_exhausted")

    monkeypatch.setattr(runner, "enforce_experiment_attempt_budget", reject)

    with pytest.raises(AttemptBudgetExceeded) as exc_info:
        asyncio.run(
            runner._consume_client_stream_with_attempt_budget(
                SlowClient(),
                "compile",
                thread_id="thread-attempt-budget",
            )
        )

    assert exc_info.value.classification == "attempt_budget_exhausted"
    assert stream_cancelled.is_set()
    assert enforced == [("thread-attempt-budget", "before_submit_or_replay")]


def test_runner_without_attempt_budget_preserves_unbounded_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        async def astream(self, _message: str, *, thread_id: str):
            del thread_id
            yield type(
                "Event",
                (),
                {"type": "end", "data": None},
            )()

    monkeypatch.setattr(
        runner,
        "remaining_experiment_work_seconds",
        lambda _thread_id: None,
    )

    result = asyncio.run(
        runner._consume_client_stream_with_attempt_budget(
            Client(),
            "compile",
            thread_id="legacy-thread",
        )
    )

    assert result == {
        "tool_call_count": 0,
        "compile_tool_call_count": 0,
        "stream_completed": True,
    }
