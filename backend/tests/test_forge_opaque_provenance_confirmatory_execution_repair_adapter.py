from __future__ import annotations

import asyncio
import copy
import importlib.util
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
