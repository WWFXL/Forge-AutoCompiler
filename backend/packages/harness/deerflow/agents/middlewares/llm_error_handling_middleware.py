"""LLM error handling middleware with retry/backoff and user-facing fallbacks."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from email.utils import parsedate_to_datetime
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage
from langgraph.errors import GraphBubbleUp

from deerflow.compile.evidence import (
    get_active_experiment,
    model_response_metadata,
    new_evidence_id,
    record_experiment_event,
    request_model_endpoint,
    request_model_name,
    request_model_role,
    request_thread_id,
)

logger = logging.getLogger(__name__)

_RETRIABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
_BUSY_PATTERNS = (
    "server busy",
    "temporarily unavailable",
    "try again later",
    "please retry",
    "please try again",
    "overloaded",
    "high demand",
    "rate limit",
    "负载较高",
    "服务繁忙",
    "稍后重试",
    "请稍后重试",
)
_QUOTA_PATTERNS = (
    "insufficient_quota",
    "quota",
    "billing",
    "credit",
    "payment",
    "余额不足",
    "超出限额",
    "额度不足",
    "欠费",
)
_AUTH_PATTERNS = (
    "authentication",
    "unauthorized",
    "invalid api key",
    "invalid_api_key",
    "permission",
    "forbidden",
    "access denied",
    "无权",
    "未授权",
)


class LLMErrorHandlingMiddleware(AgentMiddleware[AgentState]):
    """Retry transient LLM errors and surface graceful assistant messages."""

    retry_max_attempts: int = 3
    retry_base_delay_ms: int = 1000
    retry_cap_delay_ms: int = 8000

    def _classify_error(self, exc: BaseException) -> tuple[bool, str]:
        detail = _extract_error_detail(exc)
        lowered = detail.lower()
        error_code = _extract_error_code(exc)
        status_code = _extract_status_code(exc)

        if _matches_any(lowered, _QUOTA_PATTERNS) or _matches_any(str(error_code).lower(), _QUOTA_PATTERNS):
            return False, "quota"
        if _matches_any(lowered, _AUTH_PATTERNS):
            return False, "auth"

        exc_name = exc.__class__.__name__
        if exc_name in {
            "APITimeoutError",
            "APIConnectionError",
            "InternalServerError",
        }:
            return True, "transient"
        if status_code in _RETRIABLE_STATUS_CODES:
            return True, "transient"
        if _matches_any(lowered, _BUSY_PATTERNS):
            return True, "busy"

        return False, "generic"

    def _build_retry_delay_ms(self, attempt: int, exc: BaseException) -> int:
        retry_after = _extract_retry_after_ms(exc)
        if retry_after is not None:
            return retry_after
        backoff = self.retry_base_delay_ms * (2 ** max(0, attempt - 1))
        return min(backoff, self.retry_cap_delay_ms)

    def _build_retry_message(self, attempt: int, wait_ms: int, reason: str) -> str:
        seconds = max(1, round(wait_ms / 1000))
        reason_text = "provider is busy" if reason == "busy" else "provider request failed temporarily"
        return f"LLM request retry {attempt}/{self.retry_max_attempts}: {reason_text}. Retrying in {seconds}s."

    def _build_user_message(self, exc: BaseException, reason: str) -> str:
        detail = _extract_error_detail(exc)
        if reason == "quota":
            return "The configured LLM provider rejected the request because the account is out of quota, billing is unavailable, or usage is restricted. Please fix the provider account and try again."
        if reason == "auth":
            return "The configured LLM provider rejected the request because authentication or access is invalid. Please check the provider credentials and try again."
        if reason in {"busy", "transient"}:
            return "The configured LLM provider is temporarily unavailable after multiple retries. Please wait a moment and continue the conversation."
        return f"LLM request failed: {detail}"

    def _effective_max_attempts(self, request: ModelRequest) -> int:
        active = get_active_experiment(request_thread_id(request))
        if active is not None:
            return active.policy.model_max_retries + 1
        return self.retry_max_attempts

    def _failure_classification(
        self,
        exc: BaseException,
        reason: str,
    ) -> str:
        status_code = _extract_status_code(exc)
        exception_name = type(exc).__name__.lower()
        if reason == "quota":
            return "quota"
        if reason == "auth":
            return "authentication"
        if status_code == 429:
            return "rate_limited"
        if "timeout" in exception_name:
            return "timeout"
        if "connection" in exception_name:
            return "connection_error"
        if status_code is not None:
            return f"http_{status_code}"
        if reason == "busy":
            return "provider_busy"
        if reason == "transient":
            return "transient_provider_error"
        return "provider_error"

    def _request_started(
        self,
        request: ModelRequest,
        *,
        model_call_id: str,
        model_request_id: str,
        attempt: int,
        max_attempts: int,
    ) -> str | None:
        thread_id = request_thread_id(request)
        active = get_active_experiment(thread_id)
        configured_model = request_model_name(
            request,
            active.policy.model_name if active is not None else "unknown",
        )
        record_experiment_event(
            thread_id,
            "model.request_started",
            model_call_id=model_call_id,
            model_request_id=model_request_id,
            role=request_model_role(request),
            attempt=attempt,
            max_attempts=max_attempts,
            configured_model=configured_model,
            observed_endpoint=request_model_endpoint(request),
            request_timeout_seconds=(active.policy.request_timeout_seconds if active is not None else None),
            provider_max_retries=0 if active is not None else None,
        )
        return thread_id

    def _request_completed(
        self,
        thread_id: str | None,
        response: ModelCallResult,
        *,
        model_call_id: str,
        model_request_id: str,
        attempt: int,
        latency_seconds: float,
    ) -> None:
        actual_model, token_usage = model_response_metadata(response)
        record_experiment_event(
            thread_id,
            "model.request_completed",
            model_call_id=model_call_id,
            model_request_id=model_request_id,
            attempt=attempt,
            latency_seconds=round(latency_seconds, 6),
            status_code=None,
            actual_model=actual_model,
            token_usage=token_usage,
        )

    def _request_failed(
        self,
        thread_id: str | None,
        exc: BaseException,
        reason: str,
        *,
        model_call_id: str,
        model_request_id: str,
        attempt: int,
        max_attempts: int,
        latency_seconds: float,
        retriable: bool,
    ) -> str:
        classification = self._failure_classification(exc, reason)
        exhausted = retriable and attempt >= max_attempts
        record_experiment_event(
            thread_id,
            "model.request_failed",
            model_call_id=model_call_id,
            model_request_id=model_request_id,
            attempt=attempt,
            max_attempts=max_attempts,
            latency_seconds=round(latency_seconds, 6),
            status_code=_extract_status_code(exc),
            classification=classification,
            retriable=retriable,
            retry_exhausted=exhausted,
        )
        if not retriable or exhausted:
            record_experiment_event(
                thread_id,
                "failure.recorded",
                failure_id=new_evidence_id("failure"),
                model_call_id=model_call_id,
                model_request_id=model_request_id,
                domain="model_endpoint",
                classification=classification,
                primary=True,
                secondary_classifications=(["retry_exhausted"] if exhausted else []),
            )
        return classification

    def _emit_retry_event(self, attempt: int, wait_ms: int, reason: str) -> None:
        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
            writer(
                {
                    "type": "llm_retry",
                    "attempt": attempt,
                    "max_attempts": self.retry_max_attempts,
                    "wait_ms": wait_ms,
                    "reason": reason,
                    "message": self._build_retry_message(attempt, wait_ms, reason),
                }
            )
        except Exception:
            logger.debug("Failed to emit llm_retry event", exc_info=True)

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        model_call_id = new_evidence_id("model_call")
        max_attempts = self._effective_max_attempts(request)
        attempt = 1
        while True:
            model_request_id = new_evidence_id("model_request")
            thread_id = self._request_started(
                request,
                model_call_id=model_call_id,
                model_request_id=model_request_id,
                attempt=attempt,
                max_attempts=max_attempts,
            )
            started_monotonic = time.monotonic()
            try:
                response = handler(request)
                self._request_completed(
                    thread_id,
                    response,
                    model_call_id=model_call_id,
                    model_request_id=model_request_id,
                    attempt=attempt,
                    latency_seconds=time.monotonic() - started_monotonic,
                )
                return response
            except GraphBubbleUp:
                record_experiment_event(
                    thread_id,
                    "model.request_cancelled",
                    model_call_id=model_call_id,
                    model_request_id=model_request_id,
                    attempt=attempt,
                    classification="graph_control_flow",
                    latency_seconds=round(
                        time.monotonic() - started_monotonic,
                        6,
                    ),
                )
                # Preserve LangGraph control-flow signals (interrupt/pause/resume).
                raise
            except Exception as exc:
                retriable, reason = self._classify_error(exc)
                self._request_failed(
                    thread_id,
                    exc,
                    reason,
                    model_call_id=model_call_id,
                    model_request_id=model_request_id,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    latency_seconds=time.monotonic() - started_monotonic,
                    retriable=retriable,
                )
                if retriable and attempt < max_attempts:
                    wait_ms = self._build_retry_delay_ms(attempt, exc)
                    logger.warning(
                        "Transient LLM error on attempt %d/%d; retrying in %dms: %s",
                        attempt,
                        self.retry_max_attempts,
                        wait_ms,
                        _extract_error_detail(exc),
                    )
                    self._emit_retry_event(attempt, wait_ms, reason)
                    record_experiment_event(
                        thread_id,
                        "model.retry_scheduled",
                        model_call_id=model_call_id,
                        failed_model_request_id=model_request_id,
                        attempt=attempt,
                        next_attempt=attempt + 1,
                        wait_ms=wait_ms,
                        classification=self._failure_classification(exc, reason),
                    )
                    time.sleep(wait_ms / 1000)
                    attempt += 1
                    continue
                logger.warning(
                    "LLM call failed after %d attempt(s): %s",
                    attempt,
                    _extract_error_detail(exc),
                    exc_info=exc,
                )
                return AIMessage(content=self._build_user_message(exc, reason))

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        model_call_id = new_evidence_id("model_call")
        max_attempts = self._effective_max_attempts(request)
        attempt = 1
        while True:
            model_request_id = new_evidence_id("model_request")
            thread_id = self._request_started(
                request,
                model_call_id=model_call_id,
                model_request_id=model_request_id,
                attempt=attempt,
                max_attempts=max_attempts,
            )
            started_monotonic = time.monotonic()
            try:
                response = await handler(request)
                self._request_completed(
                    thread_id,
                    response,
                    model_call_id=model_call_id,
                    model_request_id=model_request_id,
                    attempt=attempt,
                    latency_seconds=time.monotonic() - started_monotonic,
                )
                return response
            except GraphBubbleUp:
                record_experiment_event(
                    thread_id,
                    "model.request_cancelled",
                    model_call_id=model_call_id,
                    model_request_id=model_request_id,
                    attempt=attempt,
                    classification="graph_control_flow",
                    latency_seconds=round(
                        time.monotonic() - started_monotonic,
                        6,
                    ),
                )
                # Preserve LangGraph control-flow signals (interrupt/pause/resume).
                raise
            except asyncio.CancelledError:
                record_experiment_event(
                    thread_id,
                    "model.request_cancelled",
                    model_call_id=model_call_id,
                    model_request_id=model_request_id,
                    attempt=attempt,
                    classification="cancelled",
                    latency_seconds=round(
                        time.monotonic() - started_monotonic,
                        6,
                    ),
                )
                raise
            except Exception as exc:
                retriable, reason = self._classify_error(exc)
                self._request_failed(
                    thread_id,
                    exc,
                    reason,
                    model_call_id=model_call_id,
                    model_request_id=model_request_id,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    latency_seconds=time.monotonic() - started_monotonic,
                    retriable=retriable,
                )
                if retriable and attempt < max_attempts:
                    wait_ms = self._build_retry_delay_ms(attempt, exc)
                    logger.warning(
                        "Transient LLM error on attempt %d/%d; retrying in %dms: %s",
                        attempt,
                        self.retry_max_attempts,
                        wait_ms,
                        _extract_error_detail(exc),
                    )
                    self._emit_retry_event(attempt, wait_ms, reason)
                    record_experiment_event(
                        thread_id,
                        "model.retry_scheduled",
                        model_call_id=model_call_id,
                        failed_model_request_id=model_request_id,
                        attempt=attempt,
                        next_attempt=attempt + 1,
                        wait_ms=wait_ms,
                        classification=self._failure_classification(exc, reason),
                    )
                    await asyncio.sleep(wait_ms / 1000)
                    attempt += 1
                    continue
                logger.warning(
                    "LLM call failed after %d attempt(s): %s",
                    attempt,
                    _extract_error_detail(exc),
                    exc_info=exc,
                )
                return AIMessage(content=self._build_user_message(exc, reason))


def _matches_any(detail: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in detail for pattern in patterns)


def _extract_error_code(exc: BaseException) -> Any:
    for attr in ("code", "error_code"):
        value = getattr(exc, attr, None)
        if value not in (None, ""):
            return value

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            for key in ("code", "type"):
                value = error.get(key)
                if value not in (None, ""):
                    return value
    return None


def _extract_status_code(exc: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _extract_retry_after_ms(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None

    raw = None
    header_name = ""
    for key in ("retry-after-ms", "Retry-After-Ms", "retry-after", "Retry-After"):
        header_name = key
        if hasattr(headers, "get"):
            raw = headers.get(key)
        if raw:
            break
    if not raw:
        return None

    try:
        multiplier = 1 if "ms" in header_name.lower() else 1000
        return max(0, int(float(raw) * multiplier))
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(str(raw))
            delta = target.timestamp() - time.time()
            return max(0, int(delta * 1000))
        except (TypeError, ValueError, OverflowError):
            return None


def _extract_error_detail(exc: BaseException) -> str:
    detail = str(exc).strip()
    if detail:
        return detail
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    return exc.__class__.__name__
