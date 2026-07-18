"""Public compile API with lazy imports for standalone evidence tooling."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "BuildArtifact": ("deerflow.compile.schemas", "BuildArtifact"),
    "BuildCommandRecord": ("deerflow.compile.schemas", "BuildCommandRecord"),
    "CommandResult": ("deerflow.compile.schemas", "CommandResult"),
    "CompileSession": ("deerflow.compile.schemas", "CompileSession"),
    "CompileSessionManager": (
        "deerflow.compile.manager",
        "CompileSessionManager",
    ),
    "get_compile_services": (
        "deerflow.compile.operations",
        "get_compile_services",
    ),
    "get_bound_session": ("deerflow.compile.operations", "get_bound_session"),
    "relative_or_original": (
        "deerflow.compile.operations",
        "relative_or_original",
    ),
    "prepare_compile_session_impl": (
        "deerflow.compile.operations",
        "prepare_compile_session_impl",
    ),
    "clone_repository_impl": (
        "deerflow.compile.operations",
        "clone_repository_impl",
    ),
    "inspect_build_system_impl": (
        "deerflow.compile.operations",
        "inspect_build_system_impl",
    ),
    "submit_build_result_impl": (
        "deerflow.compile.operations",
        "submit_build_result_impl",
    ),
    "finalize_compile_session_impl": (
        "deerflow.compile.operations",
        "finalize_compile_session_impl",
    ),
    "finalize_compile_session_json": (
        "deerflow.compile.operations",
        "finalize_compile_session_json",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
