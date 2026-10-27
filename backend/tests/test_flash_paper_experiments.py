"""Flash正常和异常响应都必须保留用量并按Flash计费。"""

import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
flash = importlib.import_module("forge_build_flash_paper_experiments")

from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


@pytest.mark.parametrize("actual_model", ["DeepSeek-V4.1-Flash-1017", "unexpected-model"])
def test_flash_usage_and_price_survive_identity_rejection(tmp_path, actual_model):
    candidate = json.loads((ROOT / "benchmarks/manifests/cpp-build-library-strategy-comparison-v2.json").read_text())
    task = candidate["projects"][0]["task"]
    meter = flash.FlashMeter(
        PlanAgentLedger(tmp_path / "agent"),
        registry=flash.base.FixedVerifierRegistry(task),
        obligation={},
        accepted_models=tuple(flash.PROVIDER["accepted_response_models"]),
        deadline=(datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        packet=lambda: {},
    )
    sequence = meter._before_request()
    response = ModelResponse(
        result=[
            AIMessage(
                content="",
                tool_calls=[dict(name="ObservedBuildActions", args={}, id="reply")],
                usage_metadata=dict(input_tokens=1000, output_tokens=200, total_tokens=1200),
                response_metadata=dict(model_name=actual_model),
            )
        ]
    )
    if actual_model == "unexpected-model":
        with pytest.raises(PlanContractError, match="模型标识"):
            meter.capture_response(response, sequence)
    else:
        meter.capture_response(response, sequence)
    meter.capture_response(response, sequence)
    summary = meter.summary()
    assert summary["recorded_tokens"] == 1200
    assert summary["estimated_cost_usd_completed_responses"] == pytest.approx(0.00054)
    assert summary["unknown_usage_requests"] == 0
    assert (tmp_path / "agent/response-1.json").is_file()
