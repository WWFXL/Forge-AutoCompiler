#!/usr/bin/env python3
"""Bounded, secret-safe connectivity checks for supported model providers."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

SAFE_MODEL_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")


@dataclass(frozen=True)
class Provider:
    endpoint: str
    credential_env: str
    models: tuple[str, ...]


PROVIDERS = {
    "richlab": Provider(
        endpoint="https://richlab-api-x.choosefire.com/v1",
        credential_env="OpenAI_AK",
        models=("gpt-5.5", "gpt-5.4"),
    ),
    "deepseek": Provider(
        endpoint="https://api.deepseek.com",
        credential_env="DEEPSEEK_API_KEY",
        models=("deepseek-v4-flash", "deepseek-v4-pro"),
    ),
}


def _emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def _safe_model(value: object) -> str | None:
    return value if isinstance(value, str) and SAFE_MODEL_RE.fullmatch(value) else None


def _request(provider: Provider, path: str, credential: str, payload: dict | None, timeout: int) -> tuple[object, dict | None, float]:
    headers = {"Authorization": f"Bearer {credential}", "User-Agent": "forge-model-preflight/1.0"}
    data = None
    method = "GET"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
        method = "POST"
    request = urllib.request.Request(f"{provider.endpoint}{path}", data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
        return response.status, json.load(response), round(time.monotonic() - started, 3)
    except urllib.error.HTTPError as error:
        return error.code, None, round(time.monotonic() - started, 3)
    except Exception as error:
        return type(getattr(error, "reason", error)).__name__, None, round(time.monotonic() - started, 3)


def run_preflight(provider_name: str, *, timeout: int, include_tool_call: bool = True) -> bool:
    provider = PROVIDERS[provider_name]
    credential = os.environ.get(provider.credential_env, "").strip()
    if not credential:
        _emit({"provider": provider_name, "stage": "credential", "ok": False, "classification": "credential_missing"})
        return False

    all_ok = True
    status, body, latency = _request(provider, "/models", credential, None, timeout)
    available = {_safe_model(item.get("id")) for item in (body or {}).get("data", []) if isinstance(item, dict)}
    models_present = [model for model in provider.models if model in available]
    models_ok = status == 200 and len(models_present) == len(provider.models)
    _emit(
        {
            "provider": provider_name,
            "stage": "models",
            "ok": models_ok,
            "status": status,
            "latency_seconds": latency,
            "target_models_present": models_present,
        }
    )
    all_ok &= models_ok

    for model in provider.models:
        status, body, latency = _request(
            provider,
            "/chat/completions",
            credential,
            {
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "thinking": {"type": "disabled"},
                "max_tokens": 8,
                "stream": False,
            },
            timeout,
        )
        choice = ((body or {}).get("choices") or [{}])[0]
        message = choice.get("message") or {}
        actual_model = _safe_model((body or {}).get("model"))
        chat_ok = status == 200 and bool(message.get("content")) and actual_model == model
        _emit(
            {
                "provider": provider_name,
                "stage": "minimal_chat",
                "requested_model": model,
                "actual_model": actual_model,
                "ok": chat_ok,
                "status": status,
                "latency_seconds": latency,
                "finish_reason": choice.get("finish_reason") if choice.get("finish_reason") in {"stop", "length", "tool_calls"} else None,
                "content_present": bool(message.get("content")),
            }
        )
        all_ok &= chat_ok

        if not include_tool_call:
            continue
        status, body, latency = _request(
            provider,
            "/chat/completions",
            credential,
            {
                "model": model,
                "messages": [{"role": "user", "content": "Call select_build_system for a CMake project."}],
                "thinking": {"type": "disabled"},
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "select_build_system",
                            "description": "Select the required build system.",
                            "parameters": {
                                "type": "object",
                                "properties": {"build_system": {"type": "string", "enum": ["cmake", "make", "autotools"]}},
                                "required": ["build_system"],
                                "additionalProperties": False,
                            },
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": "select_build_system"}},
                "max_tokens": 64,
                "stream": False,
            },
            timeout,
        )
        choice = ((body or {}).get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        function_name = None
        if tool_calls:
            function_name = (tool_calls[0].get("function") or {}).get("name")
        actual_model = _safe_model((body or {}).get("model"))
        tool_ok = status == 200 and actual_model == model and function_name == "select_build_system"
        _emit(
            {
                "provider": provider_name,
                "stage": "tool_call",
                "requested_model": model,
                "actual_model": actual_model,
                "ok": tool_ok,
                "status": status,
                "latency_seconds": latency,
                "finish_reason": choice.get("finish_reason") if choice.get("finish_reason") in {"stop", "length", "tool_calls"} else None,
                "tool_call_present": bool(tool_calls),
                "function_name": function_name if function_name == "select_build_system" else None,
            }
        )
        all_ok &= tool_ok

    _emit({"provider": provider_name, "stage": "summary", "ready": all_ok})
    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--skip-tool-call", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be between 1 and 120 seconds")
    return 0 if run_preflight(args.provider, timeout=args.timeout, include_tool_call=not args.skip_tool_call) else 2


if __name__ == "__main__":
    raise SystemExit(main())
