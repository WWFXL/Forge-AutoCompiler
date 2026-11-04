"""规划模型对照的Responses工具适配和角色计量；全部使用本机模拟服务。"""

import json
import sys
from collections import Counter
from pathlib import Path

import httpx
from test_simple_build import simple_actions, task

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_planner_model_comparison as comparison  # noqa: E402

from deerflow.compile.plan_agent import PlanAgentLedger  # noqa: E402
from deerflow.compile.simple_build_agents import SimpleBuildMeter  # noqa: E402
from deerflow.compile.simple_build_task import propose_simple  # noqa: E402


def test_fixed_pairs_reverse_planner_order_with_common_experience_and_recovery():
    rows = comparison.schedule()
    assert len(rows) == 16 and set(Counter((r["project"], r["repetition"]) for r in rows).values()) == {2}
    assert all(rows[i]["planner"] != rows[i + 8]["planner"] for i in range(8))
    assert {r["method"] for r in rows} == {"forge_experience"}


def test_responses_function_call_enters_real_graph_and_keeps_usage_and_identity(tmp_path):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=dict(
                id="resp_offline",
                object="response",
                created_at=1,
                status="completed",
                model="gpt-5.6",
                output=[dict(id="fc_offline", call_id="call_offline", type="function_call", name="SimpleBuildActions", arguments=json.dumps(simple_actions().model_dump(mode="json")), status="completed")],
                usage=dict(input_tokens=3, output_tokens=2, total_tokens=5, input_tokens_details=dict(cached_tokens=0), output_tokens_details=dict(reasoning_tokens=0)),
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model = comparison.RichLabPlanner(
            model="gpt-6-astra", api_key="offline-placeholder", base_url="https://offline.invalid/v1", http_client=client, use_responses_api=True, reasoning_effort="low", max_retries=0, max_tokens=32768, store=False
        )
        meter = SimpleBuildMeter(PlanAgentLedger(tmp_path / "agent"), accepted_models=comparison.RICH_MODELS, deadline="2099-01-01T00:00:00+00:00", packet=lambda: {}, pricing_by_model=comparison.PRICES)
        plan, _ = propose_simple(model=model, task=task(), source_root=tmp_path, session_root=tmp_path, meter=meter)
    assert plan.steps[-1].command == "make" and len(requests) == 1
    assert requests[0]["model"] == "gpt-6-astra" and requests[0]["tool_choice"] == "auto"
    assert requests[0]["reasoning"]["effort"] == "low" and requests[0]["max_output_tokens"] == 32768
    assert meter.summary()["recorded_tokens"] == 5 and meter.summary()["estimated_cost_usd"] == 0.000005
    raw = json.loads((tmp_path / "agent/response-1.json").read_text())[0]
    assert raw["response_metadata"]["model_name"] == "gpt-5.6"
