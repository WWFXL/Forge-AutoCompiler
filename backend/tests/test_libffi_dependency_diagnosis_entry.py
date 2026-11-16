"""只验证新单次入口与参数装配，不调用Provider或重复构建。"""

import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deerflow.compile.recovery_harness import RecoveryHarness
from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
entry = importlib.import_module("forge_libffi_dependency_diagnosis")


def auth():
    return dict(identity=entry.IDENTITY, maximum_cost_usd="1.00", user_authorized=True, deadline_utc=(datetime.now(UTC) + timedelta(minutes=45)).isoformat())


def material(monkeypatch):
    data = json.loads((entry.ROOT / "benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json").read_text())
    item = next(p for p in data["projects"] if p["name"] == "libffi")
    recovery = RecoveryHarness.model_validate_json((entry.ROOT / "benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/candidate.json").read_text())
    monkeypatch.setattr(entry, "previous_material", lambda: (PublicBuildTask.model_validate(item["task"]), BuildReference.model_validate(item["reference"]), Path("unused.tar"), recovery))


def test_new_identity_requires_current_one_run_authorization():
    entry.validate_authorization(auth())
    with pytest.raises(ValueError, match="授权"):
        entry.validate_authorization({**auth(), "identity": "cpp-build-libffi-diagnostic-memory-flash-v1"})
    with pytest.raises(ValueError, match="授权"):
        entry.validate_authorization({**auth(), "deadline_utc": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()})


def test_default_only_checks_material_without_provider(monkeypatch, capsys):
    material(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["entry"])

    def forbidden(*args, **kwargs):
        pytest.fail("默认入口不能调用Provider或Docker")

    monkeypatch.setattr(entry, "PlanThinkingDeepSeek", forbidden)
    monkeypatch.setattr(entry.subprocess, "run", forbidden)
    entry.main()
    result = json.loads(capsys.readouterr().out)
    assert result["identity"] == entry.IDENTITY and result["credentials_read"] is False
    assert result["provider_calls"] == 0 and result["task"]["image_id"] == entry.IMAGE_ID


def test_run_wiring_enables_diagnosis_without_answers_or_retry(monkeypatch, tmp_path):
    import dotenv

    material(monkeypatch)
    value = {**auth(), "credentials_env_file": "unused.env"}
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(value))
    out = tmp_path / "attempt"
    monkeypatch.setattr(sys, "argv", ["entry", "--authorization", str(path), "--output", str(out)])
    monkeypatch.setattr(entry.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(entry.subprocess, "check_output", lambda *args, **kwargs: "a" * 40)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unit-test-placeholder")
    calls = {}
    monkeypatch.setattr(entry, "PlanThinkingDeepSeek", lambda **kwargs: calls.setdefault("model", kwargs))
    monkeypatch.setattr(entry, "run_simple_system", lambda **kwargs: (calls.update(run=kwargs) or dict(status="scripted_only")))
    entry.main()
    assert calls["model"]["model"] == "deepseek-flash" and calls["model"]["max_retries"] == 0
    run = calls["run"]
    assert run["diagnose_dependencies"] and run["retain_recovery_diagnostics"] and run["enforce_planning_tools"]
    assert run["maximum_cost_usd"] == "1.00" and run["validation_scope"] == "main_build"
    assert "initial_plan" not in run and "bank" not in run and "recipe" not in run
    scope = json.loads((out / "scope.json").read_text())
    assert scope["dependency_diagnosis"] == "dependency-diagnosis-v1"
    assert scope["project_specific_hint"] is None and scope["experience_bank"] is None
    assert not scope["automatic_retries"] and scope["attempts"] == 1
