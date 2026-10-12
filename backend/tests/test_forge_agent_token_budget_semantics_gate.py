from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_ROOT / "forge_agent_token_budget_semantics_gate.py"


def _load_module() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS_ROOT))
    try:
        spec = importlib.util.spec_from_file_location("forge_agent_token_budget_semantics_gate", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_ROOT))


def test_gate_passes_all_scripted_budget_cases_without_provider() -> None:
    module = _load_module()

    report = module.run_gate(audit_v2=False)

    assert report["status"] == "passed"
    assert report["decision"] == "proceed_to_progress_aware_harness_v3_replication_decision"
    assert report["summary"] == {
        "passed": 9,
        "total": 9,
        "credential_read": False,
        "provider_requests": 0,
        "docker_runs": 0,
        "formal_effect_attempts": 0,
        "v2_evidence_mutated": False,
    }
    cases = {item["case"]: item for item in report["cases"]}
    assert cases["exact_threshold"]["completed_event_recorded_tokens"] == 100
    assert cases["bounded_overshoot"]["node_result_recorded_tokens"] == 110
    assert cases["bounded_overshoot"]["model_calls"] == 2
    assert cases["response_bound_violation"]["primary_failure"] == "budget_contract_violation"
    assert cases["missing_usage"]["requests_usage_incomplete"] == 1
    assert all(item["request_lifecycle_closed"] is True for item in cases.values())


def test_markdown_keeps_engineering_claim_boundary() -> None:
    module = _load_module()
    report = module.run_gate(audit_v2=False)

    markdown = module._render_markdown(report)

    assert "工程修复验证" in markdown
    assert "不改变 v2 的正式停止决定" in markdown
    assert "v3 尚未创建或获得执行授权" in markdown
    assert "0 credential、0 Provider、0 Docker、0 formal effect attempt" in markdown
