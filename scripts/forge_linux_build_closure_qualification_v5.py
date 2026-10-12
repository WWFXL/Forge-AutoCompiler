#!/usr/bin/env python3
"""Issue #417 Linux 构建闭合资格 v5 机制与 canary runner。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend/packages/harness"
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from deerflow.compile.operations import _classify_compiled_artifact  # noqa: E402

IDENTITY = "cpp-jev-natural-failure-linux-build-closure-canary-v5"
DEFAULT_CASES_PATH = REPO_ROOT / "benchmarks/fixtures/linux-build-closure-v5/cases.json"
SYSTEMS = ("cmake", "make", "autotools")
COMPILED_TYPES = frozenset({"executable", "shared_library", "static_library", "object"})
ELF_MAGIC = b"\x7fELF"
AR_MAGIC = b"!<arch>\n"
AR_HEADER_SIZE = 60
AR_TRAILER = b"`\n"
MACHO_MAGICS = frozenset(
    {
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
    }
)
PROBE_PATH_PATTERNS = (
    re.compile(r"(?:^|/)CMakeFiles/(?:[^/]+/)?CompilerId", re.IGNORECASE),
    re.compile(
        r"(?:^|/)CMakeFiles/(?:[^/]+/)?CMakeDetermineCompilerABI_[A-Za-z0-9_]+\.bin$",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|/)CMakeFiles/(?:CMakeScratch|CMakeTmp)(?:/|$)", re.IGNORECASE),
    re.compile(r"(?:^|/)conftest(?:\.|$)", re.IGNORECASE),
)
NETWORK_PATTERNS = (
    "could not resolve host",
    "could not resolve hostname",
    "temporary failure in name resolution",
    "network is unreachable",
    "failed to connect to",
    "unable to access 'http",
    'unable to access "http',
    "download step failed",
    "failed to download",
)
ERROR_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "configure_required",
        (
            "no makefile found",
            "no targets specified and no makefile found",
            "please run configure",
            "no rule to make target 'config.mk'",
        ),
    ),
    (
        "missing_dependency",
        (
            "could not find package",
            "could not find a package configuration file",
            "package requirements (",
            "required package",
            "not found (missing:",
            "fatal error:",
            "no such file or directory",
        ),
    ),
    (
        "missing_tool",
        (
            "command not found",
            "not found in path",
            "unable to find executable",
            "could not find program",
            "not found",
        ),
    ),
    (
        "target_or_layout_error",
        (
            "no rule to make target",
            "does not appear to contain cmakelists.txt",
            "the source directory",
        ),
    ),
    ("compile_error", ("error:", "undefined reference to", "collect2: error")),
)
TARGET_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "apple_toolchain",
        re.compile(
            r"(?:\bxcrun\b|\blipo\b|\b-?target\s+[^\s]*apple|\b-?framework\s+|CMAKE_OSX_SYSROOT)",
            re.IGNORECASE,
        ),
    ),
    (
        "windows_toolchain",
        re.compile(
            r"(?:\bmsbuild(?:\.exe)?\b|\bcl(?:\.exe)?\b|\blink\.exe\b|\b(?:i686|x86_64)-w64-mingw32-|\s-mwindows\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "android_target",
        re.compile(
            r"(?:\bandroid[_ -]?ndk\b|/ndk/|\b[a-z0-9_+.-]+-linux-android(?:\d+)?-)",
            re.IGNORECASE,
        ),
    ),
    (
        "console_toolchain",
        re.compile(
            r"(?:\barm-vita-eabi-|\bpowerpc-eabi-|\bdevkitpro\b|\bxedk\b|\b(?:psp|vita|xbox|wii)(?:sdk|toolchain)\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "bare_metal_toolchain",
        re.compile(
            r"(?:\b(?:arm|aarch64|riscv\d*|mips\w*|xtensa\w*|avr)-[^\s/]*(?:none|elf)[^\s/]*-(?:gcc|g\+\+|clang|cc|c\+\+)|\bavr-(?:gcc|g\+\+))",
            re.IGNORECASE,
        ),
    ),
    (
        "freestanding_flags",
        re.compile(
            r"(?:^|\s)(?:-ffreestanding|-nostdlib|-nostartfiles)(?:\s|$)", re.IGNORECASE
        ),
    ),
    (
        "foreign_target_flag",
        re.compile(
            r"(?:--target=|-target\s+)(?!x86_64-linux-gnu\b)[a-z0-9_.+-]+",
            re.IGNORECASE,
        ),
    ),
    (
        "kernel_build_contract",
        re.compile(
            r"(?:\bKernelPlatform\b.{0,80}\bnot set\b|\bvalid platforms are\b.{0,120}\bqemu-(?:arm|riscv)|\b-ffreestanding\b.{0,120}\bkernel\b)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "device_firmware_contract",
        re.compile(
            r"(?:\bfirmware/[A-Za-z0-9_.+-]+/rootfs/|\bunpack\b.{0,80}\bfirmware first\b)",
            re.IGNORECASE,
        ),
    ),
)
PRODUCER_TOOL_PATTERN = re.compile(
    r"(?:^|[\s/])(?:gcc(?:-\d+)?|g\+\+(?:-\d+)?|clang(?:\+\+)?|cc|c\+\+|ld|ar)(?:\s|$)",
    re.IGNORECASE,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return _sha256_bytes(payload)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根必须是 object: {path}")
    return value


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _run(
    argv: list[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int | float | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _preview(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _elf_machine_from_bytes(value: bytes) -> int | None:
    if len(value) < 20 or not value.startswith(ELF_MAGIC):
        return None
    if value[5] == 1:
        byte_order = "<"
    elif value[5] == 2:
        byte_order = ">"
    else:
        return None
    return int(struct.unpack(f"{byte_order}H", value[18:20])[0])


def _elf_machine(path: Path) -> int | None:
    try:
        with path.open("rb") as handle:
            return _elf_machine_from_bytes(handle.read(64))
    except OSError:
        return None


def _archive_member_machines(path: Path) -> list[int]:
    machines: list[int] = []
    try:
        file_size = path.stat().st_size
        with path.open("rb") as stream:
            if stream.read(len(AR_MAGIC)) != AR_MAGIC:
                return []
            offset = len(AR_MAGIC)
            while offset < file_size:
                if offset + AR_HEADER_SIZE > file_size:
                    return []
                stream.seek(offset)
                header = stream.read(AR_HEADER_SIZE)
                if len(header) != AR_HEADER_SIZE or header[58:60] != AR_TRAILER:
                    return []
                member_size = int(header[48:58].decode("ascii").strip())
                member_name = header[:16].decode("ascii").strip()
                payload_offset = offset + AR_HEADER_SIZE
                payload_size = member_size
                if member_name.startswith("#1/"):
                    embedded_name_size = int(member_name[3:])
                    payload_offset += embedded_name_size
                    payload_size -= embedded_name_size
                if payload_size >= 20 and member_name not in {
                    "/",
                    "//",
                    "__.SYMDEF",
                    "__.SYMDEF SORTED",
                }:
                    stream.seek(payload_offset)
                    machine = _elf_machine_from_bytes(
                        stream.read(min(payload_size, 64))
                    )
                    if machine is not None:
                        machines.append(machine)
                offset += AR_HEADER_SIZE + member_size + (member_size % 2)
    except (OSError, UnicodeDecodeError, ValueError):
        return []
    return machines


def _binary_format(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            magic = handle.read(8)
    except OSError:
        return None
    if magic.startswith(ELF_MAGIC):
        return "elf"
    if magic.startswith(AR_MAGIC):
        return "ar"
    if magic.startswith(b"MZ"):
        return "pe"
    if magic[:4] in MACHO_MAGICS:
        return "macho"
    return None


def inspect_artifact(
    path: Path, *, relative_path: str, host_elf_machine: int
) -> dict[str, Any] | None:
    artifact_type = _classify_compiled_artifact(path)
    binary_format = _binary_format(path)
    if artifact_type is None and binary_format not in {"pe", "macho"}:
        return None
    machines = (
        _archive_member_machines(path) if artifact_type == "static_library" else []
    )
    if artifact_type in {"executable", "shared_library", "object"}:
        machine = _elf_machine(path)
        machines = [machine] if machine is not None else []
    return {
        "relative_path": relative_path,
        "size": path.stat().st_size,
        "sha256": _sha256_file(path),
        "artifact_type": artifact_type,
        "binary_format": binary_format,
        "elf_machines": sorted(set(machines)),
        "host_machine_match": bool(machines)
        and all(machine == host_elf_machine for machine in machines),
    }


def _is_probe_path(relative_path: str) -> bool:
    return any(pattern.search(relative_path) for pattern in PROBE_PATH_PATTERNS)


def snapshot_files(
    root: Path, *, maximum_files: int = 100_000
) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            ".git" in relative.parts
            or ".forge-home" in relative.parts
            or path.is_symlink()
        ):
            continue
        try:
            mode = path.stat().st_mode
        except OSError:
            continue
        if not stat.S_ISREG(mode):
            continue
        result[relative.as_posix()] = (path.stat().st_size, path.stat().st_mtime_ns)
        if len(result) > maximum_files:
            raise RuntimeError("workspace_file_limit_exceeded")
    return result


def inspect_changed_artifacts(
    root: Path,
    before: dict[str, tuple[int, int]],
    *,
    host_elf_machine: int,
) -> list[dict[str, Any]]:
    after = snapshot_files(root)
    artifacts: list[dict[str, Any]] = []
    for relative_path, fingerprint in sorted(after.items()):
        if before.get(relative_path) == fingerprint or _is_probe_path(relative_path):
            continue
        details = inspect_artifact(
            root / relative_path,
            relative_path=relative_path,
            host_elf_machine=host_elf_machine,
        )
        if details is not None:
            artifacts.append(details)
    return artifacts


def attach_producer_evidence(
    artifacts: list[dict[str, Any]], execution_text: str
) -> None:
    lines = execution_text.splitlines()
    for artifact in artifacts:
        relative_path = str(artifact["relative_path"])
        basename = Path(relative_path).name
        producing_lines = [
            line
            for line in lines
            if (relative_path in line or basename in line)
            and PRODUCER_TOOL_PATTERN.search(line)
        ]
        artifact["producer_evidence"] = bool(producing_lines)
        artifact["producer_line_sha256"] = (
            _sha256_bytes(producing_lines[-1].encode()) if producing_lines else None
        )


def extract_target_signals(text: str) -> list[str]:
    return sorted(
        name for name, pattern in TARGET_SIGNAL_PATTERNS if pattern.search(text)
    )


def normalize_failure(text: str) -> tuple[str, str]:
    normalized = text.lower()
    normalized = re.sub(r"/workspace(?:/[^\s:'\"]+)*", "<workspace>", normalized)
    normalized = re.sub(r":\d+(?::\d+)?", ":<line>", normalized)
    if any(pattern in normalized for pattern in NETWORK_PATTERNS):
        return "network_dependency_failure", "network_dependency"
    for category, patterns in ERROR_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return "bounded_failure", category
    return "bounded_failure", "unknown_build_failure"


def classify_observation(
    observation: dict[str, Any], *, host_elf_machine: int
) -> dict[str, Any]:
    commands = observation.get("commands", [])
    artifacts = observation.get("artifacts", [])
    signals = sorted(set(observation.get("target_signals", [])))
    foreign_artifacts = [
        row
        for row in artifacts
        if row.get("binary_format") in {"pe", "macho"}
        or (row.get("elf_machines") and not row.get("host_machine_match"))
    ]
    host_artifacts = [
        row
        for row in artifacts
        if row.get("artifact_type") in COMPILED_TYPES
        and row.get("host_machine_match")
        and row.get("elf_machines")
        and row.get("producer_evidence") is True
    ]
    final = commands[-1] if commands else {}
    failure_phase = final.get("phase")
    if observation.get("infrastructure_failure") or any(
        row.get("infrastructure_failure") for row in commands
    ):
        classification, category = "infrastructure_failure", "docker_runtime_failure"
    elif observation.get("timed_out") or any(row.get("timed_out") for row in commands):
        classification, category = "timeout", "timeout"
    elif signals or foreign_artifacts:
        classification, category = (
            "non_host_target",
            signals[0] if signals else "foreign_binary_format_or_machine",
        )
    elif commands and all(row.get("exit_code") == 0 for row in commands):
        if host_artifacts:
            classification, category = "host_userland_closure", None
        elif any(row.get("artifact_type") in COMPILED_TYPES for row in artifacts):
            classification, category = (
                "target_unresolved_success",
                "artifact_machine_unresolved",
            )
        else:
            classification, category = (
                "no_compiled_artifact",
                "default_path_produced_no_compiled_artifact",
            )
    elif commands:
        combined = str(observation.get("_failure_text", ""))
        classification, category = normalize_failure(combined)
    else:
        classification, category = "infrastructure_failure", "no_commands_observed"
    return {
        "classification": classification,
        "failure_phase": failure_phase
        if classification not in {"host_userland_closure", "no_compiled_artifact"}
        else None,
        "error_category": category,
        "target_signals": signals,
        "host_artifact_signature": sorted(
            (row["relative_path"], row["artifact_type"], tuple(row["elf_machines"]))
            for row in host_artifacts
        ),
        "foreign_artifact_count": len(foreign_artifacts),
        "host_elf_machine": host_elf_machine,
    }


def aggregate_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    if len(observations) != 2:
        raise ValueError("v5 mechanism qualification requires exactly two observations")
    classes = [row["classification"] for row in observations]
    if any(value == "infrastructure_failure" for value in classes):
        classification, reason = (
            "infrastructure_failure",
            "observation_infrastructure_failure",
        )
    elif any(value == "timeout" for value in classes):
        classification, reason = "timeout", "observation_timeout"
    elif classes == ["non_host_target", "non_host_target"]:
        classification, reason = (
            "stable_non_host_target",
            "two_clean_observations_show_non_host_target",
        )
    elif classes == ["host_userland_closure", "host_userland_closure"]:
        signatures = [row["host_artifact_signature"] for row in observations]
        if signatures[0] == signatures[1]:
            classification, reason = (
                "stable_host_userland_closure",
                "two_clean_host_artifact_signatures_agree",
            )
        else:
            classification, reason = (
                "inconsistent_observation",
                "host_artifact_signatures_differ",
            )
    elif classes == ["no_compiled_artifact", "no_compiled_artifact"]:
        classification, reason = (
            "stable_no_compiled_artifact",
            "two_clean_default_paths_produced_no_artifact",
        )
    elif classes == ["bounded_failure", "bounded_failure"]:
        facts = [(row["failure_phase"], row["error_category"]) for row in observations]
        if facts[0] == facts[1]:
            classification, reason = (
                "stable_failure_candidate",
                "two_clean_failures_agree_target_unresolved",
            )
        else:
            classification, reason = (
                "inconsistent_observation",
                "failure_phase_or_category_differs",
            )
    elif classes == ["network_dependency_failure", "network_dependency_failure"]:
        classification, reason = (
            "network_dependency_excluded",
            "two_clean_network_failures",
        )
    elif classes == ["target_unresolved_success", "target_unresolved_success"]:
        classification, reason = "target_unresolved", "artifact_machine_unresolved"
    else:
        classification, reason = (
            "inconsistent_observation",
            "observation_classes_differ",
        )
    return {
        "classification": classification,
        "reason": reason,
        "observation_classes": classes,
        "eligible_as_natural_failure": False,
    }


def validate_reference_recipe(
    recipe: dict[str, Any], *, build_system: str
) -> dict[str, Any]:
    errors: list[str] = []
    commands = recipe.get("commands")
    artifact_paths = recipe.get("artifact_paths")
    if not isinstance(commands, list) or not commands:
        errors.append("commands_missing")
        commands = []
    if not isinstance(artifact_paths, list) or not artifact_paths:
        errors.append("artifact_paths_missing")
        artifact_paths = []
    allowed_phases = {"dependency", "configure", "build"}
    for index, row in enumerate(commands):
        if (
            not isinstance(row, dict)
            or row.get("phase") not in allowed_phases
            or not isinstance(row.get("command"), str)
        ):
            errors.append(f"invalid_command:{index}")
    build_commands = [
        row for row in commands if isinstance(row, dict) and row.get("phase") == "build"
    ]
    expected_build = default_commands(REPO_ROOT, build_system)[-1]["command"]
    if len(build_commands) != 1 or build_commands[0].get("command") != expected_build:
        errors.append("default_build_command_not_bound")
    if (
        not commands
        or not isinstance(commands[-1], dict)
        or commands[-1].get("phase") != "build"
    ):
        errors.append("default_build_command_not_final")
    for index, value in enumerate(artifact_paths):
        if (
            not isinstance(value, str)
            or not value
            or value.startswith("/")
            or ".." in Path(value).parts
        ):
            errors.append(f"unsafe_artifact_path:{index}")
    return {
        "valid": not errors,
        "errors": errors,
        "default_build_bound": "default_build_command_not_bound" not in errors
        and "default_build_command_not_final" not in errors,
    }


def qualify_project(
    default_path: dict[str, Any], reference_path: dict[str, Any] | None
) -> dict[str, Any]:
    default_class = default_path["classification"]
    reference_class = reference_path["classification"] if reference_path else None
    reference_contract = (
        reference_path.get("reference_contract", {}) if reference_path else {}
    )
    if (
        default_class == "stable_failure_candidate"
        and reference_class == "stable_host_userland_closure"
        and reference_contract.get("valid") is True
        and reference_contract.get("default_build_bound") is True
        and reference_path.get("source_identity_clean") is True
    ):
        return {
            "classification": "qualified_natural_failure",
            "eligible_as_natural_failure": True,
            "reason": "stable_default_failure_and_reference_host_closure",
        }
    reasons = {
        "stable_host_userland_closure": "default_path_already_succeeds",
        "stable_non_host_target": "default_path_targets_non_host_endpoint",
        "stable_no_compiled_artifact": "default_path_has_no_compiled_artifact",
        "stable_failure_candidate": "reference_host_closure_required",
    }
    if (
        default_class == "stable_failure_candidate"
        and reference_class == "stable_host_userland_closure"
    ):
        reason = "reference_contract_or_source_identity_invalid"
    else:
        reason = reasons.get(default_class, f"default_path_{default_class}")
    return {
        "classification": "not_qualified",
        "eligible_as_natural_failure": False,
        "reason": reason,
    }


def default_commands(source: Path, build_system: str) -> list[dict[str, str]]:
    if build_system == "cmake":
        return [
            {
                "phase": "configure",
                "command": "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_VERBOSE_MAKEFILE=ON -DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            },
            {"phase": "build", "command": "cmake --build build --verbose --parallel 4"},
        ]
    if build_system == "make":
        return [{"phase": "build", "command": "make --trace -j4 V=1 VERBOSE=1"}]
    if build_system == "autotools":
        if (source / "autogen.sh").is_file():
            bootstrap = "./autogen.sh"
        elif (source / "bootstrap").is_file():
            bootstrap = "./bootstrap"
        else:
            bootstrap = "autoreconf -fi"
        return [
            {"phase": "configure", "command": bootstrap},
            {"phase": "configure", "command": "./configure"},
            {"phase": "build", "command": "make --trace -j4 V=1 VERBOSE=1"},
        ]
    raise ValueError(f"unknown build system: {build_system}")


def _remove_container(name: str) -> bool:
    completed = _run(["docker", "rm", "-f", name], timeout=30)
    return completed.returncode == 0 or "No such container" in completed.stderr


def managed_containers() -> list[str]:
    completed = _run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=forge.experiment={IDENTITY}",
            "--format",
            "{{.Names}}",
        ],
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "docker ps failed")
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _run_docker_command(
    *,
    workspace: Path,
    command: dict[str, str],
    case_id: str,
    replicate: int,
    image: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    name = f"forge-417-{case_id[:24]}-{replicate}-{uuid.uuid4().hex[:8]}"
    argv = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--cpus",
        "4",
        "--label",
        "forge.managed=true",
        "--label",
        f"forge.experiment={IDENTITY}",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "HOME=/tmp",
        "--env",
        "LC_ALL=C",
        "--volume",
        f"{workspace}:/workspace:rw",
        "--workdir",
        "/workspace",
        image,
        "bash",
        "-lc",
        f"set -euo pipefail\n{command['command']}",
    ]
    started = time.monotonic()
    try:
        completed = _run(argv, timeout=timeout_seconds)
        return {
            **command,
            "exit_code": completed.returncode,
            "timed_out": False,
            "infrastructure_failure": completed.returncode == 125
            or completed.stderr.startswith("docker:"),
            "elapsed_seconds": time.monotonic() - started,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            **command,
            "exit_code": None,
            "timed_out": True,
            "infrastructure_failure": False,
            "elapsed_seconds": time.monotonic() - started,
            "stdout": _timeout_text(exc.stdout),
            "stderr": _timeout_text(exc.stderr),
        }
    finally:
        _remove_container(name)


def _persist_command_log(
    root: Path, index: int, command: dict[str, Any]
) -> dict[str, Any]:
    stdout = str(command.pop("stdout"))
    stderr = str(command.pop("stderr"))
    stdout_path = root / f"command-{index}.stdout.log"
    stderr_path = root / f"command-{index}.stderr.log"
    stdout_path.write_text(stdout, encoding="utf-8", errors="replace")
    stderr_path.write_text(stderr, encoding="utf-8", errors="replace")
    return {
        **command,
        "stdout_path": str(stdout_path.relative_to(REPO_ROOT))
        if stdout_path.is_relative_to(REPO_ROOT)
        else str(stdout_path),
        "stderr_path": str(stderr_path.relative_to(REPO_ROOT))
        if stderr_path.is_relative_to(REPO_ROOT)
        else str(stderr_path),
        "stdout_sha256": _sha256_bytes(stdout.encode()),
        "stderr_sha256": _sha256_bytes(stderr.encode()),
        "stdout_preview": _preview(stdout),
        "stderr_preview": _preview(stderr),
        "_signal_text": f"{stdout}\n{stderr}",
    }


def run_observation(
    *,
    source: Path,
    workspace: Path,
    evidence_root: Path,
    case: dict[str, Any],
    replicate: int,
    image: str,
    command_timeout_seconds: int,
    session_timeout_seconds: int,
    host_elf_machine: int,
) -> dict[str, Any]:
    started = time.monotonic()
    replicate_root = (
        evidence_root / "cases" / case["case_id"] / f"replicate-{replicate}"
    )
    replicate_root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, workspace, symlinks=True)
    before = snapshot_files(workspace)
    observed: list[dict[str, Any]] = []
    try:
        for command in default_commands(workspace, case["build_system"]):
            remaining = session_timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                row = {
                    **command,
                    "exit_code": None,
                    "timed_out": True,
                    "infrastructure_failure": False,
                    "elapsed_seconds": 0.0,
                    "stdout": "",
                    "stderr": "session timeout before command",
                }
            else:
                row = _run_docker_command(
                    workspace=workspace,
                    command=command,
                    case_id=case["case_id"],
                    replicate=replicate,
                    image=image,
                    timeout_seconds=max(
                        1, min(command_timeout_seconds, int(remaining))
                    ),
                )
            persisted = _persist_command_log(replicate_root, len(observed) + 1, row)
            observed.append(persisted)
            if (
                persisted["exit_code"] != 0
                or persisted["timed_out"]
                or persisted["infrastructure_failure"]
            ):
                break
        artifacts = inspect_changed_artifacts(
            workspace, before, host_elf_machine=host_elf_machine
        )
        signal_text = "\n".join(str(row.pop("_signal_text")) for row in observed)
        attach_producer_evidence(artifacts, signal_text)
        observation = {
            "replicate": replicate,
            "commands": observed,
            "artifacts": artifacts,
            "target_signals": extract_target_signals(signal_text),
            "elapsed_seconds": time.monotonic() - started,
            "timed_out": any(row["timed_out"] for row in observed),
            "infrastructure_failure": any(
                row["infrastructure_failure"] for row in observed
            ),
            "_failure_text": signal_text,
        }
        observation.update(
            classify_observation(observation, host_elf_machine=host_elf_machine)
        )
        observation.pop("_failure_text")
        _write_json_atomic(replicate_root / "observation.json", observation)
        return observation
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def clone_exact_source(
    case: dict[str, Any], destination: Path, *, timeout_seconds: int
) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    stages = [
        (["git", "init", "--quiet"], "init"),
        (["git", "remote", "add", "origin", case["repository_url"]], "remote"),
        (["git", "fetch", "--depth", "1", "origin", case["commit_sha"]], "fetch"),
        (["git", "checkout", "--detach", "FETCH_HEAD"], "checkout"),
    ]
    observed: list[dict[str, Any]] = []
    for argv, name in stages:
        try:
            completed = _run(argv, cwd=destination, timeout=timeout_seconds, env=env)
            row = {
                "stage": name,
                "exit_code": completed.returncode,
                "timed_out": False,
                "stdout_sha256": _sha256_bytes(completed.stdout.encode()),
                "stderr_sha256": _sha256_bytes(completed.stderr.encode()),
                "stderr_preview": _preview(completed.stderr),
            }
        except subprocess.TimeoutExpired as exc:
            row = {
                "stage": name,
                "exit_code": None,
                "timed_out": True,
                "stdout_sha256": _sha256_bytes(_timeout_text(exc.stdout).encode()),
                "stderr_sha256": _sha256_bytes(_timeout_text(exc.stderr).encode()),
                "stderr_preview": _preview(_timeout_text(exc.stderr)),
            }
        observed.append(row)
        if row["exit_code"] != 0 or row["timed_out"]:
            return {"succeeded": False, "stages": observed, "failed_stage": name}
    head = _run(["git", "rev-parse", "HEAD"], cwd=destination, timeout=30)
    return {
        "succeeded": head.returncode == 0 and head.stdout.strip() == case["commit_sha"],
        "stages": observed,
        "head": head.stdout.strip(),
    }


def _runtime_fingerprint(image: str) -> dict[str, Any]:
    image_result = _run(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            "{{.Id}} {{.Architecture}} {{.Os}}",
        ],
        timeout=30,
    )
    compiler_result = _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            image,
            "bash",
            "-lc",
            "uname -m; gcc -dumpmachine; g++ -dumpmachine",
        ],
        timeout=30,
    )
    if image_result.returncode != 0 or compiler_result.returncode != 0:
        raise RuntimeError("runtime_fingerprint_failed")
    lines = compiler_result.stdout.splitlines()
    if len(lines) != 3:
        raise RuntimeError("runtime_fingerprint_shape_invalid")
    return {
        "image": image,
        "image_inspect": image_result.stdout.strip(),
        "uname_machine": lines[0],
        "cc_target": lines[1],
        "cxx_target": lines[2],
        "host_elf_machine": 62 if lines[0] == "x86_64" else None,
    }


def evaluate_canary(results: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    groups = Counter(row["audit_group"] for row in results)
    if groups != Counter(
        {"non_host_negative": 6, "linux_positive": 2, "no_default_artifact_risk": 2}
    ):
        failures.append("audit_group_count_mismatch")
    for row in results:
        aggregate = row.get("default_path", {}).get("classification")
        if (
            row["audit_group"] == "linux_positive"
            and aggregate == "stable_non_host_target"
        ):
            failures.append(f"linux_positive_misclassified_non_host:{row['case_id']}")
        if (
            row["audit_group"] == "non_host_negative"
            and aggregate == "stable_host_userland_closure"
        ):
            failures.append(f"non_host_misclassified_host_closure:{row['case_id']}")
        if (
            row["audit_group"] == "no_default_artifact_risk"
            and aggregate == "stable_host_userland_closure"
        ):
            failures.append(
                f"no_artifact_risk_misclassified_host_closure:{row['case_id']}"
            )
        if aggregate == "infrastructure_failure":
            failures.append(f"case_infrastructure_failure:{row['case_id']}")
        if row.get("project_qualification", {}).get("eligible_as_natural_failure"):
            failures.append(
                f"case_entered_natural_failure_without_reference:{row['case_id']}"
            )
    if not any(
        row.get("default_path", {}).get("classification")
        == "stable_host_userland_closure"
        for row in results
    ):
        failures.append("no_real_host_userland_closure_observed")
    if managed_containers():
        failures.append("managed_containers_remain")
    return {
        "passed": not failures,
        "decision": "proceed_to_formal_build_reference_qualification_design"
        if not failures
        else "stop_linux_build_closure_v5",
        "failed_requirements": failures,
        "counts": Counter(
            row.get("default_path", {}).get("classification", "missing")
            for row in results
        ),
    }


def run_canary(args: argparse.Namespace) -> dict[str, Any]:
    cases_path = args.cases.resolve()
    output_path = args.output.resolve()
    evidence_root = args.evidence_root.resolve()
    work_root = args.work_root.resolve()
    for path in (output_path, evidence_root, work_root):
        if path.exists():
            raise FileExistsError(f"create-once path already exists: {path}")
    runtime_check = _run(
        [str(REPO_ROOT / "scripts/require-docker-runtime.sh")], timeout=60
    )
    if runtime_check.returncode != 0:
        raise RuntimeError(runtime_check.stderr.strip() or runtime_check.stdout.strip())
    if managed_containers():
        raise RuntimeError("managed_containers_present_before_canary")
    fixture = _load_json(cases_path)
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("canary cases missing")
    fingerprint = _runtime_fingerprint(args.image)
    if fingerprint["host_elf_machine"] is None:
        raise ValueError("unsupported_host_machine")
    evidence_root.mkdir(parents=True)
    work_root.mkdir(parents=True)
    started_at = _utc_now()
    results: list[dict[str, Any]] = []
    try:
        for case in cases:
            if case.get("build_system") not in SYSTEMS or not re.fullmatch(
                r"[0-9a-f]{40}", str(case.get("commit_sha"))
            ):
                raise ValueError(f"invalid case: {case.get('case_id')}")
            source = work_root / f"source-{case['case_id']}"
            try:
                source_result = clone_exact_source(
                    case, source, timeout_seconds=args.source_timeout_seconds
                )
                case_result: dict[str, Any] = {
                    **case,
                    "source": source_result,
                    "observations": [],
                }
                if source_result["succeeded"]:
                    for replicate in (1, 2):
                        case_result["observations"].append(
                            run_observation(
                                source=source,
                                workspace=work_root
                                / f"workspace-{case['case_id']}-{replicate}",
                                evidence_root=evidence_root,
                                case=case,
                                replicate=replicate,
                                image=args.image,
                                command_timeout_seconds=args.command_timeout_seconds,
                                session_timeout_seconds=args.session_timeout_seconds,
                                host_elf_machine=fingerprint["host_elf_machine"],
                            )
                        )
                    case_result["default_path"] = aggregate_observations(
                        case_result["observations"]
                    )
                else:
                    case_result["default_path"] = {
                        "classification": "infrastructure_failure",
                        "reason": "source_clone_failed",
                        "eligible_as_natural_failure": False,
                    }
                case_result["project_qualification"] = qualify_project(
                    case_result["default_path"], None
                )
            except Exception as exc:
                case_result = {
                    **case,
                    "source": {"succeeded": False},
                    "observations": [],
                    "error": {"kind": type(exc).__name__, "message": str(exc)[:500]},
                    "default_path": {
                        "classification": "infrastructure_failure",
                        "reason": "unhandled_case_exception",
                        "eligible_as_natural_failure": False,
                    },
                    "project_qualification": {
                        "classification": "not_qualified",
                        "eligible_as_natural_failure": False,
                        "reason": "default_path_infrastructure_failure",
                    },
                }
            finally:
                shutil.rmtree(source, ignore_errors=True)
            results.append(case_result)
            _write_json_atomic(evidence_root / "partial-results.json", results)
            print(
                json.dumps(
                    {
                        "case_id": case["case_id"],
                        "classification": case_result["default_path"]["classification"],
                        "completed": len(results),
                        "total": len(cases),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                flush=True,
            )
        qualification = evaluate_canary(results)
        report = {
            "schema_version": "forge-linux-build-closure-canary-report-1.0.0",
            "identity": IDENTITY,
            "status": "completed",
            "started_at": started_at,
            "completed_at": _utc_now(),
            "fixture_path": str(cases_path.relative_to(REPO_ROOT)),
            "fixture_sha256": _sha256_file(cases_path),
            "runtime": fingerprint,
            "budget": {
                "cases": len(cases),
                "replicates_per_case": 2,
                "source_timeout_seconds": args.source_timeout_seconds,
                "command_timeout_seconds": args.command_timeout_seconds,
                "session_timeout_seconds": args.session_timeout_seconds,
                "provider_requests": 0,
                "credential_reads": 0,
                "model_tokens": 0,
            },
            "results": results,
            "qualification": qualification,
        }
        report["report_canonical_sha256"] = _canonical_sha256(report)
        _write_json_atomic(output_path, report)
        return report
    finally:
        for name in managed_containers():
            _remove_container(name)
        shutil.rmtree(work_root, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    canary = subparsers.add_parser("run-canary")
    canary.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    canary.add_argument("--output", type=Path, required=True)
    canary.add_argument("--evidence-root", type=Path, required=True)
    canary.add_argument("--work-root", type=Path, required=True)
    canary.add_argument("--image", default="autocompiler:gcc13")
    canary.add_argument("--source-timeout-seconds", type=int, default=180)
    canary.add_argument("--command-timeout-seconds", type=int, default=180)
    canary.add_argument("--session-timeout-seconds", type=int, default=360)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "run-canary":
        report = run_canary(args)
        print(json.dumps(report["qualification"], ensure_ascii=False, sort_keys=True))
        return 0 if report["qualification"]["passed"] else 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
