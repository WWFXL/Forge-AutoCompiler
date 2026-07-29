from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "forge_formal_case_protocol.py"
PROTOCOL = ROOT / "benchmarks" / "preregistrations" / "cpp-formal-v1-cases.json"
PREREGISTRATION = ROOT / "benchmarks" / "preregistrations" / "cpp-formal-v1.json"
MARKDOWN = ROOT / "benchmarks" / "preregistrations" / "cpp-formal-v1-cases.md"


def _module():
    spec = importlib.util.spec_from_file_location("forge_formal_case_protocol", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def case_protocol_module():
    return _module()


@pytest.fixture
def protocol():
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


@pytest.fixture
def preregistration():
    return json.loads(PREREGISTRATION.read_text(encoding="utf-8"))


def test_committed_case_protocol_is_complete_result_blind_and_not_authorized(case_protocol_module, protocol, preregistration):
    summary = case_protocol_module.validate_protocol(protocol, preregistration)

    assert summary["valid"] is True
    assert summary["cases"] == 30
    assert summary["artifact_oracles"] == 30
    assert summary["unique_evidence_urls"] == 77
    assert summary["collection_authorized"] is False
    assert summary["case_protocol_sha256"] == protocol["protocolization"]["case_protocol_sha256"]
    assert all(case["review_state"] == "reviewed" for case in protocol["cases"])
    assert all(case["result_data_consulted"] is False for case in protocol["cases"])


def test_case_set_and_strata_remain_equal_to_preregistration(case_protocol_module, protocol, preregistration):
    summary = case_protocol_module.validate_protocol(protocol, preregistration)

    assert {case["id"] for case in protocol["cases"]} == {case["id"] for case in preregistration["cases"]}
    assert summary["strata"] == {
        "autotools-large": 3,
        "autotools-medium": 4,
        "autotools-small": 3,
        "cmake-large": 3,
        "cmake-medium": 4,
        "cmake-small": 3,
        "make-large": 3,
        "make-medium": 4,
        "make-small": 3,
    }


@pytest.mark.parametrize("field", ["repository_url", "commit", "build_system"])
def test_preregistered_identity_drift_is_rejected(case_protocol_module, protocol, preregistration, field):
    replacements = {
        "repository_url": "https://github.com/example/repository",
        "commit": "0" * 40,
        "build_system": "make",
    }
    protocol["cases"][0][field] = replacements[field]

    with pytest.raises(case_protocol_module.CaseProtocolError, match=f"{field} drifted"):
        case_protocol_module.validate_protocol(protocol, preregistration)


def test_base_preregistration_digest_drift_is_rejected(case_protocol_module, protocol, preregistration):
    preregistration["design"]["rounds"] = 4

    with pytest.raises(case_protocol_module.CaseProtocolError, match="digest drifted"):
        case_protocol_module.validate_protocol(protocol, preregistration)


def test_collection_authorization_is_rejected(case_protocol_module, protocol, preregistration):
    protocol["protocolization"]["collection_authorized"] = True

    with pytest.raises(case_protocol_module.CaseProtocolError, match="must not authorize"):
        case_protocol_module.validate_protocol(protocol, preregistration)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda case: case["artifact_oracle"]["required_artifacts"][0].update(build_output_path="build/**/*.a"),
            "cannot use globs",
        ),
        (
            lambda case: case["artifact_oracle"]["required_artifacts"][0].update(staged_relative_path="../escape"),
            "unsafe",
        ),
        (
            lambda case: case["artifact_oracle"]["required_artifacts"][0].update(artifact_type="archive"),
            "unsupported artifact type",
        ),
        (
            lambda case: case["artifact_oracle"]["required_artifacts"][0].update(producing_target="not-built"),
            "artifact target is not built",
        ),
    ],
)
def test_unsafe_or_incomplete_artifact_oracles_are_rejected(case_protocol_module, protocol, preregistration, mutation, message):
    mutation(protocol["cases"][0])

    with pytest.raises(case_protocol_module.CaseProtocolError, match=message):
        case_protocol_module.validate_protocol(protocol, preregistration)


def test_missing_evidence_claim_is_rejected(case_protocol_module, protocol, preregistration):
    for evidence in protocol["cases"][0]["evidence"]:
        evidence["supports"] = ["build_path"]

    with pytest.raises(case_protocol_module.CaseProtocolError, match="artifact identity"):
        case_protocol_module.validate_protocol(protocol, preregistration)


def test_unpinned_evidence_url_is_rejected(case_protocol_module, protocol, preregistration):
    protocol["cases"][0]["evidence"][0]["url"] = "https://github.com/PowerDNS/pdns/blob/main/configure.ac"

    with pytest.raises(case_protocol_module.CaseProtocolError, match="exact-commit pinned"):
        case_protocol_module.validate_protocol(protocol, preregistration)


@pytest.mark.parametrize(
    ("field", "value"),
    [("review_state", "pending"), ("result_data_consulted", True)],
)
def test_unreviewed_or_result_informed_case_is_rejected(case_protocol_module, protocol, preregistration, field, value):
    protocol["cases"][0][field] = value

    with pytest.raises(case_protocol_module.CaseProtocolError):
        case_protocol_module.validate_protocol(protocol, preregistration)


def test_secret_like_and_placeholder_content_are_rejected(case_protocol_module, protocol, preregistration):
    for value, message in (
        ("sk-" + "not-a-real-secret-value", "Secret-like"),
        ("TODO decide after collection", "Pending or placeholder"),
    ):
        candidate = copy.deepcopy(protocol)
        candidate["protocolization"]["note"] = value
        with pytest.raises(case_protocol_module.CaseProtocolError, match=message):
            case_protocol_module.validate_protocol(candidate, preregistration)


def test_markdown_is_deterministic_and_matches_committed_file(case_protocol_module, protocol, preregistration):
    summary = case_protocol_module.validate_protocol(protocol, preregistration)
    first = case_protocol_module.render_markdown(protocol, summary)
    reloaded = json.loads(json.dumps(protocol, ensure_ascii=False, sort_keys=True))
    second_summary = case_protocol_module.validate_protocol(reloaded, preregistration)
    second = case_protocol_module.render_markdown(reloaded, second_summary)

    assert first == second
    assert first == MARKDOWN.read_text(encoding="utf-8")
    assert first.count("\n| `") == 30


def test_cli_validate_and_render(case_protocol_module, tmp_path, capsys, protocol, preregistration):
    protocol_path = tmp_path / "protocol.json"
    preregistration_path = tmp_path / "preregistration.json"
    markdown_path = tmp_path / "protocol.md"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    preregistration_path.write_text(json.dumps(preregistration), encoding="utf-8")

    assert (
        case_protocol_module.main(
            [
                "validate",
                "--protocol",
                str(protocol_path),
                "--preregistration",
                str(preregistration_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["valid"] is True

    assert (
        case_protocol_module.main(
            [
                "render",
                "--protocol",
                str(protocol_path),
                "--preregistration",
                str(preregistration_path),
                "--output",
                str(markdown_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["valid"] is True
    assert markdown_path.read_text(encoding="utf-8").startswith("# Forge C/C++ 正式实验逐项目构建协议")
