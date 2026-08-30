"""Issue #218 R3 Make execution amendment 的零 provider 测试。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS_DIR / "forge_opaque_provenance_r3_make_execution_protocol.py"
RUNNER_PATH = SCRIPTS_DIR / "forge_opaque_provenance_r3_make_execution_runner.py"
PARENT_RUNNER_PATH = SCRIPTS_DIR / "forge_opaque_provenance_r2_make_execution_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-r3-make-execution.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-r3-make-execution.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module(
    "forge_opaque_provenance_r3_make_execution_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_opaque_provenance_r3_make_execution_runner_test",
    RUNNER_PATH,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_and_all_component_hashes_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    protocol.verify_frozen_components(manifest, REPO_ROOT)
    assert manifest["parent"]["canonical_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256
    assert manifest["parent"]["evidence_identity_sha256"] == (protocol.PARENT_EVIDENCE_IDENTITY_SHA256)


def test_authorization_budget_schedule_and_make_identity_are_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["authorization"]["model_tokens_authorized"] == 245_000
    assert all(value is True for key, value in manifest["authorization"].items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    assert manifest["budget"] == {
        "maximum_reachability_requests": 1,
        "reachability_maximum_recorded_tokens": 5_000,
        "recorded_tokens_per_arm": 120_000,
        "recorded_tokens_per_pair": 240_000,
        "stage_maximum_recorded_tokens": 245_000,
        "enforcement": "after_reachability_and_each_arm_before_continuation",
    }
    assert manifest["schedule"][0]["arm_order"] == ["baseline", "treatment"]
    assert manifest["case"]["build_system"] == "make"
    assert manifest["runtime_parity"]["action_surface"]["build_directory"] == "/workspace/repo"
    assert manifest["runtime_parity"]["action_surface"]["target"] == "libhoedown.a"
    assert manifest["runtime_parity"]["action_surface"]["jobs"] == {
        "omitted_allowed": True,
        "minimum": 1,
        "maximum": 2,
    }
    assert manifest["case"]["reference_case_id"] == protocol.REFERENCE_CASE_ID
    assert manifest["analysis"]["historical_pairs_pooled"] is False


def test_preflight_is_zero_provider_before_any_evidence_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_: None)
    monkeypatch.setattr(runner, "_output_dir", lambda _manifest, value: value)
    monkeypatch.setattr(
        runner.legacy,
        "_release_identity",
        lambda *_args: {"revision": "a" * 40},
    )
    monkeypatch.setattr(runner.legacy, "_network_medium", lambda _manifest: "wifi")
    monkeypatch.setattr(runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner.v3_runner, "require_zero_managed_containers", lambda: None)
    monkeypatch.setattr(runner.legacy, "_provider_preflight", lambda _manifest: None)
    result = runner.collect_preflight(
        manifest,
        output_dir=tmp_path / "absent-evidence",
        repo_root=tmp_path,
        require_empty=True,
    )
    assert result["ready"] is True
    assert result["network_access_medium"] == "wifi"
    assert result["evidence_files"] == []
    assert (
        result["provider_calls"],
        result["formal_attempts"],
        result["model_tokens"],
    ) == (0, 0, 0)
    assert not (tmp_path / "absent-evidence").exists()


def _record(
    command_id: str,
    command: str,
    role: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        command_id=command_id,
        command=command,
        stage="bash",
        workdir="/workspace/repo",
        exit_code=0,
        timed_out=False,
        role=role,
    )


@pytest.mark.parametrize("build_command", ("make libhoedown.a", "make -j1 libhoedown.a"))
def test_make_p2_session_projection_converts_only_after_direct_make(
    tmp_path: Path,
    build_command: str,
) -> None:
    artifact = tmp_path / runner.make_lifecycle.BUILD_OUTPUT
    content = b"!<arch>\n" + b"frozen-make-artifact"
    artifact.write_bytes(content)
    frozen = runner.make_lifecycle.build_frozen_identity(
        image_id="sha256:" + "2" * 64,
        physical_attempt_id="attempt-r3-make-execution-test",
        artifact_size=len(content),
        artifact_sha256=hashlib.sha256(content).hexdigest(),
    )
    parent_id = "parent-wrapper"
    parent_record = _record(
        parent_id,
        runner.make_lifecycle.PARENT_COMMAND,
        "build",
    )
    baseline = SimpleNamespace(
        leadagent_repo_dir=str(tmp_path),
        post_build_supporting_command_id=parent_id,
        commands=[parent_record],
    )
    baseline_p2, baseline_history = runner._evaluate_arm_p2(
        baseline,
        frozen,
        parent_id,
    )
    assert baseline_p2.status == "unproven"
    assert baseline_p2.reason == "opaque_wrapper"
    assert len(baseline_history) == 1

    treatment = SimpleNamespace(
        leadagent_repo_dir=str(tmp_path),
        post_build_supporting_command_id="direct-make",
        commands=[
            parent_record,
            _record(
                "direct-make",
                build_command,
                "build",
            ),
            _record(
                "artifact-stage",
                "cp libhoedown.a /artifacts/libhoedown.a",
                "artifact_stage",
            ),
        ],
    )
    treatment_p2, treatment_history = runner._evaluate_arm_p2(
        treatment,
        frozen,
        parent_id,
    )
    assert treatment_p2.status == "proven"
    assert treatment_p2.proof_mode == "direct_make"
    assert treatment_history[:1] == baseline_history


def test_runner_uses_make_pair_path_and_does_not_embed_credentials() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "legacy._run_pair" not in source
    assert "build/build.ninja" not in source
    assert 'parent.build_system = "make"' in source
    assert "evaluate_make_p2" in source
    assert "ObservableRuntimeParityToolAdapter" not in source
    assert "opaque-provenance-r2-make" not in source
    assert "forge_opaque_provenance_r2_make_pair_attempt" not in source
    for forbidden in ("sk-", "api_key=", "OPENAI_AK", "os.environ["):
        assert forbidden not in source


def test_schema_and_protocol_reject_authorization_budget_or_make_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    mutations = (
        ("authorization", "provider_calls_authorized", False),
        ("authorization", "model_tokens_authorized", 245_001),
        ("budget", "stage_maximum_recorded_tokens", 245_001),
        ("runtime_parity", "parallel_tool_calls", True),
    )
    for section, field, value in mutations:
        drifted = copy.deepcopy(manifest)
        drifted[section][field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
            protocol.validate_manifest(drifted, REPO_ROOT)

    drifted = copy.deepcopy(manifest)
    drifted["runtime_parity"]["action_surface"]["jobs"]["maximum"] = 8
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(drifted)
    with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
        protocol.validate_manifest(drifted, REPO_ROOT)


def test_runner_is_a_versioned_identity_only_derivation() -> None:
    parent = PARENT_RUNNER_PATH.read_text(encoding="utf-8")
    derived = RUNNER_PATH.read_text(encoding="utf-8")
    normalized = derived
    replacements = {
        "Issue #218 授权的 R3": "Issue #208 授权的 R2",
        "forge_opaque_provenance_r3_make_candidate_runner as make_observability": "forge_opaque_provenance_make_rejection_observability_gate as make_observability",
        "forge_opaque_provenance_r3_make_candidate_runner as make_parity": "forge_opaque_provenance_make_runtime_parity_gate as make_parity",
        "forge_opaque_provenance_r3_make_execution_protocol": "forge_opaque_provenance_r2_make_execution_protocol",
        "benchmark-evidence-opaque-provenance-r3-hoextdown-v1": "benchmark-evidence-opaque-provenance-r2-hoextdown-v1",
        "R3 Make execution": "R2 Make execution",
        "#216 冻结的 R3 Make": "#206 冻结的 R2 Make",
        "R3 Make evidence": "R2 Make evidence",
        "forge-opaque-provenance-r3-make-hoextdown": "forge-opaque-provenance-r2-make-hoextdown",
        "forge_opaque_provenance_r3_make_pair_attempt": "forge_opaque_provenance_r2_make_pair_attempt",
        "opaque-r3-make-": "opaque-make-",
        "opaque-provenance-r3-make-controlled-parent": "opaque-provenance-r2-make-controlled-parent",
        "opaque-provenance-r3-make-execution": "opaque-provenance-r2-make-execution",
        "opaque-provenance-r3-make-arm": "opaque-provenance-r2-make-arm",
        'manifest["case"]["case_id"]': "make_lifecycle.CASE_ID",
    }
    for current, frozen in replacements.items():
        normalized = normalized.replace(current, frozen)
    reordered_imports = "\n".join(
        (
            "import forge_opaque_provenance_make_lifecycle_gate as make_lifecycle  # noqa: E402",
            "import forge_opaque_provenance_minimal_canary_execution_runner as legacy  # noqa: E402",
            "import forge_opaque_provenance_r1_execution_runner as r1  # noqa: E402",
            "import forge_opaque_provenance_make_rejection_observability_gate as make_observability  # noqa: E402",
            "import forge_opaque_provenance_make_runtime_parity_gate as make_parity  # noqa: E402",
            "import forge_opaque_provenance_r2_make_execution_protocol as protocol  # noqa: E402",
        )
    )
    frozen_imports = "\n".join(
        (
            "import forge_opaque_provenance_make_lifecycle_gate as make_lifecycle  # noqa: E402",
            "import forge_opaque_provenance_make_rejection_observability_gate as make_observability  # noqa: E402",
            "import forge_opaque_provenance_make_runtime_parity_gate as make_parity  # noqa: E402",
            "import forge_opaque_provenance_minimal_canary_execution_runner as legacy  # noqa: E402",
            "import forge_opaque_provenance_r1_execution_runner as r1  # noqa: E402",
            "import forge_opaque_provenance_r2_make_execution_protocol as protocol  # noqa: E402",
        )
    )
    normalized = normalized.replace(reordered_imports, frozen_imports)
    normalized = "\n".join(line for line in normalized.splitlines() if '"reference_case_id":' not in line) + "\n"
    assert normalized == parent
