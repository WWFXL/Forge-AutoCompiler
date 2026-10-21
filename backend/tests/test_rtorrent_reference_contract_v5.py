"""完整测试在重放配方保留，产物短smoke只消费独立CLI成功记录。"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_reference_v5 import delivery_cli_evidence  # noqa: E402


def test_successful_cli_binding_does_not_consume_full_test_command(tmp_path):
    log = tmp_path / "cli.log"
    log.write_text("Rakshasa's BitTorrent client version 0.16.25.\nUsage: rtorrent\n")
    record = SimpleNamespace(command_id="cli", command="LD_LIBRARY_PATH=/artifacts /artifacts/rtorrent -h", workdir="/workspace/repo", exit_code=0, log_path=str(log))
    evidence = delivery_cli_evidence(record)
    assert evidence.command_id == "cli" and evidence.command == record.command and evidence.output == log.read_text()


@pytest.mark.parametrize("output,exit_code", [("FORGE_RTORRENT_FULL_TESTS={}\n", 0), ("Rakshasa's BitTorrent client version 0.16.25.\nUsage: rtorrent\n", 1)])
def test_missing_cli_or_failure_cannot_supply_trusted_artifact_smoke(tmp_path, output, exit_code):
    log = tmp_path / "bad.log"
    log.write_text(output)
    record = SimpleNamespace(command_id="wrong", command="tests", workdir="/workspace/repo", exit_code=exit_code, log_path=str(log))
    with pytest.raises(ValueError):
        delivery_cli_evidence(record)


def test_v5_keeps_complete_tests_before_additional_cli_in_replay():
    root = Path(__file__).resolve().parents[2]
    spec = json.loads((root / "benchmarks/manifests/cpp-build-rtorrent-reference-v5.json").read_text())
    smokes = [s for s in spec["plan"]["steps"] if s["role"] == "smoke"]
    assert [s["step_id"] for s in smokes] == ["full-author-tests", "delivery-cli"]
    assert spec["plan"]["steps"][-2] == json.loads((root / "benchmarks/manifests/cpp-build-rtorrent-reference-v4.json").read_text())["plan"]["steps"][-1]
    assert smokes[-1]["command"] == "LD_LIBRARY_PATH=/artifacts /artifacts/rtorrent -h"
    assert sum(sum(programs.values()) for programs in spec["original_test_counts"].values()) == 323
