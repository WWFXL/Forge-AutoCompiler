"""Issue #294 Phase 5 v2 build-system qualification 测试。"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_agent_workflow_stage_b_phase5_v2_qualification_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_agent_workflow_stage_b_phase5_v2_qualification_runner.py"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module("forge_agent_workflow_stage_b_phase5_v2_qualification_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_agent_workflow_stage_b_phase5_v2_qualification_runner_test", RUNNER_PATH)


def _result(plan: dict) -> dict:
    tasks = []
    for task in plan["tasks"]:
        capabilities = ["cmake", "make", "autotools"] if task["task_id"] == "c-ares" else [task["historical_build_system_label"]]
        tasks.append(
            {
                **task,
                "build_system_capabilities": capabilities,
                "selected_build_system": capabilities[0],
                "cleanup_succeeded": True,
            }
        )
    return {
        "schema_version": protocol.RESULT_SCHEMA_VERSION,
        "document_type": protocol.RESULT_DOCUMENT_TYPE,
        "status": "passed",
        "qualification_plan_sha256": protocol.canonical_sha256(plan),
        "release_revision": "a" * 40,
        "image": plan["environment"]["compile_image"],
        "image_id": plan["environment"]["image_id"],
        "provider_request_count": 0,
        "model_created": False,
        "formal_attempt_created": False,
        "zero_managed_resources_before": True,
        "zero_managed_resources_after": True,
        "tasks": tasks,
    }


def test_qualification_plan_and_schema_are_deterministic() -> None:
    plan = protocol.generate_plan(REPO_ROOT)
    schema = protocol.generate_schema(plan)

    assert protocol.load_plan(repo_root=REPO_ROOT) == plan
    assert plan["authorization"]["provider_calls_authorized"] is False
    assert plan["authorization"]["docker_qualification_execution_owner"] == "user"
    assert [task["task_id"] for task in plan["tasks"]] == ["yyjson", "cppitertools", "openh264", "uwebsockets", "c-ares", "libass"]
    assert schema["const"] == plan


def test_qualification_result_freezes_capabilities_and_selection() -> None:
    plan = protocol.generate_plan(REPO_ROOT)
    result = _result(plan)

    assert protocol.validate_result(result, plan) == result
    c_ares = next(task for task in result["tasks"] if task["task_id"] == "c-ares")
    assert c_ares["selected_build_system"] == "cmake"

    drifted = copy.deepcopy(result)
    drifted["tasks"][0]["selected_build_system"] = "autotools"
    with pytest.raises(protocol.Phase5V2QualificationError, match="qualification"):
        protocol.validate_result(drifted, plan)


def test_qualify_task_uses_exact_commit_and_always_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = protocol.generate_plan(REPO_ROOT)
    task = plan["tasks"][0]
    session = SimpleNamespace(
        image=plan["environment"]["compile_image"],
        image_id=plan["environment"]["image_id"],
        commit_sha=task["commit_sha"],
        build_system_capabilities=["cmake", "make"],
        session_id="session-qualification",
        metadata_path="/tmp/session.json",
    )
    clone_calls: list[dict] = []
    cleanup_calls: list[dict] = []
    monkeypatch.setattr(runner, "prepare_compile_session_impl", lambda **_kwargs: session)

    def clone(**kwargs):
        clone_calls.append(kwargs)
        return SimpleNamespace(exit_code=0), "ok"

    monkeypatch.setattr(runner, "clone_repository_impl", clone)
    monkeypatch.setattr(runner, "inspect_build_system_impl", lambda **_kwargs: ("cmake", [("cmake", "CMakeLists.txt"), ("make", "Makefile")], ["cmake -S . -B build"]))

    def cleanup(**kwargs):
        cleanup_calls.append(kwargs)
        return session, SimpleNamespace(succeeded=True)

    monkeypatch.setattr(runner, "cleanup_and_finalize_compile_session_impl", cleanup)
    monkeypatch.setattr(runner, "require_zero_managed_resources", lambda: None)

    result = runner._qualify_task(plan, task)

    assert clone_calls[0]["commit_sha"] == task["commit_sha"]
    assert result["build_system_capabilities"] == ["cmake", "make"]
    assert result["selected_build_system"] == "cmake"
    assert cleanup_calls[0]["interrupted_status"] == "cancelled"
