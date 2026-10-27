"""参考比较只验证关键计量停止与原文件边界，不调用Provider。"""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
reference = importlib.import_module("forge_cxx_current_reference")


def test_known_usage_survives_model_identity_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "remaining", lambda: 3600)
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50), model="unexpected", model_dump=lambda **kw: {"usage": {"prompt_tokens": 100, "completion_tokens": 50}})
    meter = reference.SDKMeter(tmp_path / "agent", 1)
    with pytest.raises(reference.StopPaid, match="身份"):
        meter.request(lambda **kw: response, {"messages": []})
    assert meter.summary()["estimated_cost_usd_completed_responses"] == "0.00009"
    assert meter.requests == 1 and meter.stopped


def test_unknown_usage_stops_without_second_request(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "remaining", lambda: 3600)
    meter = reference.SDKMeter(tmp_path / "agent", 1)

    def failed(**kw):
        raise TimeoutError("offline timeout")

    with pytest.raises(TimeoutError):
        meter.request(failed, {"messages": []})
    with pytest.raises(reference.StopPaid):
        meter.request(failed, {"messages": []})
    assert meter.requests == meter.unknown == 1


def test_source_inventory_keeps_dangling_link_identity(tmp_path):
    (tmp_path / "source.c").write_text("original")
    (tmp_path / "link").symlink_to("not-generated-yet")
    rows = reference.source_hashes(tmp_path)
    assert rows["link"] == {"link": "not-generated-yet"}
    assert rows["source.c"]["sha256"] == reference.sha(tmp_path / "source.c")
