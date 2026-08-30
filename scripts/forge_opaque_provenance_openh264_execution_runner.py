#!/usr/bin/env python3
"""执行 Issue #226 授权的 OpenH264 reachability 与单配对实验。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
REPO_SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(REPO_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_SCRIPT_ROOT))

import forge_opaque_provenance_openh264_candidate_gate as candidate  # noqa: E402
import forge_opaque_provenance_openh264_execution_protocol as protocol  # noqa: E402
import forge_opaque_provenance_r3_make_execution_failure_gate as failure_gate  # noqa: E402
import forge_opaque_provenance_r3_make_execution_runner as reference  # noqa: E402

DEFAULT_MANIFEST = protocol.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = Path("/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-openh264-execution-v1")
_IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_PACKAGE_BYTES = 2 * 1024 * 1024
CommandRunner = Callable[[list[str], int], subprocess.CompletedProcess[str]]
PackageDownloader = Callable[[dict[str, Any], Path], dict[str, Any]]


class OpenH264ExecutionError(RuntimeError):
    """OpenH264 execution 身份、fixture、委派或清理无效。"""


def _run_command(args: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def _docker(
    args: list[str],
    *,
    command_runner: CommandRunner,
    timeout_seconds: int = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = command_runner(["docker", *args], timeout_seconds)
    if check and completed.returncode != 0:
        operation = " ".join(args[:2])
        raise OpenH264ExecutionError(f"dependency fixture Docker 操作失败: {operation} (exit={completed.returncode})")
    return completed


def _download_verified_package(
    package: dict[str, Any],
    destination: Path,
) -> dict[str, Any]:
    request = urllib.request.Request(
        package["url"],
        headers={"User-Agent": "Forge-AutoCompiler/issue-226"},
    )
    digest = hashlib.sha256()
    size = 0
    with (
        urllib.request.urlopen(
            request,
            timeout=package["download_timeout_seconds"],
        ) as response,
        destination.open("xb") as stream,
    ):
        while chunk := response.read(64 * 1024):
            size += len(chunk)
            if size > _MAX_PACKAGE_BYTES:
                raise OpenH264ExecutionError("固定 nasm 包超过预注册大小上限")
            digest.update(chunk)
            stream.write(chunk)
    actual = digest.hexdigest()
    if actual != package["sha256"]:
        raise OpenH264ExecutionError("固定 nasm 包 SHA-256 不匹配")
    return {"sha256": actual, "size_bytes": size}


def _write_once(path: Path, value: dict[str, Any]) -> None:
    reference.v3_runner._write_once(path, value)


def _fixture_paths(
    manifest: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    evidence = manifest["evidence"]
    return (
        output_dir / evidence["dependency_fixture_marker"],
        output_dir / evidence["dependency_fixture_report"],
        output_dir / evidence["dependency_fixture_cleanup_report"],
    )


def _require_fixture_absent(
    manifest: dict[str, Any],
    *,
    command_runner: CommandRunner,
) -> None:
    fixture = manifest["dependency_fixture"]
    probes = (
        ["container", "inspect", fixture["preparation_container_name"]],
        ["image", "inspect", fixture["compile_image"]],
    )
    if any(
        _docker(
            args,
            command_runner=command_runner,
            timeout_seconds=30,
            check=False,
        ).returncode
        == 0
        for args in probes
    ):
        raise OpenH264ExecutionError("preflight 前存在 OpenH264 dependency fixture")


def _prepare_dependency_fixture(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
    release_revision: str,
    command_runner: CommandRunner = _run_command,
    downloader: PackageDownloader = _download_verified_package,
) -> dict[str, Any]:
    fixture = manifest["dependency_fixture"]
    marker, report_path, _cleanup_path = _fixture_paths(manifest, output_dir)
    digest = protocol.canonical_sha256(manifest)
    reference.v3_runner._claim_marker(
        marker,
        kind="forge_opaque_provenance_openh264_dependency_fixture",
        manifest_sha256=digest,
        revision=release_revision,
    )
    container = fixture["preparation_container_name"]
    image_tag = fixture["compile_image"]
    package = fixture["nasm_package"]
    image_id: str | None = None
    try:
        _require_fixture_absent(manifest, command_runner=command_runner)
        with tempfile.TemporaryDirectory(prefix="forge-openh264-issue226-") as directory:
            package_path = Path(directory) / "nasm.deb"
            package_evidence = downloader(package, package_path)
            if not package_path.is_file():
                raise OpenH264ExecutionError("dependency fixture 下载器未生成固定包")
            _docker(
                [
                    "create",
                    "--name",
                    container,
                    "--label",
                    f"{fixture['docker_label']}=true",
                    fixture["base_image"],
                    "sleep",
                    "infinity",
                ],
                command_runner=command_runner,
            )
            _docker(["start", container], command_runner=command_runner)
            _docker(
                ["cp", str(package_path), f"{container}:/tmp/nasm.deb"],
                command_runner=command_runner,
            )
            _docker(
                ["exec", container, "dpkg", "--install", "/tmp/nasm.deb"],
                command_runner=command_runner,
                timeout_seconds=120,
            )
            version = _docker(
                ["exec", container, "nasm", "-v"],
                command_runner=command_runner,
            ).stdout.strip()
            _docker(
                ["commit", "--no-pause", container, image_tag],
                command_runner=command_runner,
                timeout_seconds=120,
            )
        image_id = _docker(
            ["image", "inspect", image_tag, "--format", "{{.Id}}"],
            command_runner=command_runner,
        ).stdout.strip()
        if _IMAGE_ID_PATTERN.fullmatch(image_id) is None:
            raise OpenH264ExecutionError("dependency fixture image ID 无效")
        _docker(["rm", "--force", container], command_runner=command_runner)
        report = {
            "schema_version": "forge-openh264-dependency-fixture-1.0.0",
            "document_type": "forge_openh264_dependency_fixture",
            "manifest_sha256": digest,
            "release_revision": release_revision,
            "base_image": fixture["base_image"],
            "compile_image": image_tag,
            "image_id": image_id,
            "package_sha256": package_evidence["sha256"],
            "package_size_bytes": package_evidence["size_bytes"],
            "nasm_version_sha256": hashlib.sha256(version.encode("utf-8")).hexdigest(),
            "apt_index_downloaded": False,
            "preparation_container_removed": True,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _write_once(report_path, report)
    except BaseException as exc:
        reference.v3_runner._finish_marker(
            marker,
            status="failed",
            error_class=type(exc).__name__,
        )
        _cleanup_dependency_fixture(
            manifest,
            output_dir=output_dir,
            image_id=image_id,
            command_runner=command_runner,
        )
        raise
    reference.v3_runner._finish_marker(marker, status="passed")
    return report


def _cleanup_dependency_fixture(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
    image_id: str | None,
    command_runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    fixture = manifest["dependency_fixture"]
    _marker, _report, cleanup_path = _fixture_paths(manifest, output_dir)
    container = fixture["preparation_container_name"]
    image_tag = fixture["compile_image"]
    _docker(
        ["rm", "--force", container],
        command_runner=command_runner,
        check=False,
    )
    _docker(
        ["image", "rm", "--force", image_tag],
        command_runner=command_runner,
        check=False,
    )
    if image_id is not None:
        _docker(
            ["image", "rm", "--force", image_id],
            command_runner=command_runner,
            check=False,
        )
    container_absent = (
        _docker(
            ["container", "inspect", container],
            command_runner=command_runner,
            check=False,
        ).returncode
        != 0
    )
    tag_absent = (
        _docker(
            ["image", "inspect", image_tag],
            command_runner=command_runner,
            check=False,
        ).returncode
        != 0
    )
    image_absent = image_id is None or (
        _docker(
            ["image", "inspect", image_id],
            command_runner=command_runner,
            check=False,
        ).returncode
        != 0
    )
    cleanup = {
        "schema_version": "forge-openh264-dependency-fixture-cleanup-1.0.0",
        "document_type": "forge_openh264_dependency_fixture_cleanup",
        "manifest_sha256": protocol.canonical_sha256(manifest),
        "container_absent": container_absent,
        "tag_absent": tag_absent,
        "image_id_absent": image_absent,
        "cleanup_succeeded": container_absent and tag_absent and image_absent,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _write_once(cleanup_path, cleanup)
    if cleanup["cleanup_succeeded"] is not True:
        raise OpenH264ExecutionError("OpenH264 dependency fixture cleanup 未闭合")
    return cleanup


def _lifecycle_adapter(compile_image: str) -> SimpleNamespace:
    adapter = candidate.build_docker_adapter(compile_image)
    base_lifecycle, _construction, _r3_runtime, _failure_gate = candidate._runtime_modules()
    adapter._parent_invocation = candidate._parent_invocation
    adapter.reference = base_lifecycle.reference
    return adapter


@contextmanager
def _reference_runtime_hooks() -> Iterator[None]:
    parity, observability = failure_gate.build_runtime_bindings()
    adapter = _lifecycle_adapter(protocol.COMPILE_IMAGE)
    originals = {
        "protocol": reference.protocol,
        "make_lifecycle": reference.make_lifecycle,
        "make_parity": reference.make_parity,
        "make_observability": reference.make_observability,
        "policy": reference._policy,
        "classify_arm_terminal": reference.v2_runner.classify_arm_terminal,
    }

    def openh264_policy(
        manifest: dict[str, Any],
        *,
        arm: str,
        image_id: str,
    ) -> Any:
        return replace(
            originals["policy"](manifest, arm=arm, image_id=image_id),
            benchmark_id="forge-opaque-provenance-openh264-execution",
        )

    reference.protocol = protocol
    reference.make_lifecycle = adapter
    reference.make_parity = parity
    reference.make_observability = observability
    reference._policy = openh264_policy

    def classify_arm_terminal(
        manifest: dict[str, Any],
        *,
        arm: str,
        ledger: Any,
        error: Exception,
    ) -> dict[str, Any]:
        invalid = failure_gate.classify_pre_model_failure(
            arm=arm,
            ledger=ledger,
            error=error,
        )
        if invalid is not None:
            return invalid
        return originals["classify_arm_terminal"](
            manifest,
            arm=arm,
            ledger=ledger,
            error=error,
        )

    reference.v2_runner.classify_arm_terminal = classify_arm_terminal
    try:
        yield
    finally:
        reference.protocol = originals["protocol"]
        reference.make_lifecycle = originals["make_lifecycle"]
        reference.make_parity = originals["make_parity"]
        reference.make_observability = originals["make_observability"]
        reference._policy = originals["policy"]
        reference.v2_runner.classify_arm_terminal = originals["classify_arm_terminal"]


def collect_preflight(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    require_empty: bool,
    command_runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    static_gate = candidate.validate_static_gate(repo_root)
    construction = asyncio.run(candidate.validate_agent_construction())
    with _reference_runtime_hooks():
        result = reference.collect_preflight(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            require_empty=require_empty,
        )
    _require_fixture_absent(manifest, command_runner=command_runner)
    return {
        **result,
        "openh264_static_gate": static_gate["parent_history_prefix_preserved"],
        "full_agent_construction_gate": construction["status"],
        "dependency_fixture_absent": True,
    }


def execute_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
) -> dict[str, Any]:
    collect_preflight(
        manifest,
        output_dir=output_dir,
        repo_root=repo_root,
        require_empty=True,
    )
    with _reference_runtime_hooks():
        return reference.execute_reachability(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            model_factory=model_factory,
        )


def execute_pair(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Any | None = None,
    command_runner: CommandRunner = _run_command,
    downloader: PackageDownloader = _download_verified_package,
) -> dict[str, Any]:
    preflight = collect_preflight(
        manifest,
        output_dir=output_dir,
        repo_root=repo_root,
        require_empty=False,
        command_runner=command_runner,
    )
    fixture: dict[str, Any] | None = None
    operation_error: BaseException | None = None
    with _reference_runtime_hooks():
        reachability = reference.legacy._passed_reachability(
            manifest,
            output_dir,
            preflight["release_revision"],
        )
        original_passed = reference.legacy._passed_reachability
        try:
            fixture = _prepare_dependency_fixture(
                manifest,
                output_dir=output_dir,
                release_revision=preflight["release_revision"],
                command_runner=command_runner,
                downloader=downloader,
            )
            reference.legacy._passed_reachability = lambda *_args, **_kwargs: reachability
            return reference.execute_pair(
                manifest,
                output_dir=output_dir,
                repo_root=repo_root,
                model_factory=model_factory,
            )
        except BaseException as exc:
            operation_error = exc
            raise
        finally:
            reference.legacy._passed_reachability = original_passed
            if fixture is not None:
                try:
                    _cleanup_dependency_fixture(
                        manifest,
                        output_dir=output_dir,
                        image_id=fixture["image_id"],
                        command_runner=command_runner,
                    )
                except BaseException as cleanup_error:
                    if operation_error is None:
                        raise
                    raise cleanup_error from operation_error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate", "preflight", "reachability", "pair"),
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest)
    if args.command == "validate":
        protocol.verify_frozen_components(manifest)
        parity, observability = failure_gate.build_runtime_bindings()
        result: Any = {
            "status": "valid",
            "manifest_sha256": protocol.canonical_sha256(manifest),
            "corrected_runtime_bindings": all(
                hasattr(namespace, name)
                for namespace, name in (
                    (parity, "FrozenActionPolicy"),
                    (parity, "SerialToolCallMiddleware"),
                    (observability, "RejectionObservationRegistry"),
                    (observability, "ObservableRuntimeParityToolAdapter"),
                )
            ),
            "provider_calls": 0,
            "formal_attempts": 0,
            "model_tokens": 0,
        }
    elif args.command == "preflight":
        result = collect_preflight(
            manifest,
            output_dir=args.output_dir,
            require_empty=True,
        )
    elif args.command == "reachability":
        result = execute_reachability(manifest, output_dir=args.output_dir)
    else:
        result = execute_pair(manifest, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
