from __future__ import annotations

import importlib.util
import tarfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/forge_progress_aware_harness_qualification_v2.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_progress_aware_harness_qualification_v2_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest_with_current_components(module: ModuleType) -> dict:
    module._activate_base()
    manifest = module.base._manifest()
    manifest["components"] = {relative: module.base._file_sha256(REPO_ROOT / relative) for relative in module.COMPONENT_PATHS}
    return manifest


def test_v2_manifest_binds_v1_failure_and_source_ready_archive() -> None:
    module = _load_module()
    manifest = _manifest_with_current_components(module)

    validated = module.validate_manifest(manifest)

    assert validated["remediation_parent"]["failure"] == ("clean_replay_git_fetch_gnutls_handshake")
    source = module._source_archive(validated)
    assert source.name == "workspace.tar.gz"
    assert module.base._file_sha256(source) == validated["source_archive"]["sha256"]
    with tarfile.open(source, "r:*") as archive:
        names = archive.getnames()
    assert "CMakeLists.txt" in names
    assert not any(name == "build" or name.startswith("build/") for name in names)


def test_bind_source_archive_sets_session_identity_without_network(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    manifest = _manifest_with_current_components(module)
    saved: list[object] = []
    services = SimpleNamespace(manager=SimpleNamespace(save_session=lambda session: saved.append(session)))
    monkeypatch.setattr(module.base, "get_compile_services", lambda: services)
    session = SimpleNamespace(
        leadagent_repro_dir=str(tmp_path / "repro"),
        replay_source_archive_sha256=None,
    )

    observed = module._bind_source_archive(manifest, session)

    assert observed == manifest["source_archive"]["sha256"]
    assert session.replay_source_archive_sha256 == observed
    assert module.base._file_sha256(tmp_path / "repro/source.tar") == observed
    assert saved == [session]


def test_replay_observation_requires_archive_and_excludes_git_fetch(
    tmp_path: Path,
) -> None:
    module = _load_module()
    repro = tmp_path / "repro"
    repro.mkdir()
    (repro / "build.sh").write_text(
        'SOURCE_ARCHIVE=/repro/source.tar\ntar -xf "$SOURCE_ARCHIVE" -C /workspace/repo\n',
        encoding="utf-8",
    )
    session = SimpleNamespace(
        replay_attempts=[SimpleNamespace(checks=[SimpleNamespace(name="source_snapshot", passed=True)])],
        leadagent_repro_dir=str(repro),
    )

    observed = module._replay_observation(session)

    assert observed == {
        "attempt_count": 1,
        "source_snapshot_passed": True,
        "git_fetch_present": False,
        "source_archive_extract_present": True,
    }


def test_v2_qualification_adds_offline_replay_gates() -> None:
    module = _load_module()
    manifest = _manifest_with_current_components(module)
    result = {
        "credential_reads": 0,
        "provider_requests": 0,
        "script_model_calls": 5,
        "event_summary": {
            "progress_snapshot_count": 5,
            "effective_compaction_count": 2,
            "ready_guard_rejections": 1,
            "candidate_prefreeze_verified": True,
            "candidate_submit_accepted": True,
        },
        "candidate_submitted": True,
        "strict_success": True,
        "layers": [{"layer": layer, "status": "passed"} for layer in ("S0", "S1", "S2", "S3", "S4", "S5")],
        "usage": {
            "model_requests": 5,
            "tool_calls": 5,
            "commands": 3,
            "agent_steps": 10,
        },
        "cleanup_succeeded": True,
        "managed_containers_after_cleanup": [],
        "parent_inventory_before": manifest["parent"]["inventory_canonical_sha256"],
        "parent_inventory_after": manifest["parent"]["inventory_canonical_sha256"],
        "remediation_parent_inventory_before": manifest["remediation_parent"]["inventory_canonical_sha256"],
        "remediation_parent_inventory_after": manifest["remediation_parent"]["inventory_canonical_sha256"],
        "source_archive_sha256": manifest["source_archive"]["sha256"],
        "replay": {
            "source_snapshot_passed": True,
            "git_fetch_present": False,
            "source_archive_extract_present": True,
        },
    }

    qualified = module._qualification(result, manifest)
    assert qualified["passed"] is True

    result["replay"]["git_fetch_present"] = True
    rejected = module._qualification(result, manifest)
    assert rejected["passed"] is False
    assert rejected["gates"]["replay_network_independent"] is False
