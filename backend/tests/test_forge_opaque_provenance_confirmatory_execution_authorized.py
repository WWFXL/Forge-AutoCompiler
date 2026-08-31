"""Issue #237 确认性 execution authorized amendment 的零 provider 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS / "forge_opaque_provenance_confirmatory_execution_authorized_protocol.py"
RUNNER_PATH = SCRIPTS / "forge_opaque_provenance_confirmatory_execution_authorized_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-execution-authorized.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-confirmatory-execution-authorized.schema.json"


def _load_module(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_module(
    "forge_confirmatory_execution_authorized_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_confirmatory_execution_authorized_runner_test",
    RUNNER_PATH,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_schema_and_runtime_identity_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    protocol.verify_frozen_components(manifest, REPO_ROOT)
    assert protocol.canonical_sha256(manifest) == "68349316cfdbe8411c49c7ffc9491760bf19fb10e0583f40a47dd0c91ea31e78"


def test_authorized_delta_preserves_candidate_and_closes_budget() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    delta = protocol.validate_allowed_delta(manifest, REPO_ROOT)
    assert delta["parent_manifest_sha256"] == protocol.PARENT_MANIFEST_CANONICAL_SHA256
    assert delta["schedule_identity_sha256"] == "3f35dd8c245cb7e9db6069f63cf133c98fbfdf6813a11e3fa2306a5eb34c2134"
    assert delta["historical_evidence_reused"] is False
    assert delta["verifier_relaxation"] is False
    assert manifest["authorization"]["model_tokens_authorized"] == 2_940_000
    assert all(value is True for key, value in manifest["authorization"].items() if key.endswith("_authorized") and key != "model_tokens_authorized")
    execution = manifest["authorized_execution"]
    assert execution["provider"] == {
        "status": "active_authorized",
        "id": "deepseek-v4-flash",
        "endpoint": "https://api.deepseek.com",
        "credential_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-flash",
        "request_timeout_seconds": 300,
        "max_retries": 0,
        "fallback": "forbidden",
        "streaming": False,
    }
    assert execution["execution"]["checkpoint_capture_restore_reimplemented"] is False


def test_six_pair_runtime_adapters_preserve_case_and_order() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    pairs = manifest["schedule"]["pairs"]
    pair_manifests = [runner._pair_manifest(manifest, pair, Path("/tmp") / pair["pair_id"]) for pair in pairs]
    assert [item["case"]["case_id"] for item in pair_manifests] == [pair["case_id"] for pair in pairs]
    assert [item["continuation"]["arm_order"] for item in pair_manifests] == [pair["arm_order"] for pair in pairs]
    assert {item["runtime_parity"]["policy_family"] for item in pair_manifests} == {
        "cmake_runtime_parity_v1",
        "r3_make_runtime_parity_v1",
    }
    assert all(item["budget"]["stage_maximum_recorded_tokens"] == 245_000 for item in pair_manifests)


def test_preflight_is_zero_provider_and_does_not_create_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    output_dir = tmp_path / "absent-evidence"
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_: None)
    monkeypatch.setattr(runner, "_output_dir", lambda _manifest, value: value)
    monkeypatch.setattr(
        runner,
        "require_release_identity",
        lambda *_args: {
            "branch": "main",
            "revision": "a" * 40,
            "origin_main": "a" * 40,
        },
    )
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "wifi")
    monkeypatch.setattr(runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner, "require_zero_managed_containers", lambda: None)
    monkeypatch.setattr(
        runner.evidence_runtime,
        "_provider_config_preflight",
        lambda _manifest: None,
    )
    result = runner.collect_preflight(
        manifest,
        output_dir=output_dir,
        repo_root=tmp_path,
        require_empty=True,
    )
    assert result["ready"] is True
    assert result["credential_check"] == "environment_variable_presence_only"
    assert result["credential_env"] == "DEEPSEEK_API_KEY"
    assert (result["provider_calls"], result["formal_attempts"], result["model_tokens"]) == (
        0,
        0,
        0,
    )
    assert not output_dir.exists()


def _outcome(pair: dict, *, delta: int = 1, terminal: str = "valid") -> dict:
    return {
        "schema_version": "test",
        "document_type": "test",
        "manifest_sha256": "ignored",
        "pair_id": pair["pair_id"],
        "case_id": pair["case_id"],
        "replicate": pair["replicate"],
        "arm_order": pair["arm_order"],
        "terminal": terminal,
        "arms": {},
        "recorded_tokens": 100,
        "primary_mechanism_eligible": terminal != "endpoint_censored",
        "provenance_conversion": {
            "baseline": delta < 0,
            "treatment": delta > 0,
        },
        "paired_conversion_delta": (delta if terminal != "endpoint_censored" else None),
        "cleanup_succeeded": True,
    }


def test_batch_state_checks_schedule_taxonomy_and_prelaunch_ceiling() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    first, second = manifest["schedule"]["pairs"][:2]
    state = runner.next_batch_state(
        manifest,
        [_outcome(first, terminal="endpoint_censored")],
        reachability_tokens=17,
    )
    assert state["status"] == "ready"
    assert state["next_pair_id"] == second["pair_id"]

    ceiling_manifest = copy.deepcopy(manifest)
    ceiling_manifest["authorized_execution"]["budget"]["batch_maximum_recorded_tokens"] = 200
    state = runner.next_batch_state(
        ceiling_manifest,
        [],
        reachability_tokens=1,
    )
    assert state["status"] == "stopped"
    assert state["reason"] == "token_ceiling_reached"


def test_batch_reuses_one_event_loop_and_computes_project_level_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    digest = protocol.canonical_sha256(manifest)
    output_dir = tmp_path / "evidence"
    output_dir.mkdir()
    execution = manifest["authorized_execution"]
    _write_json(
        output_dir / execution["evidence"]["reachability_marker"],
        {
            "status": "passed",
            "manifest_sha256": digest,
            "release_revision": "b" * 40,
        },
    )
    _write_json(
        output_dir / execution["evidence"]["reachability_report"],
        {
            "passed": True,
            "manifest_sha256": digest,
            "release_revision": "b" * 40,
            "recorded_tokens": 10,
        },
    )
    monkeypatch.setattr(runner.protocol, "verify_frozen_components", lambda *_: None)
    monkeypatch.setattr(runner, "_output_dir", lambda _manifest, value: value)
    monkeypatch.setattr(
        runner,
        "require_release_identity",
        lambda *_args: {
            "branch": "main",
            "revision": "b" * 40,
            "origin_main": "b" * 40,
        },
    )
    monkeypatch.setenv("FORGE_NETWORK_ACCESS_MEDIUM", "wifi")
    monkeypatch.setattr(runner.primary, "require_compose_dood", lambda: None)
    monkeypatch.setattr(runner, "require_zero_managed_containers", lambda: None)
    loop_ids: list[int] = []

    def fake_pair_executor(
        _manifest,
        pair,
        _pair_dir,
        async_runner,
        _reachability,
        _release,
    ):
        loop_ids.append(id(async_runner.get_loop()))
        value = _outcome(pair)
        value["manifest_sha256"] = digest
        return value

    report = runner.run_batch(
        manifest,
        output_dir=output_dir,
        repo_root=tmp_path,
        pair_executor=fake_pair_executor,
    )
    assert len(set(loop_ids)) == 1
    assert len(loop_ids) == 12
    assert report["status"] == "completed"
    assert report["all_project_blocks_estimable"] is True
    assert report["primary_test"] == {
        "method": "two_sided_exact_sign_flip",
        "statistic": 6.0,
        "permutations": 64,
        "p_value": 0.03125,
    }
    assert report["recorded_tokens"] == 1_210
    assert _load(output_dir / execution["evidence"]["batch_marker"])["status"] == "passed"


def test_schema_rejects_identity_or_authorization_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    drifted = copy.deepcopy(manifest)
    drifted["authorization"]["pair_collection_authorized"] = False
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(drifted)
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_manifest(drifted, REPO_ROOT)


def test_runner_reuses_pair_and_checkpoint_cores_without_credentials() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert ".RealLifecycleCheckpointGate(" not in source
    assert ".capture(" not in source
    assert ".provision_arm(" not in source
    assert "cmake_pair_runtime" in source
    assert "make_pair_runtime" in source
    assert "asyncio.Runner() as async_runner" in source
    for forbidden in ("sk-", "api_key=", "os.environ[", "OPENAI_AK"):
        assert forbidden not in source


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
