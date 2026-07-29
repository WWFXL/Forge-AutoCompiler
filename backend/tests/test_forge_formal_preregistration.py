from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "forge_formal_preregistration.py"
MANIFEST = ROOT / "benchmarks" / "preregistrations" / "cpp-formal-v1.json"


def _module():
    spec = importlib.util.spec_from_file_location("forge_formal_preregistration", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def preregistration_module():
    return _module()


@pytest.fixture
def protocol():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_committed_preregistration_is_valid_and_does_not_authorize_collection(preregistration_module, protocol):
    summary = preregistration_module.validate_preregistration(protocol)

    assert summary["valid"] is True
    assert summary["projects"] == 30
    assert summary["conditions"] == 2
    assert summary["planned_attempts"] == 180
    assert summary["collection_authorized"] is False
    assert len(summary["canonical_sha256"]) == 64
    assert len(summary["schedule_sha256"]) == 64


def test_each_build_system_has_three_small_four_medium_three_large(preregistration_module, protocol):
    summary = preregistration_module.validate_preregistration(protocol)

    assert summary["strata"] == {
        "cmake-small": 3,
        "cmake-medium": 4,
        "cmake-large": 3,
        "make-small": 3,
        "make-medium": 4,
        "make-large": 3,
        "autotools-small": 3,
        "autotools-medium": 4,
        "autotools-large": 3,
    }


def test_schedule_is_deterministic_complete_and_serial(preregistration_module, protocol):
    first = preregistration_module.build_schedule(protocol)
    second = preregistration_module.build_schedule(copy.deepcopy(protocol))

    assert first == second
    assert [slot["order"] for slot in first] == list(range(1, 181))
    assert len({(slot["case_id"], slot["condition_id"], slot["repetition"]) for slot in first}) == 180
    assert {slot["repetition"] for slot in first} == {1, 2, 3}
    assert preregistration_module.canonical_sha256(first) == protocol["design"]["schedule_sha256"]


def test_exact_project_sign_flip_matches_known_extremes(preregistration_module):
    all_ties = preregistration_module.exact_project_sign_flip([0] * 30)
    all_deepseek = preregistration_module.exact_project_sign_flip([3] * 30)

    assert all_ties["deepseek_minus_richlab"] == 0
    assert all_ties["exact_two_sided_p_value"] == 1
    assert all_deepseek["deepseek_minus_richlab"] == 1
    assert all_deepseek["exact_two_sided_p_value"] == 2 / (2**30)
    assert all_deepseek["assignment_count"] == 2**30


def test_exact_project_sign_flip_rejects_wrong_shape(preregistration_module):
    with pytest.raises(preregistration_module.PreregistrationError, match="30 project"):
        preregistration_module.exact_project_sign_flip([1] * 29)

    with pytest.raises(preregistration_module.PreregistrationError, match="integers from -3 to 3"):
        preregistration_module.exact_project_sign_flip([1] * 29 + [4])


def test_case_replacement_or_duplicate_repository_is_rejected(preregistration_module, protocol):
    protocol["cases"][0]["repository_url"] = protocol["cases"][1]["repository_url"]

    with pytest.raises(preregistration_module.PreregistrationError, match="Repositories"):
        preregistration_module.validate_preregistration(protocol)


def test_selection_hash_drift_is_rejected(preregistration_module, protocol):
    protocol["cases"][0]["commit"] = "0" * 40

    with pytest.raises(preregistration_module.PreregistrationError, match="Selection hash"):
        preregistration_module.validate_preregistration(protocol)


def test_size_stratum_drift_is_rejected(preregistration_module, protocol):
    protocol["cases"][0]["repository_size_kib"] = 100

    with pytest.raises(preregistration_module.PreregistrationError, match="Size stratum"):
        preregistration_module.validate_preregistration(protocol)


def test_retry_fallback_and_collection_authorization_are_rejected(preregistration_module, protocol):
    for mutation, message in (
        (
            lambda value: value["conditions"][0].update(provider_retries=1),
            "Fallback and provider retry",
        ),
        (
            lambda value: value["conditions"][0].update(fallback_policy="allowed"),
            "Fallback and provider retry",
        ),
        (
            lambda value: value["preregistration"].update(collection_authorized=True),
            "must not authorize collection",
        ),
    ):
        candidate = copy.deepcopy(protocol)
        mutation(candidate)
        with pytest.raises(preregistration_module.PreregistrationError, match=message):
            preregistration_module.validate_preregistration(candidate)


def test_secret_like_values_are_rejected(preregistration_module, protocol):
    protocol["conditions"][0]["credential_env"] = "sk-" + "not-a-real-secret-value"

    with pytest.raises(preregistration_module.PreregistrationError, match="Secret-like"):
        preregistration_module.validate_preregistration(protocol)


def test_unsafe_repository_url_is_rejected(preregistration_module, protocol):
    protocol["cases"][0]["repository_url"] = "https://token@github.com/PowerDNS/pdns?secret=value"

    with pytest.raises(preregistration_module.PreregistrationError, match="forbidden"):
        preregistration_module.validate_preregistration(protocol)


def test_resource_projection_matches_v8_linear_scale(protocol):
    projection = protocol["resource_projection_from_v8"]

    assert projection["planned_attempts"] / projection["reference_attempts"] == 18
    assert projection["linear_projected_tokens"] == 1_306_532 * 18
    assert projection["linear_projected_wall_clock_seconds"] == pytest.approx(5_008.122 * 18)
    assert projection["linear_projected_model_requests"] == 191 * 18


def test_source_frame_exclusion_is_pre_data_and_replaced(protocol):
    exclusion = protocol["source_frame"]["pre_collection_exclusions"][0]
    case_ids = {case["id"] for case in protocol["cases"]}

    assert exclusion["source_project_id"] == "esp-v2"
    assert exclusion["replacement_case_id"] == "fio"
    assert exclusion["timing"] == "before any formal model request"
    assert "esp-v2" not in case_ids
    assert "fio" in case_ids


def test_cli_validate_and_schedule(preregistration_module, tmp_path, capsys, protocol):
    path = tmp_path / "preregistration.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")

    assert preregistration_module.main(["validate", "--preregistration", str(path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["valid"] is True

    assert preregistration_module.main(["schedule", "--preregistration", str(path)]) == 0
    schedule = json.loads(capsys.readouterr().out)
    assert len(schedule) == 180


def test_cli_rejects_invalid_document(preregistration_module, tmp_path, capsys, protocol):
    protocol["cases"].pop()
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")

    assert preregistration_module.main(["validate", "--preregistration", str(path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert "30 projects" in result["error"]
