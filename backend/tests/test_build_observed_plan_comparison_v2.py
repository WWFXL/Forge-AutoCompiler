"""充值后继续的身份、总预算与旧证据保护；全程零Provider。"""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_observed_plan_comparison_v2 as compare


def candidate():
    return json.loads((compare.REPO_ROOT / "benchmarks/manifests/cpp-build-observed-plan-comparison-v2.json").read_text())


def authorization():
    return {
        "experiment_identity": compare.IDENTITY,
        "candidate_sha256": "new-sha",
        "user_authorized": True,
        "authorized_at_utc": "2026-10-20T14:36:26Z",
        "deadline_utc": compare.DEADLINE,
        "max_new_provider_cost_usd": "19.60",
        "provider_service_recheck_authorized": True,
        "prior_reserved_cost_usd": "0.40",
        "aggregate_maximum_usd": "20.00",
        "user_continue_verified_utc": "2026-10-20T14:36:26Z",
    }


def test_explicitly_reuses_qualified_dispatch_without_mutating_old_identity():
    assert compare.execute is compare.previous.execute
    assert compare.schedule is compare.previous.schedule
    assert compare.previous.IDENTITY == "cpp-build-observed-plan-comparison-v1"
    assert compare.IDENTITY != compare.previous.IDENTITY


@pytest.mark.parametrize(
    "field,value",
    [
        ("experiment_identity", "cpp-build-observed-plan-comparison-v1"),
        ("max_new_provider_cost_usd", "20"),
        ("deadline_utc", "2026-10-20T18:36:26Z"),
        ("prior_reserved_cost_usd", "0"),
        ("aggregate_maximum_usd", "20.40"),
        ("user_continue_verified_utc", None),
    ],
)
def test_cannot_restart_old_identity_reset_budget_or_extend_deadline(monkeypatch, field, value):
    monkeypatch.setattr(compare.previous, "validate_authorization", Mock())
    with pytest.raises(compare.PlanContractError):
        compare.validate_authorization("new-sha", {**authorization(), field: value})


def test_valid_authorization_delegates_all_original_time_hash_and_service_checks(monkeypatch):
    validate = Mock()
    monkeypatch.setattr(compare.previous, "validate_authorization", validate)
    compare.validate_authorization("new-sha", authorization())
    validate.assert_called_once_with("new-sha", {**authorization(), "experiment_identity": compare.previous.IDENTITY})


def test_candidate_preserves_method_resource_test_and_schedule_contract(monkeypatch):
    # 主机外CI也能验证字段不变；完整历史库存由实际CLI preflight核验。
    monkeypatch.setattr(compare.previous, "validate", Mock())
    monkeypatch.setattr(compare, "audit", Mock(return_value={"inventory_canonical_sha256": compare.PARENT_INVENTORY}))
    original_read = Path.read_text
    parent_result = {
        "identity": compare.previous.IDENTITY,
        "arms": [{"agent_usage": {"unknown_usage_requests": 1}}],
        "not_observed": [{}] * 11,
        "lifecycle_complete": True,
        "stop_reason": "cleanup_or_unknown_usage",
        "known_estimated_cost_usd": "0",
        "unknown_usage_reservation_usd": "0.40",
    }

    c = candidate()
    parent_result_path = Path(c["restart"]["parent_evidence_root"]) / "result.json"

    def safe_read(path, *args, **kwargs):
        return json.dumps(parent_result) if path == parent_result_path else original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", safe_read)
    compare.validate(c)
    for field, value in [("identity", compare.previous.IDENTITY), ("schedule", c["schedule"][1:]), ("runtime", {}), ("provider", {}), ("projects", [])]:
        altered = copy.deepcopy(c)
        altered[field] = value
        with pytest.raises(compare.PlanContractError):
            compare.validate(altered)
    parent_result["unknown_usage_reservation_usd"] = "0"
    with pytest.raises(compare.PlanContractError):
        compare.validate(c)


def test_cli_missing_authorization_cannot_read_credentials_or_create_raw(tmp_path, monkeypatch):
    path = tmp_path / "candidate.json"
    path.write_text("{}")
    monkeypatch.setattr(compare, "validate", Mock())
    monkeypatch.setattr(compare, "require_gates", Mock())
    monkeypatch.setattr(compare, "os", SimpleNamespace(environ=None))
    monkeypatch.setattr(sys, "argv", ["comparison", "--candidate", str(path), "--output-root", str(tmp_path / "raw")])
    with pytest.raises(compare.PlanContractError, match="新的明确授权"):
        compare.main()
    assert not (tmp_path / "raw").exists()
