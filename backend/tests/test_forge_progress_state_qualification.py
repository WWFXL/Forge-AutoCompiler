"""Issue #382 跨构建系统进展状态资格审计测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_progress_state_qualification.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "forge_progress_state_qualification_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


qualification = _load_module()


def _command(
    role: str,
    exit_code: int,
    *,
    timed_out: bool = False,
    termination: str = "completed",
) -> dict:
    return {
        "role": role,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "termination": termination,
    }


def test_make_configuration_is_explicitly_not_applicable() -> None:
    state = qualification.initial_state("make", "a" * 40)

    assert state.obligations["source_available"] == "verified"
    assert state.obligations["configuration_generated"] == "not_applicable"
    assert qualification.frontier_obligation(state) == "toolchain_ready"


def test_transition_semantics_cover_progress_lateral_stagnation_and_regression() -> None:
    initial = qualification.initial_state("cmake", "a" * 40)

    configured = qualification.apply_command(
        initial,
        _command("configure", 0),
        "",
    )
    assert qualification.classify_transition(initial, configured) == "progress"

    diagnosed = qualification.apply_command(
        initial,
        _command("diagnostic", 1),
        "unexpected diagnostic failure",
    )
    assert qualification.classify_transition(initial, diagnosed) == "lateral"

    unchanged = qualification.apply_command(
        initial,
        _command("diagnostic", 0),
        "inspection completed",
    )
    assert qualification.classify_transition(initial, unchanged) == "stagnation"

    built = qualification.apply_command(
        configured,
        _command("build", 0),
        "",
    )
    failed_rebuild = qualification.apply_command(
        built,
        _command("build", 2),
        "compiler error: build failed",
    )
    assert qualification.classify_transition(built, failed_rebuild) == "regression"
    assert failed_rebuild.obligations["contract_target_built"] == "invalidated"


def test_policy_rejection_does_not_invalidate_but_timeout_does() -> None:
    initial = qualification.initial_state("autotools", "b" * 40)
    built = qualification.apply_command(
        initial,
        _command("build", 0),
        "",
    )
    staged = qualification.apply_command(
        built,
        _command("artifact_stage", 0),
        "",
    )

    rejected = qualification.apply_command(
        staged,
        _command("build", 126, termination="policy_rejected"),
        "command rejected by policy",
    )
    assert rejected.obligations == staged.obligations
    assert qualification.classify_transition(staged, rejected) == "lateral"

    timed_out = qualification.apply_command(
        staged,
        _command("build", 124, timed_out=True, termination="timeout"),
        "",
    )
    assert timed_out.obligations["contract_target_built"] == "invalidated"
    assert timed_out.obligations["artifacts_staged"] == "invalidated"
    assert qualification.classify_transition(staged, timed_out) == "regression"


@pytest.mark.parametrize(
    ("role", "exit_code", "log_text", "expected"),
    [
        ("build", 0, "warning only", "none"),
        ("build", 124, "", "timeout"),
        ("build", 126, "policy rejected", "policy_rejected"),
        ("dependency", 1, "command not found", "dependency_missing"),
        ("configure", 1, "CMake Error at x", "configuration_error"),
        ("build", 1, "foo.cc:1: error: bad", "compile_error"),
        ("build", 1, "undefined reference to x", "link_error"),
        ("build", 2, "No rule to make target x", "target_error"),
        ("artifact_stage", 1, "cp: cannot stat x", "artifact_error"),
        ("smoke", 1, "assertion failed", "test_error"),
        ("diagnostic", 1, "opaque failure", "unknown_error"),
    ],
)
def test_diagnostic_classification_is_deterministic(
    role: str,
    exit_code: int,
    log_text: str,
    expected: str,
) -> None:
    command = _command(role, exit_code, timed_out=exit_code == 124)
    assert qualification.classify_diagnostic(command, log_text.lower()) == expected


def test_allowed_session_projection_discards_command_text_and_hidden_results(
    tmp_path: Path,
) -> None:
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps(
            {
                "repo_url": "https://github.com/example/project.git",
                "commit_sha": "a" * 40,
                "build_system": "cmake",
                "created_at": "2026-10-09T00:00:00+00:00",
                "verification": {"hidden_answer": "do-not-read"},
                "artifacts": [{"path": "hidden"}],
                "commands": [
                    {
                        "command_id": "command-1",
                        "command": "ground-truth patch text",
                        "role": "build",
                        "exit_code": 0,
                        "log_path": "logs/command-1.log",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    projected = qualification._read_allowed_session(path)

    assert set(projected) == set(qualification.SESSION_KEYS)
    assert set(projected["commands"][0]) == set(qualification.COMMAND_KEYS)
    assert "command" not in projected["commands"][0]
    assert "verification" not in projected
    assert "artifacts" not in projected


def test_model_feature_sets_exclude_identity_and_current_outcome() -> None:
    forbidden = {
        "project_family",
        "repo_url",
        "commit_sha",
        "session_path",
        "attempt_id",
        "created_at",
        "exit_code",
        "after_diagnostic_category",
        "transition",
    }
    for name in qualification.NUMERIC_FEATURES:
        features = {
            *qualification.NUMERIC_FEATURES[name],
            *qualification.CATEGORICAL_FEATURES[name],
        }
        assert not features & forbidden
        assert "next_action_role" in features


def test_fixed_logistic_pipeline_returns_four_aligned_probabilities() -> None:
    rows = []
    for index, transition in enumerate(qualification.TRANSITIONS * 3):
        row = {
            "turn_index": index + 1,
            "commands_used": index,
            "wall_clock_seconds_used": float(index),
            "model_requests_used": index // 2,
            "recorded_tokens_used": index * 100,
            "build_system": qualification.BUILD_SYSTEMS[index % 3],
            "next_action_role": qualification.ELIGIBLE_ROLES[index % 6],
            "prior_error_category": qualification.DIAGNOSTIC_CATEGORIES[index % 4],
            "transition": transition,
        }
        rows.append(row)
    development = pd.DataFrame(rows[:8])
    evaluation = pd.DataFrame(rows[8:])

    probabilities, features = qualification._fit_model(
        "simple_combined",
        development,
        evaluation,
    )

    assert features == [
        *qualification.NUMERIC_FEATURES["simple_combined"],
        *qualification.CATEGORICAL_FEATURES["simple_combined"],
    ]
    assert probabilities.shape == (4, 4)
    assert np.allclose(probabilities.sum(axis=1), 1.0)


@pytest.mark.skipif(
    not qualification.DEFAULT_SESSIONS_ROOT.is_dir(),
    reason="本机未挂载只读历史 Compile Session",
)
def test_local_input_inventory_matches_frozen_corpus_shape() -> None:
    manifest = qualification.generate_input_manifest()

    assert manifest["summary"]["session_count"] == 30
    assert manifest["summary"]["development_session_count"] == 6
    assert manifest["summary"]["evaluation_session_count"] == 24
    assert manifest["summary"]["development_project_family_count"] == 6
    assert manifest["summary"]["evaluation_project_family_count"] == 12
    assert manifest["summary"]["evaluation_project_families_by_build_system"] == {
        "cmake": 6,
        "make": 3,
        "autotools": 3,
    }


@pytest.mark.skipif(
    not qualification.DEFAULT_SESSIONS_ROOT.is_dir() or not qualification.DEFAULT_MANIFEST.is_file() or not qualification.DEFAULT_MANUAL_AUDIT.is_file(),
    reason="本机未同时挂载只读历史 Session 与资格审计输入",
)
def test_local_manifest_and_manual_audit_are_deterministically_rebuilt() -> None:
    committed_manifest = qualification.load_json(
        qualification.DEFAULT_MANIFEST,
        "input manifest",
    )
    assert qualification.generate_input_manifest() == committed_manifest

    committed_manual = qualification.load_json(
        qualification.DEFAULT_MANUAL_AUDIT,
        "manual audit",
    )
    regenerated_manual = qualification.generate_manual_audit_template(committed_manifest)
    committed_without_annotations = json.loads(json.dumps(committed_manual))
    for item in committed_without_annotations["annotations"]:
        item["annotation"] = None
    assert regenerated_manual == committed_without_annotations

    rows = qualification.extract_all_rows(committed_manifest)
    audit = qualification.evaluate_manual_audit(committed_manual, rows)
    assert audit == {
        "item_count": 12,
        "obligation_field_count": 216,
        "obligation_agreement": 1.0,
        "diagnostic_agreement": 1.0,
        "transition_agreement": 1.0,
        "passed": True,
        "mismatches": [],
    }


@pytest.mark.skipif(
    not qualification.DEFAULT_SESSIONS_ROOT.is_dir()
    or not qualification.DEFAULT_MANIFEST.is_file()
    or not qualification.DEFAULT_MANUAL_AUDIT.is_file()
    or not qualification.DEFAULT_JSON_REPORT.is_file()
    or not qualification.DEFAULT_MARKDOWN_REPORT.is_file(),
    reason="本机未同时挂载只读历史 Session 与资格审计报告",
)
def test_committed_reports_are_deterministically_rebuilt() -> None:
    expected = qualification.build_report()
    committed = qualification.load_json(
        qualification.DEFAULT_JSON_REPORT,
        "qualification report",
    )

    assert expected == committed
    assert qualification.render_markdown(expected) == qualification.DEFAULT_MARKDOWN_REPORT.read_text(encoding="utf-8")


def test_analysis_source_has_no_runtime_or_network_execution_path() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "create_chat_model",
        "run_container_bash",
        "subprocess",
        "requests.",
        "httpx.",
        "docker",
        "chmod(",
        "chown(",
    ):
        assert forbidden not in source
