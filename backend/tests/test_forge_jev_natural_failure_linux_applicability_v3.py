from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_natural_failure_linux_applicability_v3 as protocol  # noqa: E402


def _candidate() -> dict[str, object]:
    return {
        "project_family": "example/project",
        "full_name": "example/project",
        "repository_url": "https://github.com/example/project",
        "default_branch": "main",
        "search_query_ids": ["cpp"],
        "search_metadata": {},
    }


def _blob(text: str) -> dict[str, str]:
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


def test_protocol_is_valid_and_candidate_only() -> None:
    result = protocol.validate_protocol()

    assert result["valid"] is True
    assert result["authorization"] == "candidate_only"
    assert result["history_project_family_count"] == 205


def test_history_exclusion_includes_entire_v2_observed_pool() -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)

    families = protocol.exclusion_project_families(manifest)

    assert "felixkratz/sketchybar" in families
    assert "sogou/workflow" in families
    assert protocol._canonical_sha256(families) == manifest["history_exclusion"]["canonical_sha256"]


def test_frozen_regression_fixture_matches_expected_classifications() -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    fixture = protocol._load_json(protocol._path_from_manifest(manifest["regression_fixture"]["path"]))

    observed = {}
    for case in fixture["cases"]:
        decision = protocol.assess_linux_applicability(
            system=case["system"],
            entry_files=[{"path": case["entry_path"], "text": case["entry_text"]}],
            document_files=case.get("documents", []),
        )
        observed[case["id"]] = decision["classification"]
        assert set(case["expected_entry_signals"]).issubset(decision["entry_signals"])

    assert observed == {
        "sketchybar-macos-only": "platform_ineligible",
        "windows-msbuild-only": "platform_ineligible",
        "bare-metal-firmware-only": "platform_ineligible",
        "make-darwin-and-linux": "linux_applicable",
        "cmake-apple-option-and-linux-path": "linux_applicable",
        "portable-cmake-docs-mention-platforms": "linux_applicable",
        "documented-macos-only": "platform_ineligible",
    }


def test_generic_link_variable_is_not_msvc_signal() -> None:
    text = "CC ?= cc\nLINK = $(CC)\nall: app\n\t$(LINK) main.o -o app\n"

    decision = protocol.assess_linux_applicability(
        system="make",
        entry_files=[{"path": "Makefile", "text": text}],
        document_files=[],
    )

    assert decision["classification"] == "linux_applicable"
    assert "windows_msvc_compiler" not in decision["entry_signals"]


def test_platform_word_in_portable_document_does_not_exclude() -> None:
    decision = protocol.assess_linux_applicability(
        system="autotools",
        entry_files=[{"path": "configure.ac", "text": "AC_INIT([example], [1.0])\nAC_PROG_CC\n"}],
        document_files=[{"path": "README.md", "text": "Builds on Linux, macOS and Windows."}],
    )

    assert decision["classification"] == "linux_applicable"
    assert decision["document_exclusion_signals"] == []


def test_unreadable_entry_is_ambiguous() -> None:
    decision = protocol.assess_linux_applicability(
        system="make",
        entry_files=[{"path": "Makefile", "error": "entry_blob_too_large"}],
        document_files=[],
    )

    assert decision["classification"] == "ambiguous"
    assert decision["reason"] == "entrypoint_unreadable"


def test_unreadable_document_is_ambiguous_without_explicit_linux_path() -> None:
    decision = protocol.assess_linux_applicability(
        system="cmake",
        entry_files=[{"path": "CMakeLists.txt", "text": "project(example C)\nadd_library(example example.c)\n"}],
        document_files=[{"path": "README.md", "error": "document_blob_too_large"}],
    )

    assert decision["classification"] == "ambiguous"
    assert decision["reason"] == "document_unreadable"


def test_catalog_repository_excludes_sketchybar_style_makefile(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    makefile = "LIBS = -framework AppKit -framework Carbon\nx86: CFLAGS += -target x86_64-apple-macos10.13\narm: CFLAGS += -target arm64-apple-macos11\nuniversal:\n\tlipo -create -output app app_x86 app_arm\n"

    def api(endpoint: str, timeout: int) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if "/commits/" in endpoint:
            return {"sha": "a" * 40, "commit": {"committer": {"date": "2026-10-12T00:00:00Z"}}}, None
        if "/git/trees/" in endpoint:
            return {
                "sha": "b" * 40,
                "truncated": False,
                "tree": [{"path": "Makefile", "type": "blob", "sha": "c" * 40, "size": len(makefile)}],
            }, None
        return _blob(makefile), None

    monkeypatch.setattr(protocol, "_api_json", api)

    result = protocol.catalog_repository(_candidate(), manifest)

    assert result["classification"] == "source_ineligible"
    assert result["reason"] == "platform_or_endpoint_ineligible"
    applicability = result["system_scans"]["make"]["applicability"]
    assert applicability["classification"] == "platform_ineligible"
    assert applicability["strong_exclusion_signals"] == ["apple_target_triple", "macho_universal"]


def test_catalog_repository_keeps_multiplatform_linux_path(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    makefile = "UNAME_S := $(shell uname -s)\nifeq ($(UNAME_S),Darwin)\nLDFLAGS += -framework AppKit\nelse ifeq ($(UNAME_S),Linux)\nLDFLAGS += -ldl\nendif\nall: app\n\t$(CC) main.c -o app $(LDFLAGS)\n"
    readme = "Portable host utility for Linux and macOS."

    def api(endpoint: str, timeout: int) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if "/commits/" in endpoint:
            return {"sha": "a" * 40, "commit": {"committer": {"date": "2026-10-12T00:00:00Z"}}}, None
        if "/git/trees/" in endpoint:
            return {
                "sha": "b" * 40,
                "truncated": False,
                "tree": [
                    {"path": "Makefile", "type": "blob", "sha": "c" * 40, "size": len(makefile)},
                    {"path": "README.md", "type": "blob", "sha": "d" * 40, "size": len(readme)},
                ],
            }, None
        if endpoint.endswith("/" + "c" * 40):
            return _blob(makefile), None
        return _blob(readme), None

    monkeypatch.setattr(protocol, "_api_json", api)

    result = protocol.catalog_repository(_candidate(), manifest)

    assert result["classification"] == "source_eligible"
    assert result["eligible_systems"] == ["make"]
    assert result["system_scans"]["make"]["applicability"]["reason"] == "explicit_linux_entry_path"
    assert result["document_scans"][0]["content_sha256"] == protocol._sha256_bytes(readme.encode())


def test_document_api_failure_is_project_level_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)

    def api(endpoint: str, timeout: int) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if "/commits/" in endpoint:
            return {"sha": "a" * 40, "commit": {"committer": {"date": "2026-10-12T00:00:00Z"}}}, None
        if "/git/trees/" in endpoint:
            return {
                "sha": "b" * 40,
                "truncated": False,
                "tree": [
                    {"path": "CMakeLists.txt", "type": "blob", "sha": "c" * 40, "size": 20},
                    {"path": "README.md", "type": "blob", "sha": "d" * 40, "size": 20},
                ],
            }, None
        return None, {"kind": "timeout", "endpoint": endpoint}

    monkeypatch.setattr(protocol, "_api_json", api)

    result = protocol.catalog_repository(_candidate(), manifest)

    assert result["classification"] == "infrastructure_failure"
    assert result["reason"] == "document_blob_lookup_failed"


def test_api_timeout_is_project_level_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd=["gh", "api"], timeout=1, output="partial", stderr="late")

    monkeypatch.setattr(protocol, "_run", timeout)

    value, error = protocol._api_json("repos/example/project/commits/main", 1)

    assert value is None
    assert error is not None
    assert error["kind"] == "timeout"


def test_repository_exception_does_not_stop_following_candidate() -> None:
    candidates = [
        {"project_family": "example/first", "full_name": "example/first", "repository_url": "https://github.com/example/first"},
        {"project_family": "example/second", "full_name": "example/second", "repository_url": "https://github.com/example/second"},
    ]
    observed: list[str] = []

    def catalog_one(candidate: dict[str, object]) -> dict[str, object]:
        if candidate["project_family"] == "example/first":
            raise TimeoutError("injected")
        return {**candidate, "classification": "source_ineligible", "reason": "fixture"}

    results = protocol.catalog_repositories(candidates, catalog_one, lambda row: observed.append(str(row["project_family"])))

    assert [row["classification"] for row in results] == ["infrastructure_failure", "source_ineligible"]
    assert observed == ["example/first", "example/second"]


def test_allocator_creates_unique_unassigned_reserve_pool() -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    results: list[dict[str, object]] = []
    for system in protocol.SYSTEMS:
        for index in range(12):
            family = f"example/{system}-{index}"
            results.append(
                {
                    "project_family": family,
                    "full_name": family,
                    "repository_url": f"https://github.com/{family}",
                    "commit_sha": f"{protocol.SYSTEMS.index(system) + 1:x}" * 40,
                    "commit_committed_at": "2026-10-12T00:00:00Z",
                    "classification": "source_eligible",
                    "eligible_systems": [system],
                }
            )

    allocation = protocol.allocate_projects(results, manifest)

    assert allocation["passed"] is True
    assert allocation["decision"] == "proceed_to_natural_failure_build_reference_qualification_v3"
    assert allocation["counts"] == {"cmake": 12, "make": 12, "autotools": 12}
    assert len({row["project_family"] for row in allocation["projects"]}) == 36
    assert all("role" not in row for row in allocation["projects"])


def test_allocator_fails_without_make_reserve() -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    results = [
        {
            "project_family": f"example/cmake-{index}",
            "full_name": f"example/cmake-{index}",
            "repository_url": f"https://github.com/example/cmake-{index}",
            "commit_sha": "a" * 40,
            "classification": "source_eligible",
            "eligible_systems": ["cmake"],
        }
        for index in range(12)
    ]

    allocation = protocol.allocate_projects(results, manifest)

    assert allocation["passed"] is False
    assert allocation["decision"] == "stop_natural_failure_linux_applicability_v3"
    assert "make:0<12" in allocation["failed_requirements"]


def test_regression_fixture_is_valid_json() -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    path = protocol._path_from_manifest(manifest["regression_fixture"]["path"])

    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "forge-jev-linux-applicability-regressions-1.0.0"
