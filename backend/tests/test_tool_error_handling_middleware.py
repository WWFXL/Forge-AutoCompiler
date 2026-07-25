from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphInterrupt

from deerflow.agents.middlewares import tool_error_handling_middleware
from deerflow.agents.middlewares.tool_error_handling_middleware import ToolErrorHandlingMiddleware


def _request(name: str = "web_search", tool_call_id: str | None = "tc-1"):
    tool_call = {"name": name}
    if tool_call_id is not None:
        tool_call["id"] = tool_call_id
    return SimpleNamespace(tool_call=tool_call)


def test_wrap_tool_call_passthrough_on_success():
    middleware = ToolErrorHandlingMiddleware()
    req = _request()
    expected = ToolMessage(content="ok", tool_call_id="tc-1", name="web_search")

    result = middleware.wrap_tool_call(req, lambda _req: expected)

    assert result is expected


def test_wrap_tool_call_returns_error_tool_message_on_exception():
    middleware = ToolErrorHandlingMiddleware()
    req = _request(name="web_search", tool_call_id="tc-42")

    def _boom(_req):
        raise RuntimeError("network down")

    result = middleware.wrap_tool_call(req, _boom)

    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "tc-42"
    assert result.name == "web_search"
    assert result.status == "error"
    assert "Tool 'web_search' failed" in result.text
    assert "network down" in result.text


def test_wrap_tool_call_records_bounded_failure_identity(monkeypatch):
    middleware = ToolErrorHandlingMiddleware()
    req = _request(name="task", tool_call_id="tc-evidence")
    recorded: list[tuple[object, Exception, str]] = []

    monkeypatch.setattr(
        tool_error_handling_middleware,
        "record_agent_tool_failure",
        lambda request, exc, *, execution_mode: recorded.append((request, exc, execution_mode)),
    )

    def _boom(_req):
        raise RuntimeError("must not be passed as evidence payload")

    middleware.wrap_tool_call(req, _boom)

    assert len(recorded) == 1
    assert recorded[0][0] is req
    assert type(recorded[0][1]) is RuntimeError
    assert recorded[0][2] == "sync"


def test_wrap_tool_call_uses_fallback_tool_call_id_when_missing():
    middleware = ToolErrorHandlingMiddleware()
    req = _request(name="mcp_tool", tool_call_id=None)

    def _boom(_req):
        raise ValueError("bad request")

    result = middleware.wrap_tool_call(req, _boom)

    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "missing_tool_call_id"
    assert result.name == "mcp_tool"
    assert result.status == "error"


def test_wrap_tool_call_reraises_graph_interrupt():
    middleware = ToolErrorHandlingMiddleware()
    req = _request(name="ask_clarification", tool_call_id="tc-int")

    def _interrupt(_req):
        raise GraphInterrupt(())

    with pytest.raises(GraphInterrupt):
        middleware.wrap_tool_call(req, _interrupt)


@pytest.mark.anyio
async def test_awrap_tool_call_returns_error_tool_message_on_exception():
    middleware = ToolErrorHandlingMiddleware()
    req = _request(name="mcp_tool", tool_call_id="tc-async")

    async def _boom(_req):
        raise TimeoutError("request timed out")

    result = await middleware.awrap_tool_call(req, _boom)

    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "tc-async"
    assert result.name == "mcp_tool"
    assert result.status == "error"
    assert "request timed out" in result.text


@pytest.mark.anyio
async def test_awrap_tool_call_records_async_failure_identity(monkeypatch):
    middleware = ToolErrorHandlingMiddleware()
    req = _request(name="task", tool_call_id="tc-async-evidence")
    recorded: list[tuple[object, Exception, str]] = []

    monkeypatch.setattr(
        tool_error_handling_middleware,
        "record_agent_tool_failure",
        lambda request, exc, *, execution_mode: recorded.append((request, exc, execution_mode)),
    )

    async def _boom(_req):
        raise TimeoutError("must not be passed as evidence payload")

    await middleware.awrap_tool_call(req, _boom)

    assert len(recorded) == 1
    assert recorded[0][0] is req
    assert type(recorded[0][1]) is TimeoutError
    assert recorded[0][2] == "async"


@pytest.mark.anyio
async def test_awrap_tool_call_reraises_graph_interrupt():
    middleware = ToolErrorHandlingMiddleware()
    req = _request(name="ask_clarification", tool_call_id="tc-int-async")

    async def _interrupt(_req):
        raise GraphInterrupt(())

    with pytest.raises(GraphInterrupt):
        await middleware.awrap_tool_call(req, _interrupt)
