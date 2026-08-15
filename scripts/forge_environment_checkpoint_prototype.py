#!/usr/bin/env python3
"""验证 rootfs 与 bind mount 双层恢复的非模型环境 checkpoint 原型。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

SCHEMA_VERSION = "forge-environment-checkpoint-1.0.0"
PROTOTYPE_LABEL = "forge.environment-checkpoint.prototype"
RUN_LABEL = "forge.environment-checkpoint.run_id"
DEFAULT_IMAGE = "autocompiler:gcc13"
ROOTFS_SENTINEL = "/opt/forge-checkpoint/rootfs-sentinel.txt"
FIXED_MTIME = 1_700_000_000


class EnvironmentCheckpointError(RuntimeError):
    pass


@dataclass(frozen=True)
class DockerCommandResult:
    returncode: int
    stdout: str
    stderr: str


class DockerRunner(Protocol):
    command_count: int

    def run(
        self,
        arguments: list[str],
        *,
        check: bool = True,
        timeout_seconds: int = 60,
    ) -> DockerCommandResult: ...


class DockerCLI:
    def __init__(self) -> None:
        self.command_count = 0

    def run(
        self,
        arguments: list[str],
        *,
        check: bool = True,
        timeout_seconds: int = 60,
    ) -> DockerCommandResult:
        self.command_count += 1
        command = ["docker", *arguments]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EnvironmentCheckpointError(f"Docker command failed to complete: {arguments[0]}") from exc
        result = DockerCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )
        if check and result.returncode != 0:
            detail = result.stderr or result.stdout or "unknown Docker error"
            raise EnvironmentCheckpointError(f"Docker command failed ({arguments[0]}): {detail}")
        return result


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_payload_sha256(manifest: dict[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return sha256_bytes(canonical_bytes(payload))


def _normalize_archive_path(name: str) -> str | None:
    while name.startswith("./"):
        name = name[2:]
    if not name or name == ".":
        return None
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise EnvironmentCheckpointError(f"Unsafe archive member path: {name!r}")
    return path.as_posix()


def _entry(
    *,
    path: str,
    entry_type: str,
    mode: int,
    mtime: int,
    uid: int,
    gid: int,
    content_sha256: str | None = None,
    link_target: str | None = None,
) -> dict[str, Any]:
    return {
        "path": path,
        "type": entry_type,
        "mode": mode,
        "mtime": mtime,
        "uid": uid,
        "gid": gid,
        "content_sha256": content_sha256,
        "link_target": link_target,
    }


def manifest_from_tar(path: Path) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    with tarfile.open(path, mode="r:") as archive:
        for member in archive.getmembers():
            normalized = _normalize_archive_path(member.name)
            if normalized is None:
                continue
            if normalized in entries:
                raise EnvironmentCheckpointError(f"Duplicate archive member path: {normalized}")
            if member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    raise EnvironmentCheckpointError(f"Archive file cannot be read: {normalized}")
                entries[normalized] = _entry(
                    path=normalized,
                    entry_type="file",
                    mode=member.mode,
                    mtime=int(member.mtime),
                    uid=member.uid,
                    gid=member.gid,
                    content_sha256=sha256_bytes(stream.read()),
                )
            elif member.isdir():
                entries[normalized] = _entry(
                    path=normalized,
                    entry_type="directory",
                    mode=member.mode,
                    mtime=int(member.mtime),
                    uid=member.uid,
                    gid=member.gid,
                )
            elif member.issym():
                entries[normalized] = _entry(
                    path=normalized,
                    entry_type="symlink",
                    mode=member.mode,
                    mtime=int(member.mtime),
                    uid=member.uid,
                    gid=member.gid,
                    link_target=member.linkname,
                )
            else:
                raise EnvironmentCheckpointError(f"Unsupported archive member type: {normalized}")
    return [entries[name] for name in sorted(entries)]


def validate_checkpoint_manifest(manifest: Any) -> dict[str, Any]:
    expected_fields = {
        "schema_version",
        "manifest_sha256",
        "run_id",
        "capture_method",
        "base_image_id",
        "continuation_image_id",
        "rootfs",
        "bind_mounts",
        "identities",
        "budget",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_fields:
        raise EnvironmentCheckpointError("Checkpoint manifest fields do not match the frozen schema")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise EnvironmentCheckpointError("Checkpoint manifest schema version is invalid")
    if manifest["capture_method"] != "explicit-pause+docker-commit+bind-tar":
        raise EnvironmentCheckpointError("Checkpoint capture method is invalid")
    if manifest["budget"] != {"reconstructed": False, "scope": "deferred-separate-gate"}:
        raise EnvironmentCheckpointError("Budget scope drifted into the environment gate")
    for image_field in ("base_image_id", "continuation_image_id"):
        _validate_image_id(manifest[image_field])
    for mount_name in ("workspace", "artifacts"):
        mount = manifest["bind_mounts"].get(mount_name)
        if not isinstance(mount, dict) or set(mount) != {"archive_sha256", "entries"}:
            raise EnvironmentCheckpointError(f"Bind mount manifest is invalid: {mount_name}")
        if not isinstance(mount["entries"], list):
            raise EnvironmentCheckpointError(f"Bind mount entries are invalid: {mount_name}")
    if manifest["manifest_sha256"] != checkpoint_payload_sha256(manifest):
        raise EnvironmentCheckpointError("Checkpoint manifest SHA-256 does not match its payload")
    return manifest


def _validate_image_id(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise EnvironmentCheckpointError(f"Invalid immutable Docker image ID: {value!r}")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise EnvironmentCheckpointError(f"Invalid immutable Docker image ID: {value!r}") from exc
    return value.lower()


def committed_image_id(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        raise EnvironmentCheckpointError("Docker commit returned no immutable image ID")
    return _validate_image_id(lines[-1])


def capture_parent_checkpoint(
    runner: DockerRunner,
    parent_name: str,
    capture: Callable[[], str],
) -> str:
    """在同一个显式暂停窗口执行 capture，并保证异常路径恢复父容器。"""

    runner.run(["pause", parent_name])
    try:
        return capture()
    finally:
        runner.run(["unpause", parent_name])


class EnvironmentCheckpointPrototype:
    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        runner: DockerRunner | None = None,
    ) -> None:
        self.image = image
        self.runner = runner or DockerCLI()
        self.run_id = uuid.uuid4().hex[:12]
        self.working_root = Path(tempfile.mkdtemp(prefix=f"forge-env-checkpoint-{self.run_id}-"))
        self.container_names: list[str] = []
        self.continuation_image_id: str | None = None
        self.base_image_id: str | None = None

    def _name(self, role: str) -> str:
        return f"forge-env-checkpoint-{self.run_id}-{role}"

    def _label_arguments(self) -> list[str]:
        return [
            "--label",
            f"{PROTOTYPE_LABEL}=true",
            "--label",
            f"{RUN_LABEL}={self.run_id}",
        ]

    def _assert_no_preexisting_resources(self) -> None:
        containers = self.runner.run(
            ["ps", "-aq", "--filter", f"label={PROTOTYPE_LABEL}=true"],
            timeout_seconds=30,
        ).stdout
        images = self.runner.run(
            ["image", "ls", "-q", "--filter", f"label={PROTOTYPE_LABEL}=true"],
            timeout_seconds=30,
        ).stdout
        if containers or images:
            raise EnvironmentCheckpointError("Prototype-labeled Docker resources already exist; refusing broad cleanup")

    def _image_id(self, reference: str) -> str:
        result = self.runner.run(
            ["image", "inspect", "--format", "{{.Id}}", reference],
            timeout_seconds=30,
        )
        return _validate_image_id(result.stdout)

    def _create_parent(self, workspace: Path, artifacts: Path) -> str:
        parent_name = self._name("parent")
        self.container_names.append(parent_name)
        self.runner.run(
            [
                "create",
                "--name",
                parent_name,
                *self._label_arguments(),
                "--mount",
                f"type=bind,src={workspace},dst=/workspace",
                "--mount",
                f"type=bind,src={artifacts},dst=/artifacts",
                self.image,
                "sh",
                "-c",
                "while :; do sleep 3600; done",
            ],
            timeout_seconds=60,
        )
        self.runner.run(["start", parent_name], timeout_seconds=30)
        seed = f"""set -eu
mkdir -p /opt/forge-checkpoint /workspace/src /artifacts/bin
printf 'rootfs-before-checkpoint\n' > {ROOTFS_SENTINEL}
printf 'workspace-before-checkpoint\n' > /workspace/src/input.txt
printf 'artifact-before-checkpoint\n' > /artifacts/bin/output.bin
chmod 0600 {ROOTFS_SENTINEL}
chmod 0640 /workspace/src/input.txt
chmod 0750 /artifacts/bin/output.bin
ln -s input.txt /workspace/src/current
touch -d @{FIXED_MTIME} {ROOTFS_SENTINEL} /workspace/src/input.txt /artifacts/bin/output.bin
touch -h -d @{FIXED_MTIME} /workspace/src/current
touch -d @{FIXED_MTIME} /workspace/src /artifacts/bin
"""
        self.runner.run(["exec", parent_name, "sh", "-c", seed], timeout_seconds=30)
        return parent_name

    def _archive_bind_mounts(
        self,
        *,
        workspace: Path,
        artifacts: Path,
        snapshot: Path,
    ) -> None:
        helper_name = self._name("capture")
        self.container_names.append(helper_name)
        command = (
            "set -eu; "
            "tar --numeric-owner --format=posix -cpf /snapshot/workspace.tar -C /source/workspace .; "
            "tar --numeric-owner --format=posix -cpf /snapshot/artifacts.tar -C /source/artifacts .; "
            f"chown -R {os.getuid()}:{os.getgid()} /snapshot"
        )
        self.runner.run(
            [
                "run",
                "--rm",
                "--name",
                helper_name,
                *self._label_arguments(),
                "--mount",
                f"type=bind,src={workspace},dst=/source/workspace,readonly",
                "--mount",
                f"type=bind,src={artifacts},dst=/source/artifacts,readonly",
                "--mount",
                f"type=bind,src={snapshot},dst=/snapshot",
                self.image,
                "sh",
                "-c",
                command,
            ],
            timeout_seconds=120,
        )

    def _capture(self, parent_name: str, workspace: Path, artifacts: Path, snapshot: Path) -> str:
        def commit_and_archive() -> str:
            committed = self.runner.run(
                [
                    "commit",
                    "--no-pause",
                    "--change",
                    f"LABEL {PROTOTYPE_LABEL}=true",
                    "--change",
                    f"LABEL {RUN_LABEL}={self.run_id}",
                    parent_name,
                ],
                timeout_seconds=180,
            )
            self.continuation_image_id = committed_image_id(committed.stdout)
            self._archive_bind_mounts(workspace=workspace, artifacts=artifacts, snapshot=snapshot)
            return self.continuation_image_id

        return capture_parent_checkpoint(self.runner, parent_name, commit_and_archive)

    def _write_manifest(
        self,
        *,
        snapshot: Path,
        parent_name: str,
        baseline_name: str,
        treatment_name: str,
        rootfs_content: str,
    ) -> dict[str, Any]:
        workspace_tar = snapshot / "workspace.tar"
        artifacts_tar = snapshot / "artifacts.tar"
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "manifest_sha256": "",
            "run_id": self.run_id,
            "capture_method": "explicit-pause+docker-commit+bind-tar",
            "base_image_id": self.base_image_id,
            "continuation_image_id": self.continuation_image_id,
            "rootfs": {
                "sentinel_path": ROOTFS_SENTINEL,
                "content_sha256": sha256_bytes(rootfs_content.encode("utf-8")),
            },
            "bind_mounts": {
                "workspace": {
                    "archive_sha256": sha256_file(workspace_tar),
                    "entries": manifest_from_tar(workspace_tar),
                },
                "artifacts": {
                    "archive_sha256": sha256_file(artifacts_tar),
                    "entries": manifest_from_tar(artifacts_tar),
                },
            },
            "identities": {
                "parent": parent_name,
                "baseline": baseline_name,
                "treatment": treatment_name,
            },
            "budget": {"reconstructed": False, "scope": "deferred-separate-gate"},
        }
        manifest["manifest_sha256"] = checkpoint_payload_sha256(manifest)
        validate_checkpoint_manifest(manifest)
        manifest_path = snapshot / "checkpoint.json"
        manifest_path.write_bytes(canonical_bytes(manifest) + b"\n")
        for path in (workspace_tar, artifacts_tar, manifest_path):
            path.chmod(0o444)
        snapshot.chmod(0o555)
        return manifest

    def _restore_arm(self, role: str, snapshot: Path, workspace: Path, artifacts: Path) -> str:
        helper_name = self._name(f"restore-{role}")
        self.container_names.append(helper_name)
        self.runner.run(
            [
                "run",
                "--rm",
                "--name",
                helper_name,
                *self._label_arguments(),
                "--mount",
                f"type=bind,src={snapshot},dst=/snapshot,readonly",
                "--mount",
                f"type=bind,src={workspace},dst=/restore/workspace",
                "--mount",
                f"type=bind,src={artifacts},dst=/restore/artifacts",
                self.image,
                "sh",
                "-c",
                "set -eu; tar -xpf /snapshot/workspace.tar -C /restore/workspace; tar -xpf /snapshot/artifacts.tar -C /restore/artifacts",
            ],
            timeout_seconds=120,
        )

        arm_name = self._name(role)
        self.container_names.append(arm_name)
        self.runner.run(
            [
                "create",
                "--name",
                arm_name,
                *self._label_arguments(),
                "--mount",
                f"type=bind,src={workspace},dst=/workspace",
                "--mount",
                f"type=bind,src={artifacts},dst=/artifacts",
                self.continuation_image_id or "",
                "sh",
                "-c",
                "while :; do sleep 3600; done",
            ],
            timeout_seconds=60,
        )
        self.runner.run(["start", arm_name], timeout_seconds=30)
        return arm_name

    def _observe_bind_mounts(self, role: str, workspace: Path, artifacts: Path) -> dict[str, list[dict[str, Any]]]:
        observation = self.working_root / "observations" / f"{role}-{uuid.uuid4().hex[:8]}"
        observation.mkdir(parents=True)
        observation.chmod(0o777)
        helper_name = self._name(f"observe-{role}-{uuid.uuid4().hex[:6]}")
        self.container_names.append(helper_name)
        command = (
            "set -eu; "
            "tar --numeric-owner --format=posix -cpf /observation/workspace.tar -C /source/workspace .; "
            "tar --numeric-owner --format=posix -cpf /observation/artifacts.tar -C /source/artifacts .; "
            f"chown -R {os.getuid()}:{os.getgid()} /observation"
        )
        self.runner.run(
            [
                "run",
                "--rm",
                "--name",
                helper_name,
                *self._label_arguments(),
                "--mount",
                f"type=bind,src={workspace},dst=/source/workspace,readonly",
                "--mount",
                f"type=bind,src={artifacts},dst=/source/artifacts,readonly",
                "--mount",
                f"type=bind,src={observation},dst=/observation",
                self.image,
                "sh",
                "-c",
                command,
            ],
            timeout_seconds=120,
        )
        result = {
            "workspace": manifest_from_tar(observation / "workspace.tar"),
            "artifacts": manifest_from_tar(observation / "artifacts.tar"),
        }
        shutil.rmtree(observation)
        return result

    def _container_rootfs_content(self, container_name: str) -> str:
        return (
            self.runner.run(
                ["exec", container_name, "cat", ROOTFS_SENTINEL],
                timeout_seconds=30,
            ).stdout
            + "\n"
        )

    def _canonical_arm_state(
        self,
        container_name: str,
        workspace: Path,
        artifacts: Path,
    ) -> dict[str, Any]:
        image_id = _validate_image_id(
            self.runner.run(
                ["inspect", "--format", "{{.Image}}", container_name],
                timeout_seconds=30,
            ).stdout
        )
        bind_mounts = self._observe_bind_mounts(container_name.rsplit("-", 1)[-1], workspace, artifacts)
        return {
            "image_id": image_id,
            "rootfs_content_sha256": sha256_bytes(self._container_rootfs_content(container_name).encode("utf-8")),
            "workspace": bind_mounts["workspace"],
            "artifacts": bind_mounts["artifacts"],
        }

    def _run_gate(self) -> dict[str, Any]:
        self._assert_no_preexisting_resources()
        self.base_image_id = self._image_id(self.image)

        parent_workspace = self.working_root / "parent" / "workspace"
        parent_artifacts = self.working_root / "parent" / "artifacts"
        snapshot = self.working_root / "snapshot"
        baseline_workspace = self.working_root / "baseline" / "workspace"
        baseline_artifacts = self.working_root / "baseline" / "artifacts"
        treatment_workspace = self.working_root / "treatment" / "workspace"
        treatment_artifacts = self.working_root / "treatment" / "artifacts"
        directories = (
            parent_workspace,
            parent_artifacts,
            snapshot,
            baseline_workspace,
            baseline_artifacts,
            treatment_workspace,
            treatment_artifacts,
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            directory.chmod(0o777)

        parent_name = self._create_parent(parent_workspace, parent_artifacts)
        baseline_name = self._name("baseline")
        treatment_name = self._name("treatment")
        rootfs_content = self._container_rootfs_content(parent_name)
        self._capture(parent_name, parent_workspace, parent_artifacts, snapshot)
        manifest = self._write_manifest(
            snapshot=snapshot,
            parent_name=parent_name,
            baseline_name=baseline_name,
            treatment_name=treatment_name,
            rootfs_content=rootfs_content,
        )

        baseline_name = self._restore_arm("baseline", snapshot, baseline_workspace, baseline_artifacts)
        treatment_name = self._restore_arm("treatment", snapshot, treatment_workspace, treatment_artifacts)
        baseline_initial = self._canonical_arm_state(baseline_name, baseline_workspace, baseline_artifacts)
        treatment_initial = self._canonical_arm_state(treatment_name, treatment_workspace, treatment_artifacts)
        if baseline_initial != treatment_initial:
            raise EnvironmentCheckpointError("Baseline and treatment initial environments differ")
        if baseline_initial["workspace"] != manifest["bind_mounts"]["workspace"]["entries"]:
            raise EnvironmentCheckpointError("Restored workspace metadata differs from the immutable snapshot")
        if baseline_initial["artifacts"] != manifest["bind_mounts"]["artifacts"]["entries"]:
            raise EnvironmentCheckpointError("Restored artifact metadata differs from the immutable snapshot")
        if baseline_initial["image_id"] != self.continuation_image_id:
            raise EnvironmentCheckpointError("Arm container did not use the continuation image ID")

        source_before = self._observe_bind_mounts("parent-before", parent_workspace, parent_artifacts)
        archive_hashes_before = {
            "workspace": sha256_file(snapshot / "workspace.tar"),
            "artifacts": sha256_file(snapshot / "artifacts.tar"),
            "manifest": sha256_file(snapshot / "checkpoint.json"),
        }
        self.runner.run(
            [
                "exec",
                baseline_name,
                "sh",
                "-c",
                f"printf 'baseline-rootfs-write\n' > {ROOTFS_SENTINEL}; printf 'baseline-workspace-write\n' > /workspace/src/input.txt",
            ],
            timeout_seconds=30,
        )
        if self._container_rootfs_content(treatment_name) != rootfs_content:
            raise EnvironmentCheckpointError("Baseline rootfs write polluted treatment")
        if self._container_rootfs_content(parent_name) != rootfs_content:
            raise EnvironmentCheckpointError("Baseline rootfs write polluted parent")
        treatment_after_baseline_write = self._observe_bind_mounts(
            "treatment-after-baseline-write",
            treatment_workspace,
            treatment_artifacts,
        )
        if treatment_after_baseline_write["workspace"] != treatment_initial["workspace"]:
            raise EnvironmentCheckpointError("Baseline bind write polluted treatment")
        parent_after_baseline_write = self._observe_bind_mounts(
            "parent-after-baseline-write",
            parent_workspace,
            parent_artifacts,
        )
        if parent_after_baseline_write["workspace"] != source_before["workspace"]:
            raise EnvironmentCheckpointError("Baseline bind write polluted parent")
        if parent_after_baseline_write["artifacts"] != source_before["artifacts"]:
            raise EnvironmentCheckpointError("Parent artifact checkpoint changed")

        self.runner.run(
            ["exec", treatment_name, "sh", "-c", "printf 'treatment-only\n' > /artifacts/treatment-only.txt"],
            timeout_seconds=30,
        )
        if (baseline_artifacts / "treatment-only.txt").exists() or (parent_artifacts / "treatment-only.txt").exists():
            raise EnvironmentCheckpointError("Treatment artifact write crossed an arm boundary")
        archive_hashes_after = {
            "workspace": sha256_file(snapshot / "workspace.tar"),
            "artifacts": sha256_file(snapshot / "artifacts.tar"),
            "manifest": sha256_file(snapshot / "checkpoint.json"),
        }
        if archive_hashes_before != archive_hashes_after:
            raise EnvironmentCheckpointError("Immutable parent snapshot was modified")

        checks = {
            "explicit_pause_capture_and_unpause": True,
            "rootfs_sentinel_restored": True,
            "bind_content_mode_mtime_symlink_restored": True,
            "initial_canonical_state_equal": True,
            "arm_rootfs_isolated": True,
            "arm_bind_mounts_isolated": True,
            "parent_snapshot_immutable": True,
            "provider_calls_zero": True,
            "formal_physical_attempts_zero": True,
            "model_tokens_zero": True,
            "budget_reconstruction_deferred": True,
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "base_image_id": self.base_image_id,
            "continuation_image_id": self.continuation_image_id,
            "checkpoint_manifest_sha256": manifest["manifest_sha256"],
            "initial_state_sha256": sha256_bytes(canonical_bytes(baseline_initial)),
            "checks": checks,
            "counts": {
                "provider_calls": 0,
                "formal_physical_attempts": 0,
                "model_tokens": 0,
                "docker_commands_before_cleanup": self.runner.command_count,
            },
        }

    def _cleanup(self) -> list[str]:
        errors: list[str] = []
        for name in reversed(self.container_names):
            result = self.runner.run(["rm", "-f", name], check=False, timeout_seconds=20)
            if result.returncode not in (0, 1):
                errors.append(f"container cleanup failed: {name}")
        if self.continuation_image_id:
            result = self.runner.run(
                ["image", "rm", "-f", self.continuation_image_id],
                check=False,
                timeout_seconds=60,
            )
            if result.returncode != 0:
                errors.append("continuation image cleanup failed")

        if self.working_root.exists():
            try:
                snapshot = self.working_root / "snapshot"
                if snapshot.exists():
                    snapshot.chmod(0o755)
                    for child in snapshot.iterdir():
                        child.chmod(0o644)
                shutil.rmtree(self.working_root)
            except OSError:
                helper_name = self._name("cleanup-permissions")
                result = self.runner.run(
                    [
                        "run",
                        "--rm",
                        "--name",
                        helper_name,
                        *self._label_arguments(),
                        "--mount",
                        f"type=bind,src={self.working_root},dst=/cleanup",
                        self.image,
                        "sh",
                        "-c",
                        "chmod -R a+rwX /cleanup",
                    ],
                    check=False,
                    timeout_seconds=60,
                )
                if result.returncode == 0:
                    shutil.rmtree(self.working_root, ignore_errors=True)
                if self.working_root.exists():
                    errors.append("temporary directory cleanup failed")

        for kind, arguments in (
            ("container", ["ps", "-aq", "--filter", f"label={RUN_LABEL}={self.run_id}"]),
            ("image", ["image", "ls", "-q", "--filter", f"label={RUN_LABEL}={self.run_id}"]),
        ):
            result = self.runner.run(arguments, check=False, timeout_seconds=30)
            if result.returncode != 0 or result.stdout:
                errors.append(f"prototype-labeled {kind} cleanup was incomplete")
        return errors

    def run(self) -> dict[str, Any]:
        result: dict[str, Any] | None = None
        failure: BaseException | None = None
        try:
            result = self._run_gate()
        except BaseException as exc:
            failure = exc
        cleanup_errors = self._cleanup()
        if failure is not None:
            if cleanup_errors:
                failure.add_note("; ".join(cleanup_errors))
            raise failure
        if cleanup_errors:
            raise EnvironmentCheckpointError("; ".join(cleanup_errors))
        if result is None:
            raise EnvironmentCheckpointError("Environment checkpoint gate produced no result")
        result["checks"]["bounded_cleanup_complete"] = True
        result["counts"]["docker_commands_total"] = self.runner.command_count
        result["working_root_removed"] = not self.working_root.exists()
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = EnvironmentCheckpointPrototype(image=arguments.image).run()
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
