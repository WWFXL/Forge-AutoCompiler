from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_linux_build_closure_qualification_v5 as qualification  # noqa: E402

REPORT_PATH = qualification.REPO_ROOT / "benchmarks/reports/cpp-jev-natural-failure-linux-build-closure-canary-v5.json"


def _observation(
    classification: str,
    *,
    phase: str | None = None,
    category: str | None = None,
    signature: list[tuple[str, str, tuple[int, ...]]] | None = None,
) -> dict[str, object]:
    return {
        "classification": classification,
        "failure_phase": phase,
        "error_category": category,
        "host_artifact_signature": signature or [],
    }


def _docker_ready() -> bool:
    completed = subprocess.run(["docker", "info"], capture_output=True, check=False)
    image = subprocess.run(
        ["docker", "image", "inspect", "autocompiler:gcc13"],
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0 and image.returncode == 0


def test_canary_fixture_is_bound_to_frozen_parent_reports() -> None:
    fixture = qualification._load_json(qualification.DEFAULT_CASES_PATH)

    for relative_path, expected_hash in fixture["parent_reports"].items():
        assert qualification._sha256_file(qualification.REPO_ROOT / relative_path) == expected_hash
    assert len(fixture["cases"]) == 10
    assert {case["audit_group"] for case in fixture["cases"]} == {
        "linux_positive",
        "non_host_negative",
        "no_default_artifact_risk",
    }


def test_versioned_engineering_canary_summary_matches_runner_and_fixture() -> None:
    report = qualification._load_json(REPORT_PATH)

    assert report["evidence_class"] == "nonformal_engineering_canary"
    assert report["runner_sha256"] == qualification._sha256_file(qualification.SCRIPT_PATH)
    assert report["fixture_sha256"] == qualification._sha256_file(qualification.DEFAULT_CASES_PATH)
    assert report["qualification"] == {
        "counts": {
            "stable_failure_candidate": 2,
            "stable_host_userland_closure": 1,
            "stable_no_compiled_artifact": 1,
            "stable_non_host_target": 5,
            "timeout": 1,
        },
        "decision": "proceed_to_formal_build_reference_qualification_design",
        "failed_requirements": [],
        "passed": True,
    }
    assert report["summary"]["qualified_natural_failure_count"] == 0
    assert report["summary"]["managed_containers_after_run"] == 0
    assert report["transient_raw_observation"]["durable_formal_evidence"] is False


def test_real_host_executable_and_archive_use_forge_classifier(tmp_path: Path) -> None:
    source = tmp_path / "main.c"
    object_path = tmp_path / "main.o"
    executable = tmp_path / "app"
    archive = tmp_path / "libapp.a"
    source.write_text("int main(void) { return 0; }\n", encoding="ascii")
    subprocess.run(["gcc", "-c", str(source), "-o", str(object_path)], check=True)
    subprocess.run(["gcc", str(source), "-o", str(executable)], check=True)
    subprocess.run(["ar", "rcs", str(archive), str(object_path)], check=True)

    executable_details = qualification.inspect_artifact(executable, relative_path="app", host_elf_machine=62)
    archive_details = qualification.inspect_artifact(archive, relative_path="libapp.a", host_elf_machine=62)

    assert executable_details is not None
    assert executable_details["artifact_type"] == "executable"
    assert executable_details["elf_machines"] == [62]
    assert executable_details["host_machine_match"] is True
    assert archive_details is not None
    assert archive_details["artifact_type"] == "static_library"
    assert archive_details["elf_machines"] == [62]
    assert archive_details["host_machine_match"] is True


def test_foreign_elf_machine_is_not_host_closure(tmp_path: Path) -> None:
    source = tmp_path / "main.c"
    executable = tmp_path / "app"
    source.write_text("int main(void) { return 0; }\n", encoding="ascii")
    subprocess.run(["gcc", str(source), "-o", str(executable)], check=True)
    payload = bytearray(executable.read_bytes())
    payload[18:20] = (183).to_bytes(2, "little")
    executable.write_bytes(payload)

    details = qualification.inspect_artifact(executable, relative_path="app", host_elf_machine=62)
    result = qualification.classify_observation(
        {
            "commands": [{"phase": "build", "exit_code": 0}],
            "artifacts": [details],
            "target_signals": [],
        },
        host_elf_machine=62,
    )

    assert details is not None
    assert details["elf_machines"] == [183]
    assert details["host_machine_match"] is False
    assert result["classification"] == "non_host_target"


@pytest.mark.parametrize(
    ("payload", "expected_format"),
    [(b"MZ" + bytes(62), "pe"), (b"\xcf\xfa\xed\xfe" + bytes(60), "macho")],
)
def test_non_elf_binary_formats_are_recorded(tmp_path: Path, payload: bytes, expected_format: str) -> None:
    artifact = tmp_path / "artifact"
    artifact.write_bytes(payload)

    details = qualification.inspect_artifact(artifact, relative_path="artifact", host_elf_machine=62)

    assert details is not None
    assert details["artifact_type"] is None
    assert details["binary_format"] == expected_format
    assert details["host_machine_match"] is False


@pytest.mark.parametrize(
    ("command", "signal"),
    [
        ("xcrun clang -framework AppKit app.c", "apple_toolchain"),
        ("arm-vita-eabi-gcc -c app.c", "console_toolchain"),
        ("powerpc-eabi-g++ -c app.cc", "console_toolchain"),
        ("aarch64-linux-android24-clang app.c", "android_target"),
        ("gcc -ffreestanding -nostdlib kernel.c", "freestanding_flags"),
        ("x86_64-w64-mingw32-gcc app.c", "windows_toolchain"),
        ("Variable 'KernelPlatform' is not set - valid platforms are qemu-arm-virt", "kernel_build_contract"),
        ("missing firmware/donut/rootfs/system/lib/libpryon.so", "device_firmware_contract"),
    ],
)
def test_target_signals_come_from_executed_command_text(command: str, signal: str) -> None:
    assert signal in qualification.extract_target_signals(command)


@pytest.mark.parametrize(
    "relative_path",
    [
        "build/CMakeFiles/3.28.3/CompilerIdCXX/a.out",
        "build/CMakeFiles/3.28.3/CMakeDetermineCompilerABI_CXX.bin",
    ],
)
def test_compiler_probe_artifact_is_not_counted(tmp_path: Path, relative_path: str) -> None:
    probe = tmp_path / relative_path
    probe.parent.mkdir(parents=True)
    source = tmp_path / "main.c"
    source.write_text("int main(void) { return 0; }\n", encoding="ascii")
    before = qualification.snapshot_files(tmp_path)
    subprocess.run(["gcc", str(source), "-o", str(probe)], check=True)

    artifacts = qualification.inspect_changed_artifacts(tmp_path, before, host_elf_machine=62)

    assert artifacts == []


def test_observation_classification_prioritizes_dynamic_target_evidence() -> None:
    result = qualification.classify_observation(
        {
            "commands": [{"phase": "build", "exit_code": 0}],
            "artifacts": [],
            "target_signals": ["freestanding_flags"],
        },
        host_elf_machine=62,
    )

    assert result["classification"] == "non_host_target"
    assert result["error_category"] == "freestanding_flags"


def test_host_machine_artifact_without_producer_evidence_is_unresolved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.c"
    executable = tmp_path / "app"
    source.write_text("int main(void) { return 0; }\n", encoding="ascii")
    subprocess.run(["gcc", str(source), "-o", str(executable)], check=True)
    details = qualification.inspect_artifact(executable, relative_path="app", host_elf_machine=62)

    result = qualification.classify_observation(
        {
            "commands": [{"phase": "build", "exit_code": 0}],
            "artifacts": [details],
            "target_signals": [],
        },
        host_elf_machine=62,
    )

    assert result["classification"] == "target_unresolved_success"


def test_producer_evidence_binds_artifact_path_to_host_tool(tmp_path: Path) -> None:
    source = tmp_path / "main.c"
    executable = tmp_path / "app"
    source.write_text("int main(void) { return 0; }\n", encoding="ascii")
    subprocess.run(["gcc", str(source), "-o", str(executable)], check=True)
    details = qualification.inspect_artifact(executable, relative_path="app", host_elf_machine=62)
    assert details is not None

    qualification.attach_producer_evidence([details], "gcc-13 main.c -o app\n")
    result = qualification.classify_observation(
        {
            "commands": [{"phase": "build", "exit_code": 0}],
            "artifacts": [details],
            "target_signals": [],
        },
        host_elf_machine=62,
    )

    assert details["producer_evidence"] is True
    assert result["classification"] == "host_userland_closure"


def test_failure_log_is_normalized_after_logs_are_persisted() -> None:
    result = qualification.classify_observation(
        {
            "commands": [{"phase": "configure", "exit_code": 1}],
            "artifacts": [],
            "target_signals": [],
            "_failure_text": "fatal error: zlib.h: No such file or directory",
        },
        host_elf_machine=62,
    )

    assert result["classification"] == "bounded_failure"
    assert result["error_category"] == "missing_dependency"


def test_two_failures_are_only_a_candidate_until_reference_closes() -> None:
    failures = [
        _observation("bounded_failure", phase="configure", category="missing_dependency"),
        _observation("bounded_failure", phase="configure", category="missing_dependency"),
    ]
    reference_signature = [("build/app", "executable", (62,))]
    references = [
        _observation("host_userland_closure", signature=reference_signature),
        _observation("host_userland_closure", signature=reference_signature),
    ]

    default_path = qualification.aggregate_observations(failures)
    reference_path = qualification.aggregate_observations(references)
    reference_path["reference_contract"] = {
        "valid": True,
        "default_build_bound": True,
    }
    reference_path["source_identity_clean"] = True

    assert default_path["classification"] == "stable_failure_candidate"
    assert qualification.qualify_project(default_path, None)["eligible_as_natural_failure"] is False
    assert qualification.qualify_project(default_path, reference_path) == {
        "classification": "qualified_natural_failure",
        "eligible_as_natural_failure": True,
        "reason": "stable_default_failure_and_reference_host_closure",
    }


def test_reference_recipe_must_build_the_default_target() -> None:
    valid = qualification.validate_reference_recipe(
        {
            "commands": [
                {
                    "phase": "configure",
                    "command": "cmake -S . -B build -DFEATURE=ON",
                },
                {
                    "phase": "build",
                    "command": "cmake --build build --verbose --parallel 4",
                },
            ],
            "artifact_paths": ["build/app"],
        },
        build_system="cmake",
    )
    optional_target = qualification.validate_reference_recipe(
        {
            "commands": [
                {"phase": "configure", "command": "cmake -S . -B build"},
                {
                    "phase": "build",
                    "command": "cmake --build build --target linux-port --parallel 4",
                },
            ],
            "artifact_paths": ["build/linux-port"],
        },
        build_system="cmake",
    )

    assert valid["valid"] is True
    assert valid["default_build_bound"] is True
    assert optional_target["valid"] is False
    assert "default_build_command_not_bound" in optional_target["errors"]


def test_host_reference_without_contract_cannot_qualify_failure() -> None:
    default_path = {"classification": "stable_failure_candidate"}
    reference_path = {
        "classification": "stable_host_userland_closure",
        "source_identity_clean": True,
    }

    result = qualification.qualify_project(default_path, reference_path)

    assert result["eligible_as_natural_failure"] is False
    assert result["reason"] == "reference_contract_or_source_identity_invalid"


def test_reference_host_artifact_signatures_must_agree() -> None:
    observations = [
        _observation("host_userland_closure", signature=[("build/app", "executable", (62,))]),
        _observation("host_userland_closure", signature=[("build/libapp.a", "static_library", (62,))]),
    ]

    result = qualification.aggregate_observations(observations)

    assert result["classification"] == "inconsistent_observation"


def test_default_build_commands_do_not_select_an_optional_target(tmp_path: Path) -> None:
    cmake = qualification.default_commands(tmp_path, "cmake")
    make = qualification.default_commands(tmp_path, "make")

    assert cmake[-1]["command"] == "cmake --build build --verbose --parallel 4"
    assert make[-1]["command"] == "make --trace -j4 V=1 VERBOSE=1"


@pytest.mark.skipif(not _docker_ready(), reason="需要本机 Forge Docker runtime 和 autocompiler:gcc13")
def test_make_observation_closes_real_host_artifact_and_cleans_container(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.c").write_text("int main(void) { return 0; }\n", encoding="ascii")
    (source / "Makefile").write_text("app: main.c\n\t$(CC) main.c -o app\n", encoding="ascii")
    case = {"case_id": "fixture-host-make", "build_system": "make"}
    observations = []
    for replicate in (1, 2):
        observations.append(
            qualification.run_observation(
                source=source,
                workspace=tmp_path / f"workspace-{replicate}",
                evidence_root=tmp_path / "evidence",
                case=case,
                replicate=replicate,
                image="autocompiler:gcc13",
                command_timeout_seconds=30,
                session_timeout_seconds=60,
                host_elf_machine=62,
            )
        )

    aggregate = qualification.aggregate_observations(observations)

    assert aggregate["classification"] == "stable_host_userland_closure"
    assert not qualification.managed_containers()
    stored = json.loads((tmp_path / "evidence/cases/fixture-host-make/replicate-1/observation.json").read_text())
    assert stored["classification"] == "host_userland_closure"
