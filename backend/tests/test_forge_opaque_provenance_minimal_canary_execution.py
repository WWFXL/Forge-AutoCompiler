"""Issue #184 一次性执行 amendment 的零 provider 契约测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_opaque_provenance_minimal_canary_execution_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_opaque_provenance_minimal_canary_execution_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-minimal-canary-execution.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-minimal-canary-execution.schema.json"


def _load_module(name: str, path: Path):
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


protocol = _load_module("forge_opaque_provenance_minimal_canary_execution_protocol_test", PROTOCOL_PATH)
runner = _load_module("forge_opaque_provenance_minimal_canary_execution_runner_test", RUNNER_PATH)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_parent_evidence_and_runtime_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["parent"]["canonical_sha256"] == protocol.PARENT_MANIFEST_SHA256
    assert manifest["parent"]["evidence_identity_sha256"] == protocol.PARENT_EVIDENCE_IDENTITY_SHA256
    assert manifest["runtime_adapter"]["file_sha256"] == protocol.file_sha256(RUNNER_PATH)
    assert manifest["preregistration"]["file_sha256"] == protocol.file_sha256(REPO_ROOT / manifest["preregistration"]["path"])


def test_authorization_order_and_stage_budget_are_exact() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    authorization = manifest["authorization"]
    assert authorization == {
        "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/184",
        "reachability_request_authorized": True,
        "provider_calls_authorized": True,
        "formal_attempts_authorized": True,
        "canary_collection_authorized": True,
        "model_tokens_authorized": 245000,
    }
    assert manifest["opportunities"]["required_order"] == ["reachability", "opaque-provenance-cppitertools-pair-01"]
    assert manifest["schedule"][0]["arm_order"] == ["baseline", "treatment"]
    assert manifest["budget"]["reachability_maximum_recorded_tokens"] + manifest["budget"]["recorded_tokens_per_pair"] == 245000


class _Model:
    def __init__(self, text: str, *, tokens: int = 7):
        self.text = text
        self.tokens = tokens

    def invoke(self, _prompt: str):
        return SimpleNamespace(
            content=self.text,
            response_metadata={"model_name": "deepseek-v4-flash"},
            usage_metadata={"input_tokens": 3, "output_tokens": self.tokens - 3, "total_tokens": self.tokens},
        )


def _preflight(manifest: dict) -> dict:
    return {
        "ready": True,
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "release_revision": "a" * 40,
        "network_access_medium": "wifi",
        "evidence_files": [],
        "zero_managed_containers": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
    }


def test_reachability_is_create_once_and_records_no_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    monkeypatch.setattr(runner, "collect_preflight", lambda *args, **kwargs: _preflight(manifest))
    report = runner.execute_reachability(manifest, output_dir=tmp_path, model_factory=lambda _manifest: _Model("CANARY_OK"))
    assert report["passed"] is True
    assert report["recorded_tokens"] == 7
    serialized = json.dumps(report, sort_keys=True)
    assert report["credential_env"] == "DEEPSEEK_API_KEY"
    assert "credential_value" not in report
    assert "sk-test-secret" not in serialized
    with pytest.raises(RuntimeError):
        runner.execute_reachability(manifest, output_dir=tmp_path, model_factory=lambda _manifest: _Model("CANARY_OK"))


def test_failed_reachability_consumes_marker_and_pair_gate_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    monkeypatch.setattr(runner, "collect_preflight", lambda *args, **kwargs: _preflight(manifest))
    with pytest.raises(runner.ExecutionGateError, match="reachability"):
        runner.execute_reachability(manifest, output_dir=tmp_path, model_factory=lambda _manifest: _Model("WRONG"))
    marker = _load(tmp_path / manifest["evidence"]["reachability_marker"])
    assert marker["status"] == "failed"
    with pytest.raises(runner.ExecutionGateError, match="未形成"):
        runner._passed_reachability(manifest, tmp_path, "a" * 40)


def test_pair_gate_rejects_extra_evidence_after_passed_reachability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    monkeypatch.setattr(runner, "collect_preflight", lambda *args, **kwargs: _preflight(manifest))
    runner.execute_reachability(manifest, output_dir=tmp_path, model_factory=lambda _manifest: _Model("CANARY_OK"))
    extra = tmp_path / "unexpected.json"
    extra.write_text("{}\n", encoding="utf-8")
    with pytest.raises(runner.ExecutionGateError, match="唯一 reachability"):
        runner._passed_reachability(manifest, tmp_path, "a" * 40)


def test_arm_budget_is_checked_before_each_continuation() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    runner.require_arm_budget(manifest, reachability_tokens=5000, completed_arm_tokens=[])
    runner.require_arm_budget(manifest, reachability_tokens=5000, completed_arm_tokens=[120000])
    with pytest.raises(runner.ExecutionGateError, match="预算不足"):
        runner.require_arm_budget(manifest, reachability_tokens=5001, completed_arm_tokens=[120000])
    with pytest.raises(runner.ExecutionGateError, match="evidence"):
        runner.require_arm_budget(manifest, reachability_tokens=-1, completed_arm_tokens=[])


def test_dynamic_p2_requires_runtime_recorded_direct_cmake(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "build").mkdir(parents=True)
    artifact = repo / runner.opaque.BUILD_OUTPUT
    tree = repo / "build/build.ninja"
    artifact.write_bytes(b"frozen-artifact")
    tree.write_bytes(b"frozen-tree")
    image_id = "sha256:" + "2" * 64
    frozen = runner.opaque.build_frozen_identity(
        image_id=image_id,
        physical_attempt_id="attempt-arm",
        build_tree_sha256=runner.primary.lifecycle.sha256_file(tree),
        artifact_size=artifact.stat().st_size,
        artifact_sha256=runner.primary.lifecycle.sha256_file(artifact),
    )
    parent = SimpleNamespace(command_id="parent", command=runner.opaque.PARENT_COMMAND, stage="bash")
    direct = SimpleNamespace(
        command_id="direct",
        command=f"cmake --build {runner.opaque.BUILD_DIRECTORY} --target {runner.opaque.TARGET} -j2",
        stage="bash",
        workdir=runner.opaque.WORKDIR,
        exit_code=0,
        timed_out=False,
        role="build",
    )
    session = SimpleNamespace(
        leadagent_repo_dir=str(repo),
        post_build_supporting_command_id="direct",
        commands=[parent, direct],
    )
    decision, history = runner._evaluate_arm_p2(session, frozen, "parent")
    assert decision.status == "proven"
    assert decision.proof_mode == "direct_cmake"
    assert len(history) == 2


def test_parent_policy_and_packet_keep_non_estimand_constraints_neutral() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    policy = runner._parent_policy(manifest, image_id="sha256:" + "2" * 64)
    assert policy.model_name == "deterministic-no-provider"
    assert policy.cmake_arguments == ()
    assert policy.configure_arguments == ()
    assert runner.opaque.validate_repair_packet(runner.opaque.build_repair_packet()) == runner.opaque.build_repair_packet()
