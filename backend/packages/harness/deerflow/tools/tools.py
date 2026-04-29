import logging

from langchain.tools import BaseTool

from deerflow.config import get_app_config
from deerflow.reflection import resolve_variable
from deerflow.tools.bound_compile_tools import run_container_bash, submit_build_result
from deerflow.tools.host_read import host_read_tool
from deerflow.tools.host_write import host_write_tool
from deerflow.tools.builtins import (
    ask_clarification_tool,
    clone_repository,
    finalize_session,
    identify_build_system,
    prepare_compile_session,
    task_tool,
)
from deerflow.tools.builtins.tool_search import reset_deferred_registry

logger = logging.getLogger(__name__)

BUILTIN_TOOLS = [
    ask_clarification_tool,
]

COMPILE_TOOLS = [
    prepare_compile_session,
    clone_repository,
    identify_build_system,
    finalize_session,
]

BUILD_SUBAGENT_TOOLS = [
    run_container_bash,
    submit_build_result,
]

SUBAGENT_TOOLS = [
    task_tool,
    # task_status_tool is no longer exposed to LLM (backend handles polling internally)
]

HOST_TOOLS = [
    host_read_tool,
    host_write_tool,
]


def _load_configured_tools(groups: list[str] | None, model_name: str | None) -> tuple[list[BaseTool], list[BaseTool], list[BaseTool], list[BaseTool]]:
    config = get_app_config()
    tool_configs = [tool for tool in config.tools if groups is None or tool.group in groups]

    loaded_tools = [resolve_variable(tool.use, BaseTool) for tool in tool_configs]
    builtin_tools = BUILTIN_TOOLS.copy()
    builtin_tools.extend(HOST_TOOLS)
    builtin_tools.extend(COMPILE_TOOLS)

    skill_evolution_config = getattr(config, "skill_evolution", None)
    if getattr(skill_evolution_config, "enabled", False):
        from deerflow.tools.skill_manage_tool import skill_manage_tool

        builtin_tools.append(skill_manage_tool)

    if model_name is None and config.models:
        model_name = config.models[0].name

    mcp_tools = []
    reset_deferred_registry()
    try:
        from deerflow.config.extensions_config import ExtensionsConfig
        from deerflow.mcp.cache import get_cached_mcp_tools

        extensions_config = ExtensionsConfig.from_file()
        if extensions_config.get_enabled_mcp_servers():
            mcp_tools = get_cached_mcp_tools()
            if mcp_tools:
                logger.info(f"Using {len(mcp_tools)} cached MCP tool(s)")
                if config.tool_search.enabled:
                    from deerflow.tools.builtins.tool_search import DeferredToolRegistry, set_deferred_registry
                    from deerflow.tools.builtins.tool_search import tool_search as tool_search_tool

                    registry = DeferredToolRegistry()
                    for t in mcp_tools:
                        registry.register(t)
                    set_deferred_registry(registry)
                    builtin_tools.append(tool_search_tool)
                    logger.info(f"Tool search active: {len(mcp_tools)} tools deferred")
    except ImportError:
        logger.warning("MCP module not available. Install 'langchain-mcp-adapters' package to enable MCP tools.")
    except Exception as e:
        logger.error(f"Failed to get cached MCP tools: {e}")

    return loaded_tools, builtin_tools, mcp_tools


def get_available_tools(
    groups: list[str] | None = None,
    include_mcp: bool = True,
    model_name: str | None = None,
    subagent_enabled: bool = False,
) -> list[BaseTool]:
    loaded_tools, builtin_tools, mcp_tools = _load_configured_tools(groups, model_name)

    if subagent_enabled:
        builtin_tools = builtin_tools + SUBAGENT_TOOLS
        logger.info("Including subagent tools (task)")

    if not include_mcp:
        mcp_tools = []

    logger.info(
        f"Total tools loaded: {len(loaded_tools)}, built-in tools: {len(builtin_tools)}, MCP tools: {len(mcp_tools)}"
    )
    return loaded_tools + builtin_tools + mcp_tools


def get_subagent_tools(subagent_type: str, model_name: str | None = None) -> list[BaseTool]:
    loaded_tools, builtin_tools, mcp_tools = _load_configured_tools(groups=None, model_name=model_name)

    if subagent_type == "compiler":
        tools = BUILD_SUBAGENT_TOOLS.copy()
        logger.info("Providing build-and-submit tool set to compiler subagent")
        return tools

    return loaded_tools + builtin_tools + mcp_tools
