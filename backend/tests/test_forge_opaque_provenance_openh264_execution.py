"""Issue #226 OpenH264 execution amendment 的零 provider 测试。"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
PROTOCOL_PATH = SCRIPTS_DIR / "forge_opaque_provenance_openh264_execution_protocol.py"
RUNNER_PATH = SCRIPTS_DIR / "forge_opaque_provenance_openh264_execution_runner.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-openh264-execution.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas/forge-opaque-provenance-openh264-execution.schema.json"


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
    "forge_opaque_provenance_openh264_execution_protocol_test",
    PROTOCOL_PATH,
)
runner = _load_module(
    "forge_opaque_provenance_openh264_execution_runner_test",
    RUNNER_PATH,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _completed(args: list[str], returncode: int = 0, stdout: str = ""):
    return subprocess.CompletedProcess(args, returncode, stdout, "")


def test_manifest_schema_and_execution_identity_are_frozen() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    assert manifest == protocol.generate_manifest(REPO_ROOT)
    assert schema == protocol.schema_document(manifest)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    protocol.verify_frozen_components(manifest, REPO_ROOT)
    assert manifest["case"]["target"] == "libopenh264.a"
    assert manifest["case"]["compile_image"] == protocol.COMPILE_IMAGE
    assert manifest["schedule"][0]["pair_id"] == protocol.PAIR_ID
    assert manifest["opportunities"]["required_order"] == [
        "reachability",
        protocol.PAIR_ID,
    ]


def test_authorization_budget_provider_and_fixture_are_closed() -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    assert manifest["authorization"]["model_tokens_authorized"] == 245_000
    assert manifest["provider"] == {
        "id": "deepseek-v4-flash",
        "endpoint": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "credential_env": "DEEPSEEK_API_KEY",
        "request_timeout_seconds": 300,
        "max_retries": 0,
        "streaming": False,
        "fallback": "forbidden",
        "status": "active_authorized",
    }
    assert manifest["continuation"]["maximum_requests_per_arm"] == 8
    assert manifest["budget"]["stage_maximum_recorded_tokens"] == 245_000
    assert manifest["dependency_fixture"]["apt_index_download_forbidden"] is True
    assert manifest["dependency_fixture"]["prepare_once"] is True


def test_runtime_hooks_inject_correct_bindings_and_openh264_lifecycle() -> None:
    assert runner.REPO_ROOT == REPO_ROOT
    originals = (
        runner.reference.protocol,
        runner.reference.make_lifecycle,
        runner.reference.make_parity,
        runner.reference.make_observability,
        runner.reference._policy,
        runner.reference.v2_runner.classify_arm_terminal,
    )
    with runner._reference_runtime_hooks():
        assert runner.reference.protocol is runner.protocol
        assert runner.reference.make_lifecycle.TARGET == "libopenh264.a"
        assert runner.reference.make_lifecycle.COMPILE_IMAGE == protocol.COMPILE_IMAGE
        assert hasattr(runner.reference.make_parity, "FrozenActionPolicy")
        assert hasattr(runner.reference.make_parity, "SerialToolCallMiddleware")
        assert hasattr(
            runner.reference.make_observability,
            "RejectionObservationRegistry",
        )
        assert hasattr(
            runner.reference.make_observability,
            "ObservableRuntimeParityToolAdapter",
        )
        assert runner.reference.v2_runner.classify_arm_terminal is not originals[-1]
    assert originals == (
        runner.reference.protocol,
        runner.reference.make_lifecycle,
        runner.reference.make_parity,
        runner.reference.make_observability,
        runner.reference._policy,
        runner.reference.v2_runner.classify_arm_terminal,
    )


def test_dependency_fixture_uses_fixed_package_commit_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    image_id = "sha256:" + "a" * 64
    commands: list[list[str]] = []

    def command_runner(args: list[str], _timeout: int):
        commands.append(args)
        if args[1:3] in (["container", "inspect"], ["image", "inspect"]):
            if "--format" in args:
                return _completed(args, stdout=image_id + "\n")
            return _completed(args, returncode=1)
        if args[1:3] == ["exec", manifest["dependency_fixture"]["preparation_container_name"]] and args[-2:] == ["nasm", "-v"]:
            return _completed(args, stdout="NASM version 2.16.01\n")
        return _completed(args)

    def downloader(package: dict, destination: Path) -> dict:
        destination.write_bytes(b"fixed-nasm-package")
        return {"sha256": package["sha256"], "size_bytes": 18}

    marker = tmp_path / "markers/dependency-fixture.json"
    monkeypatch.setattr(
        runner.reference.v3_runner,
        "_claim_marker",
        lambda *_args, **_kwargs: marker.parent.mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(
        runner.reference.v3_runner,
        "_finish_marker",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(runner, "_write_once", lambda path, value: path.parent.mkdir(parents=True, exist_ok=True) or path.write_text(json.dumps(value), encoding="utf-8"))
    report = runner._prepare_dependency_fixture(
        manifest,
        output_dir=tmp_path,
        release_revision="b" * 40,
        command_runner=command_runner,
        downloader=downloader,
    )
    assert report["image_id"] == image_id
    assert report["apt_index_downloaded"] is False
    assert ["docker", "commit", "--no-pause", manifest["dependency_fixture"]["preparation_container_name"], protocol.COMPILE_IMAGE] in commands
    assert not any("apt-get" in token for command in commands for token in command)

    cleanup = runner._cleanup_dependency_fixture(
        manifest,
        output_dir=tmp_path,
        image_id=image_id,
        command_runner=command_runner,
    )
    assert cleanup["cleanup_succeeded"] is True
    assert ["docker", "image", "rm", "--force", protocol.COMPILE_IMAGE] in commands
    assert ["docker", "image", "rm", "--force", image_id] in commands


def test_preflight_remains_zero_provider_and_writes_no_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    monkeypatch.setattr(
        runner.candidate,
        "validate_static_gate",
        lambda _root: {"parent_history_prefix_preserved": True},
    )

    async def construction():
        return {"status": "passed"}

    monkeypatch.setattr(runner.candidate, "validate_agent_construction", construction)
    monkeypatch.setattr(
        runner.reference,
        "collect_preflight",
        lambda *_args, **_kwargs: {
            "ready": True,
            "release_revision": "c" * 40,
            "network_access_medium": "wifi",
            "evidence_files": [],
            "provider_calls": 0,
            "formal_attempts": 0,
            "model_tokens": 0,
        },
    )
    monkeypatch.setattr(
        runner,
        "_require_fixture_absent",
        lambda *_args, **_kwargs: None,
    )
    output = tmp_path / "absent-evidence"
    result = runner.collect_preflight(
        manifest,
        output_dir=output,
        repo_root=tmp_path,
        require_empty=True,
    )
    assert result["full_agent_construction_gate"] == "passed"
    assert result["dependency_fixture_absent"] is True
    assert (
        result["provider_calls"],
        result["formal_attempts"],
        result["model_tokens"],
    ) == (0, 0, 0)
    assert not output.exists()


def test_pair_delegates_once_and_always_cleans_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    image_id = "sha256:" + "d" * 64
    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *_args, **_kwargs: {"release_revision": "e" * 40},
    )
    monkeypatch.setattr(
        runner.reference.legacy,
        "_passed_reachability",
        lambda *_args, **_kwargs: {"recorded_tokens": 17},
    )
    monkeypatch.setattr(
        runner,
        "_prepare_dependency_fixture",
        lambda *_args, **_kwargs: calls.append("prepare") or {"image_id": image_id},
    )
    monkeypatch.setattr(
        runner.reference,
        "execute_pair",
        lambda *_args, **_kwargs: calls.append("pair") or {"complete_pair": True},
    )
    monkeypatch.setattr(
        runner,
        "_cleanup_dependency_fixture",
        lambda *_args, **_kwargs: calls.append("cleanup") or {"cleanup_succeeded": True},
    )
    result = runner.execute_pair(manifest, output_dir=tmp_path)
    assert result == {"complete_pair": True}
    assert calls == ["prepare", "pair", "cleanup"]


def test_pair_does_not_mutate_cleanup_evidence_when_fixture_claim_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "collect_preflight",
        lambda *_args, **_kwargs: {"release_revision": "f" * 40},
    )
    monkeypatch.setattr(
        runner.reference.legacy,
        "_passed_reachability",
        lambda *_args, **_kwargs: {"recorded_tokens": 17},
    )

    def rejected(*_args, **_kwargs):
        raise runner.OpenH264ExecutionError("marker already exists")

    monkeypatch.setattr(runner, "_prepare_dependency_fixture", rejected)
    monkeypatch.setattr(
        runner,
        "_cleanup_dependency_fixture",
        lambda *_args, **_kwargs: calls.append("cleanup"),
    )
    with pytest.raises(runner.OpenH264ExecutionError, match="marker already exists"):
        runner.execute_pair(manifest, output_dir=tmp_path)
    assert calls == []


def test_schema_rejects_identity_authorization_or_fixture_drift() -> None:
    manifest = _load(MANIFEST_PATH)
    schema = _load(SCHEMA_PATH)
    mutations = (
        ("authorization", "provider_calls_authorized", False),
        ("case", "target", "all"),
        ("provider", "max_retries", 1),
        ("dependency_fixture", "apt_index_download_forbidden", False),
    )
    for section, field, value in mutations:
        drifted = copy.deepcopy(manifest)
        drifted[section][field] = value
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(drifted)
        with pytest.raises(protocol.ProtocolError, match="manifest drifted"):
            protocol.validate_manifest(drifted, REPO_ROOT)


def test_new_sources_do_not_embed_credentials_or_duplicate_reference_runner() -> None:
    combined = RUNNER_PATH.read_text(encoding="utf-8") + PROTOCOL_PATH.read_text(encoding="utf-8")
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 550
    assert "def _run_pair(" not in source
    assert source.index("sys.path.insert(0, str(REPO_SCRIPT_ROOT))") < source.index("import forge_opaque_provenance_openh264_candidate_gate")
    assert "apt-get update" not in combined
    assert "docker build" not in combined
    for forbidden in ("sk-", "api_key=", "OPENAI_AK", "os.environ["):
        assert forbidden not in combined
