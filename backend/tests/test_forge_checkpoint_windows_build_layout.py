from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
SCRIPTS_ROOT = REPO_ROOT / "scripts"
PRIMARY_SCRIPT = SCRIPTS_ROOT / "forge_checkpoint_primary_canary.py"
LAYOUT_SCRIPT = SCRIPTS_ROOT / "forge_checkpoint_windows_build_layout.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "manifests" / "cpp-verifier-checkpoint-primary-canary-authorized.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


primary = _load_module("forge_checkpoint_primary_canary_layout_test", PRIMARY_SCRIPT)
layout = _load_module("forge_checkpoint_windows_build_layout_test", LAYOUT_SCRIPT)


def test_frozen_v1_artifacts_remain_byte_identical() -> None:
    manifest = primary.load_manifest(MANIFEST_PATH)
    primary.verify_frozen_artifacts(manifest, REPO_ROOT)


def test_layout_adapter_rewrites_only_the_frozen_parent_commands() -> None:
    calls: list[str] = []

    def fake_record_command(*_args: Any, **kwargs: Any) -> str:
        calls.append(kwargs["command"])
        return kwargs["command"]

    original_record_command = primary._record_command
    primary._record_command = fake_record_command
    try:
        with layout.use_windows_safe_build_layout(primary):
            assert primary.BUILD_OUTPUT == ".forge-cmake-build/accumulate_examples"
            primary._record_command(command="cmake -S examples -B build -DCMAKE_BUILD_TYPE=Release")
            primary._record_command(command="cmake --build build --target accumulate_examples -j2")
            primary._record_command(command="cp build/accumulate_examples /artifacts/accumulate_examples")
            primary._record_command(command="git status --short")
        assert primary.BUILD_OUTPUT == "build/accumulate_examples"
        assert primary._record_command is fake_record_command
    finally:
        primary._record_command = original_record_command

    assert calls == [
        "cmake -S examples -B .forge-cmake-build -DCMAKE_BUILD_TYPE=Release",
        "cmake --build .forge-cmake-build --target accumulate_examples -j2",
        ("cp .forge-cmake-build/accumulate_examples /artifacts/accumulate_examples"),
        "git status --short",
    ]


def test_layout_updates_policy_and_fault_output_without_changing_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_before = primary.canonical_sha256(manifest)

    with layout.use_windows_safe_build_layout(primary):
        policy = primary._policy(
            manifest,
            arm="baseline",
            image_id="sha256:" + "1" * 64,
        )
        assert policy.artifact_instructions == (
            (
                "accumulate_examples",
                ".forge-cmake-build/accumulate_examples",
                "executable",
            ),
        )

    assert primary.canonical_sha256(manifest) == manifest_before
