"""续窗不能改变策略；原门禁与正式费用/时间门禁仍须在Provider前闭合。"""

import json
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_full_strategy_comparison as live  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402


def protocols():
    parent = json.loads((live.runtime.REPO_ROOT / live.PARENT_PATH).read_text())
    new = deepcopy(parent)
    new.update(identity=live.IDENTITY, issue=538, deadline_utc=live.DEADLINE, authorization={"root": "new-authorized-root", "sha256": "new-hash"})
    new["components"].update({name: "added-component" for name in live.ADDED_COMPONENTS})
    return new, parent


@pytest.mark.parametrize("field", ["schedule", "provider", "runtime", "projects", "max_estimated_cost_usd"])
def test_authorization_change_cannot_change_science_or_budget(field):
    new, parent = protocols()
    live.check_projection(new, parent)
    new[field] = None
    with pytest.raises(PlanContractError, match="不得改变"):
        live.check_projection(new, parent)


def test_old_execution_component_change_is_rejected():
    new, parent = protocols()
    new["components"]["scripts/forge_build_full_strategy_runtime.py"] = "modified"
    with pytest.raises(PlanContractError, match="执行组件"):
        live.check_projection(new, parent)


def test_partial_or_different_gate_refused_before_reading_any_evidence(tmp_path, monkeypatch):
    inspect = Mock(side_effect=AssertionError("错误门禁不应被消费"))
    monkeypatch.setattr(live, "ORIGINAL_REQUIRE_GATE", inspect)
    with pytest.raises(PlanContractError, match="完整v2门禁"):
        live.require_gate(tmp_path / "protocol.json", tmp_path / "partial")
    inspect.assert_not_called()


def test_qualification_cannot_create_real_identity(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["live", "--qualify"])
    launch = Mock(side_effect=AssertionError("不启动旧执行器"))
    monkeypatch.setattr(live.runtime, "main", launch)
    with pytest.raises(PlanContractError, match="仅执行真实比较"):
        live.main()
    launch.assert_not_called()
