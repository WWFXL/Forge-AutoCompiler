from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "model_provider_preflight.py"
SPEC = importlib.util.spec_from_file_location("model_provider_preflight", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
model_provider_preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = model_provider_preflight
SPEC.loader.exec_module(model_provider_preflight)


def test_missing_credential_fails_without_request(monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(model_provider_preflight, "_request", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("request must not run")))

    assert model_provider_preflight.run_preflight("deepseek", timeout=10) is False
    output = capsys.readouterr().out
    assert "credential_missing" in output
    assert "Authorization" not in output


def test_deepseek_success_records_only_bounded_metadata(monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    responses = iter(
        [
            (
                200,
                {"data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4-pro"}]},
                0.1,
            ),
            (
                200,
                {"model": "deepseek-v4-flash", "choices": [{"finish_reason": "stop", "message": {"content": "private response"}}]},
                0.2,
            ),
            (
                200,
                {
                    "model": "deepseek-v4-flash",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "select_build_system",
                                            "arguments": '{"build_system":"cmake","private":"value"}',
                                        }
                                    }
                                ]
                            },
                        }
                    ],
                },
                0.3,
            ),
            (
                200,
                {"model": "deepseek-v4-pro", "choices": [{"finish_reason": "stop", "message": {"content": "private response"}}]},
                0.4,
            ),
            (
                200,
                {
                    "model": "deepseek-v4-pro",
                    "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{"function": {"name": "select_build_system", "arguments": "{}"}}]}}],
                },
                0.5,
            ),
        ]
    )
    monkeypatch.setattr(model_provider_preflight, "_request", lambda *args, **kwargs: next(responses))

    assert model_provider_preflight.run_preflight("deepseek", timeout=10) is True
    output = capsys.readouterr().out
    assert "private response" not in output
    assert "secret-value" not in output
    assert '"arguments"' not in output
    assert output.count('"stage": "tool_call"') == 2


def test_actual_model_mismatch_fails(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    responses = iter(
        [
            (200, {"data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4-pro"}]}, 0.1),
            (200, {"model": "unexpected-model", "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]}, 0.2),
            (200, {"model": "unexpected-model", "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": []}}]}, 0.3),
            (200, {"model": "deepseek-v4-pro", "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]}, 0.4),
            (
                200,
                {
                    "model": "deepseek-v4-pro",
                    "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{"function": {"name": "select_build_system"}}]}}],
                },
                0.5,
            ),
        ]
    )
    monkeypatch.setattr(model_provider_preflight, "_request", lambda *args, **kwargs: next(responses))

    assert model_provider_preflight.run_preflight("deepseek", timeout=10) is False
