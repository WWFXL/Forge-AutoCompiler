"""Issue #137 的非模型 environment checkpoint 原型测试。"""

from __future__ import annotations

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_PATH = REPO_ROOT / "scripts" / "forge_environment_checkpoint_prototype.py"
DOCKER_INTEGRATION_ENABLED = os.getenv("FORGE_RUN_ENVIRONMENT_CHECKPOINT_DOCKER") == "1"


def _load_module():
    spec = importlib.util.spec_from_file_location("forge_environment_checkpoint_prototype_test", PROTOTYPE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prototype = _load_module()


class FakeDockerRunner:
    def __init__(self, *, fail_capture: bool = False) -> None:
        self.command_count = 0
        self.commands: list[list[str]] = []
        self.fail_capture = fail_capture

    def run(self, arguments, *, check=True, timeout_seconds=60):
        del check, timeout_seconds
        self.command_count += 1
        self.commands.append(arguments)
        if self.fail_capture and arguments[0] == "commit":
            raise prototype.EnvironmentCheckpointError("synthetic capture failure")
        return prototype.DockerCommandResult(0, "", "")


def test_capture_uses_one_pause_window_and_unpauses_on_failure() -> None:
    runner = FakeDockerRunner(fail_capture=True)

    with pytest.raises(prototype.EnvironmentCheckpointError, match="synthetic capture failure"):
        prototype.capture_parent_checkpoint(
            runner,
            "fixture-parent",
            lambda: runner.run(["commit", "fixture-parent"]).stdout,
        )

    assert runner.commands == [
        ["pause", "fixture-parent"],
        ["commit", "fixture-parent"],
        ["unpause", "fixture-parent"],
    ]


def test_commit_output_uses_the_final_strict_image_id_line() -> None:
    image_id = "sha256:" + "a" * 64

    assert prototype.committed_image_id(f"non-sensitive Docker notice\n{image_id}\n") == image_id

    with pytest.raises(prototype.EnvironmentCheckpointError, match="Invalid immutable"):
        prototype.committed_image_id("notice without an image ID")


def test_tar_manifest_fixes_content_mode_mtime_and_symlink_metadata(tmp_path: Path) -> None:
    archive_path = tmp_path / "fixture.tar"
    content = b"checkpoint-content\n"
    with tarfile.open(archive_path, "w") as archive:
        directory = tarfile.TarInfo("./src")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o750
        directory.mtime = prototype.FIXED_MTIME
        directory.uid = directory.gid = 0
        archive.addfile(directory)

        regular = tarfile.TarInfo("./src/input.txt")
        regular.size = len(content)
        regular.mode = 0o640
        regular.mtime = prototype.FIXED_MTIME
        regular.uid = regular.gid = 0
        archive.addfile(regular, io.BytesIO(content))

        symlink = tarfile.TarInfo("./src/current")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "input.txt"
        symlink.mode = 0o777
        symlink.mtime = prototype.FIXED_MTIME
        symlink.uid = symlink.gid = 0
        archive.addfile(symlink)

    assert prototype.manifest_from_tar(archive_path) == [
        {
            "path": "src",
            "type": "directory",
            "mode": 0o750,
            "mtime": prototype.FIXED_MTIME,
            "uid": 0,
            "gid": 0,
            "content_sha256": None,
            "link_target": None,
        },
        {
            "path": "src/current",
            "type": "symlink",
            "mode": 0o777,
            "mtime": prototype.FIXED_MTIME,
            "uid": 0,
            "gid": 0,
            "content_sha256": None,
            "link_target": "input.txt",
        },
        {
            "path": "src/input.txt",
            "type": "file",
            "mode": 0o640,
            "mtime": prototype.FIXED_MTIME,
            "uid": 0,
            "gid": 0,
            "content_sha256": prototype.sha256_bytes(content),
            "link_target": None,
        },
    ]


def test_checkpoint_manifest_rejects_budget_scope_or_hash_drift() -> None:
    image_id = "sha256:" + "1" * 64
    manifest = {
        "schema_version": prototype.SCHEMA_VERSION,
        "manifest_sha256": "",
        "run_id": "fixture-run",
        "capture_method": "explicit-pause+docker-commit+bind-tar",
        "base_image_id": image_id,
        "continuation_image_id": image_id,
        "rootfs": {
            "sentinel_path": prototype.ROOTFS_SENTINEL,
            "content_sha256": "2" * 64,
        },
        "bind_mounts": {
            "workspace": {"archive_sha256": "3" * 64, "entries": []},
            "artifacts": {"archive_sha256": "4" * 64, "entries": []},
        },
        "identities": {"parent": "p", "baseline": "b", "treatment": "t"},
        "budget": {"reconstructed": False, "scope": "deferred-separate-gate"},
    }
    manifest["manifest_sha256"] = prototype.checkpoint_payload_sha256(manifest)
    assert prototype.validate_checkpoint_manifest(manifest) == manifest

    manifest["budget"]["reconstructed"] = True
    with pytest.raises(prototype.EnvironmentCheckpointError, match="Budget scope"):
        prototype.validate_checkpoint_manifest(manifest)


@pytest.mark.skipif(
    not DOCKER_INTEGRATION_ENABLED,
    reason="set FORGE_RUN_ENVIRONMENT_CHECKPOINT_DOCKER=1 to run the Ubuntu-native Docker gate",
)
def test_real_docker_rootfs_and_bind_mount_checkpoint() -> None:
    if shutil.which("docker") is None:
        pytest.fail("The opt-in environment checkpoint test requires the Docker CLI")
    daemon = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if daemon.returncode != 0:
        pytest.fail(f"Docker daemon is unavailable: {daemon.stderr.strip()}")

    result = prototype.EnvironmentCheckpointPrototype().run()

    assert result["base_image_id"] == "sha256:900d7ce4b902b79df5c64ffab88631b251538f1bde578c4dd2bf91558e9d1554"
    assert result["continuation_image_id"].startswith("sha256:")
    assert result["working_root_removed"] is True
    assert all(result["checks"].values())
    assert result["counts"]["provider_calls"] == 0
    assert result["counts"]["formal_physical_attempts"] == 0
    assert result["counts"]["model_tokens"] == 0
