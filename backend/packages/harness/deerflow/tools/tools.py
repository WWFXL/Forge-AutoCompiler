import logging

from langchain.tools import BaseTool

from deerflow.config import get_app_config
from deerflow.reflection import resolve_variable
from deerflow.sandbox.security import is_host_bash_allowed
from deerflow.tools.builtins import ask_clarification_tool, present_file_tool, run_compile_workflow, task_tool, view_image_tool
from deerflow.tools.builtins.compile_tools import clone_repository, finalize_compile_session, inspect_build_system, prepare_compile_session, run_compile_command, verify_build_artifacts
from deerflow.tools.builtins.tool_search import reset_deferred_registry

logger = logging.getLogger(__name__)

BUILTIN_TOOLS = [
    present_file_tool,
    ask_clarification_tool,
    run_compile_workflow,
]

COMPILE_TOOLS = [
    prepare_compile_session,
    clone_repository,
    inspect_build_system,
    run_compile_command,
    verify_build_artifacts,
    finalize_compile_session,
]

BUILD_SUBAGENT_TOOLS = [
    run_compile_command,
]

SUBAGENT_TOOLS = [
    task_tool,
    # task_status_tool is no longer exposed to LLM (backend handles polling internally)
]


def _is_host_bash_tool(tool: object) -> bool:
    """Return True if the tool config represents a host-bash execution surface."""
    group = getattr(tool, "group", None)
    use = getattr(tool, "use", None)
    if group == "bash":
        return True
    if use == "deerflow.sandbox.tools:bash_tool":
        return True
    return False


def _load_configured_tools(groups: list[str] | None, model_name: str | None) -> tuple[list[BaseTool], list[BaseTool], list[BaseTool], list[BaseTool]]:
    config = get_app_config()
    tool_configs = [tool for tool in config.tools if groups is None or tool.group in groups]

    if not is_host_bash_allowed(config):
        tool_configs = [tool for tool in tool_configs if not _is_host_bash_tool(tool)]

    loaded_tools = [resolve_variable(tool.use, BaseTool) for tool in tool_configs]
    builtin_tools = BUILTIN_TOOLS.copy()

    skill_evolution_config = getattr(config, "skill_evolution", None)
    if getattr(skill_evolution_config, "enabled", False):
        from deerflow.tools.skill_manage_tool import skill_manage_tool

        builtin_tools.append(skill_manage_tool)

    if model_name is None and config.models:
        model_name = config.models[0].name

    model_config = config.get_model_config(model_name) if model_name else None
    if model_config is not None and model_config.supports_vision:
        builtin_tools.append(view_image_tool)
        logger.info(f"Including view_image_tool for model '{model_name}' (supports_vision=True)")

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

    acp_tools: list[BaseTool] = []
    try:
        from deerflow.config.acp_config import get_acp_agents
        from deerflow.tools.builtins.invoke_acp_agent_tool import build_invoke_acp_agent_tool

        acp_agents = get_acp_agents()
        if acp_agents:
            acp_tools.append(build_invoke_acp_agent_tool(acp_agents))
            logger.info(f"Including invoke_acp_agent tool ({len(acp_agents)} agent(s): {list(acp_agents.keys())})")
    except Exception as e:
        logger.warning(f"Failed to load ACP tool: {e}")

    return loaded_tools, builtin_tools, mcp_tools, acp_tools


def get_available_tools(
    groups: list[str] | None = None,
    include_mcp: bool = True,
    model_name: str | None = None,
    subagent_enabled: bool = False,
) -> list[BaseTool]:
    loaded_tools, builtin_tools, mcp_tools, acp_tools = _load_configured_tools(groups, model_name)

    if subagent_enabled:
        builtin_tools = builtin_tools + SUBAGENT_TOOLS
        logger.info("Including subagent tools (task)")

    if not include_mcp:
        mcp_tools = []

    logger.info(
        f"Total tools loaded: {len(loaded_tools)}, built-in tools: {len(builtin_tools)}, MCP tools: {len(mcp_tools)}, ACP tools: {len(acp_tools)}"
    )
    return loaded_tools + builtin_tools + mcp_tools + acp_tools


def get_subagent_tools(subagent_type: str, model_name: str | None = None) -> list[BaseTool]:
    loaded_tools, builtin_tools, mcp_tools, acp_tools = _load_configured_tools(groups=None, model_name=model_name)

    if subagent_type == "compiler":
        tools = BUILD_SUBAGENT_TOOLS.copy()
        logger.info("Providing build-only tool set to compiler subagent")
        return tools

    return loaded_tools + builtin_tools + mcp_tools + acp_tools
