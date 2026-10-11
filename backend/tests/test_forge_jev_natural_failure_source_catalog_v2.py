from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_jev_natural_failure_source_catalog_v2 as protocol  # noqa: E402


def test_protocol_is_valid_and_candidate_only() -> None:
    result = protocol.validate_protocol()

    assert result["valid"] is True
    assert result["authorization"] == "candidate_only"
    assert result["history_project_family_count"] == 96


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        ({"CMakeLists.txt"}, ["cmake"]),
        ({"GNUmakefile"}, ["make"]),
        ({"configure.ac"}, ["autotools"]),
        ({"CMakeLists.txt", "Makefile", "configure.in"}, ["cmake", "make", "autotools"]),
        ({"src/CMakeLists.txt"}, []),
    ],
)
def test_supported_systems_require_root_markers(paths: set[str], expected: list[str]) -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)

    assert protocol.supported_systems(paths, manifest["source_contract"]["root_markers"]) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("FetchContent_Declare(foo)", ["cmake_fetch_content"]),
        ("ExternalProject_Add(foo)", ["cmake_external_project"]),
        ("file(DOWNLOAD https://example.invalid/a b)", ["cmake_file_download"]),
        ("git clone https://example.invalid/a", ["git_clone"]),
        ("curl -L https://example.invalid/a", ["curl_command"]),
        ("wget https://example.invalid/a", ["wget_command"]),
        ("add_library(example example.c)", []),
    ],
)
def test_network_signals_are_bounded(text: str, expected: list[str]) -> None:
    assert protocol.find_network_signals(text) == expected


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


def test_catalog_repository_accepts_clean_root_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    content = base64.b64encode(b"cmake_minimum_required(VERSION 3.20)\nadd_library(example example.c)\n").decode()

    def api(endpoint: str, timeout: int) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if "/commits/" in endpoint:
            return {
                "sha": "a" * 40,
                "commit": {"committer": {"date": "2026-10-10T00:00:00Z"}},
            }, None
        if "/git/trees/" in endpoint:
            return {
                "sha": "b" * 40,
                "truncated": False,
                "tree": [{"path": "CMakeLists.txt", "type": "blob", "sha": "c" * 40, "size": 72}],
            }, None
        return {"encoding": "base64", "content": content}, None

    monkeypatch.setattr(protocol, "_api_json", api)
    candidate = {
        "project_family": "example/project",
        "full_name": "example/project",
        "repository_url": "https://github.com/example/project",
        "default_branch": "main",
        "search_query_ids": ["cpp"],
        "search_metadata": {},
    }

    result = protocol.catalog_repository(candidate, manifest)

    assert result["classification"] == "source_eligible"
    assert result["eligible_systems"] == ["cmake"]
    assert result["system_scans"]["cmake"]["network_signals"] == []


def test_catalog_repository_excludes_submodule_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)

    def api(endpoint: str, timeout: int) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if "/commits/" in endpoint:
            return {"sha": "a" * 40, "commit": {"committer": {"date": "2026-10-10T00:00:00Z"}}}, None
        return {
            "sha": "b" * 40,
            "truncated": False,
            "tree": [
                {"path": "CMakeLists.txt", "type": "blob", "sha": "c" * 40, "size": 10},
                {"path": ".gitmodules", "type": "blob", "sha": "d" * 40, "size": 10},
            ],
        }, None

    monkeypatch.setattr(protocol, "_api_json", api)
    candidate = {
        "project_family": "example/project",
        "full_name": "example/project",
        "repository_url": "https://github.com/example/project",
        "default_branch": "main",
        "search_query_ids": ["cpp"],
        "search_metadata": {},
    }

    result = protocol.catalog_repository(candidate, manifest)

    assert result["classification"] == "source_ineligible"
    assert result["reason"] == "submodule_manifest_present"


def test_allocator_requires_unique_projects_for_every_system() -> None:
    manifest = protocol._load_json(protocol.MANIFEST_PATH)
    results: list[dict[str, object]] = []
    for system in protocol.SYSTEMS:
        for index in range(8):
            family = f"example/{system}-{index}"
            results.append(
                {
                    "project_family": family,
                    "full_name": family,
                    "repository_url": f"https://github.com/{family}",
                    "commit_sha": f"{protocol.SYSTEMS.index(system) + 1:x}" * 40,
                    "commit_committed_at": "2026-10-10T00:00:00Z",
                    "classification": "source_eligible",
                    "eligible_systems": [system],
                }
            )

    allocation = protocol.allocate_projects(results, manifest)

    assert allocation["passed"] is True
    assert allocation["counts"] == {"cmake": 8, "make": 8, "autotools": 8}
    assert len({row["project_family"] for row in allocation["projects"]}) == 24
    assert [row["role"] for row in allocation["projects"] if row["selected_build_system"] == "cmake"] == [
        "design",
        "design",
        "calibration",
        "calibration",
        "evaluation",
        "evaluation",
        "evaluation",
        "evaluation",
    ]


def test_allocator_fails_when_one_system_has_insufficient_projects() -> None:
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
        for index in range(8)
    ]

    allocation = protocol.allocate_projects(results, manifest)

    assert allocation["passed"] is False
    assert allocation["decision"] == "stop_natural_failure_source_catalog_v2"
    assert "autotools:0<8" in allocation["failed_requirements"]
