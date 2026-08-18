#!/usr/bin/env python3
"""为 checkpoint primary canary 提供 Windows bind 安全的 CMake 构建布局。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import Any

CMAKE_BINARY_DIR = ".forge-cmake-build"
BUILD_OUTPUT_RELATIVE_PATH = f"{CMAKE_BINARY_DIR}/accumulate_examples"
LEGACY_BUILD_OUTPUT_RELATIVE_PATH = "build/accumulate_examples"

_COMMAND_REWRITES = {
    "cmake -S examples -B build -DCMAKE_BUILD_TYPE=Release": (f"cmake -S examples -B {CMAKE_BINARY_DIR} -DCMAKE_BUILD_TYPE=Release"),
    "cmake --build build --target accumulate_examples -j2": (f"cmake --build {CMAKE_BINARY_DIR} --target accumulate_examples -j2"),
    "cp build/accumulate_examples /artifacts/accumulate_examples": (f"cp {BUILD_OUTPUT_RELATIVE_PATH} /artifacts/accumulate_examples"),
}


class BuildLayoutError(RuntimeError):
    """冻结 parent runner 与适配器的预期不一致。"""


def rewrite_parent_build_command(command: str) -> str:
    """只替换冻结 v1 runner 中已审计的三条 parent 构建命令。"""

    return _COMMAND_REWRITES.get(command, command)


@contextmanager
def use_windows_safe_build_layout(primary_canary: ModuleType) -> Iterator[ModuleType]:
    """在私有加载的 v1 runner 上临时应用新布局，并在退出时恢复。"""

    original_output = getattr(primary_canary, "BUILD_OUTPUT", None)
    original_record_command = getattr(primary_canary, "_record_command", None)
    if original_output != LEGACY_BUILD_OUTPUT_RELATIVE_PATH or not callable(original_record_command):
        raise BuildLayoutError("checkpoint primary canary v1 build layout drifted")

    def record_command(*args: Any, **kwargs: Any) -> Any:
        command = kwargs.get("command")
        if not isinstance(command, str):
            raise BuildLayoutError("parent build command must be passed by keyword")
        kwargs["command"] = rewrite_parent_build_command(command)
        return original_record_command(*args, **kwargs)

    primary_canary.BUILD_OUTPUT = BUILD_OUTPUT_RELATIVE_PATH
    primary_canary._record_command = record_command
    try:
        yield primary_canary
    finally:
        primary_canary.BUILD_OUTPUT = original_output
        primary_canary._record_command = original_record_command
