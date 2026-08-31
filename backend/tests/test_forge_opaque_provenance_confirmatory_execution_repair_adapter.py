from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
ADAPTER_PATH = SCRIPT_ROOT / "forge_opaque_provenance_confirmatory_execution_repair_adapter.py"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-opaque-provenance-confirmatory-execution-authorized.json"
INVENTORY_PATH = REPO_ROOT / "benchmarks/fixtures/opaque-provenance-confirmatory-v1-evidence-inventory.json"


def _load_adapter():
    if str(SCRIPT_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPT_ROOT))
    spec = importlib.util.spec_from_file_location("forge_confirmatory_execution_repair_adapter_test", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load_adapter()


def test_repair_contract_covers_all_pairs_without_provider_work() -> None:
    manifest = adapter.v1.protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    result = adapter.validate_contract(manifest, repo_root=REPO_ROOT)

    assert result == {
        "status": "passed",
        "pair_count": 12,
        "case_count": 6,
        "build_systems": ["cmake", "make"],
        "reference_case_ids": {
            "pupnp": "pupnp",
            "ada-url": "ada-url",
            "args": "args",
            "gpac": "gpac",
            "fio": "fio",
            "sql-parser-shared": "sql-parser",
        },
        "provider_calls": 0,
        "credential_read": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


@pytest.mark.parametrize("case_id", ["args", "gpac"])
def test_repaired_manifest_reaches_both_pair_runtime_families(
    case_id: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = adapter.v1.protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    pair = next(item for item in manifest["schedule"]["pairs"] if item["case_id"] == case_id)
    captured: dict[str, Any] = {}

    class PairRuntime:
        make_lifecycle = SimpleNamespace(provenance=None)

        @staticmethod
        def _run_pair(pair_manifest: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
            captured["pair_manifest"] = pair_manifest
            return {
                "complete_pair": True,
                "cleanup_succeeded": True,
                "arm_order": pair["arm_order"],
                "arms": [
                    {
                        "arm": arm,
                        "infrastructure": {"status": "valid"},
                        "model_behavior": {"status": "completed"},
                        "p2": {"status": "unproven"},
                        "recorded_tokens": 0,
                    }
                    for arm in pair["arm_order"]
                ],
            }

    @contextmanager
    def pair_bindings(*_args: Any, **_kwargs: Any) -> Iterator[PairRuntime]:
        yield PairRuntime()

    monkeypatch.setattr(adapter.v1, "_pair_bindings", pair_bindings)
    with asyncio.Runner() as async_runner:
        outcome = adapter.execute_real_pair(
            manifest,
            pair,
            tmp_path / pair["pair_id"],
            async_runner,
            {"recorded_tokens": 17},
            {"branch": "main", "revision": "a" * 40, "origin_main": "a" * 40},
        )

    case = next(item for item in manifest["cases"] if item["case_id"] == case_id)
    assert captured["pair_manifest"]["case"]["reference_case_id"] == case["source_case_id"]
    if case["build_system"] == "make":
        assert PairRuntime.make_lifecycle.provenance is adapter.lifecycle.make_reference.provenance
    assert outcome["pair_id"] == pair["pair_id"]


def test_repair_fails_closed_without_source_case_identity() -> None:
    manifest = adapter.v1.protocol.load_manifest(MANIFEST_PATH, REPO_ROOT)
    candidate = copy.deepcopy(manifest)
    candidate["cases"][3].pop("source_case_id")
    pair = next(item for item in candidate["schedule"]["pairs"] if item["case_id"] == "gpac")

    with pytest.raises(adapter.ConfirmatoryRepairError, match="source case identity"):
        adapter._pair_manifest(candidate, pair, Path("/tmp/gpac"))


def test_pair_failure_cleans_only_sessions_created_by_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = SimpleNamespace(session_id="created-session")
    cleanup_calls: list[str] = []

    class Manager:
        @staticmethod
        def create_session(*_args: Any, **_kwargs: Any) -> Any:
            return created

    original_create_session = Manager.create_session

    class Runtime:
        @staticmethod
        def stop_and_remove_container(session: Any) -> Any:
            cleanup_calls.append(session.session_id)
            return SimpleNamespace(succeeded=True)

    monkeypatch.setattr(
        adapter,
        "_compile_services",
        lambda: SimpleNamespace(manager=Manager, runtime=Runtime),
    )

    with pytest.raises(RuntimeError, match="capture evidence failed"):
        with adapter._cleanup_created_sessions_on_failure():
            assert Manager.create_session() is created
            raise RuntimeError("capture evidence failed")

    assert cleanup_calls == ["created-session"]
    assert Manager.create_session is original_create_session


def test_v1_evidence_inventory_and_import_semantics_are_frozen() -> None:
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    entries = inventory["entries"]
    payload = "".join(f"{item['path']}\t{item['bytes']}\t{item['sha256']}\n" for item in sorted(entries, key=lambda item: item["path"])).encode()

    assert inventory["file_count"] == len(entries) == 28
    assert inventory["total_bytes"] == sum(item["bytes"] for item in entries) == 332_783
    assert hashlib.sha256(payload).hexdigest() == inventory["entries_sha256"]
    assert inventory["entries_sha256"] == "dc7e53020af27929ea334376628c37f02236ae5510166c07109a1ddde7f5f431"
    outcome_hashes = {item["path"]: item["sha256"] for item in entries if item["path"].endswith("pair-outcome.json")}
    assert outcome_hashes == {
        "pairs/ada-url-rep-01/reports/pair-outcome.json": "4a22a883f62e716f3b70d5daf04ec7a598277487f0bcb95f1e3d9dca1af4e17a",
        "pairs/args-rep-01/reports/pair-outcome.json": "18e67644cc3958514ed9fd3cc1bafdf93c55228ffd053a87c9554d21ba830ca9",
        "pairs/pupnp-rep-01/reports/pair-outcome.json": "c6c647db13b0e0c5e4336a14d54ec6a2287581507466f2b88a2ff30ebb1b487f",
    }
