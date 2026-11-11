"""验证共同修复后比较保留原指导、独立参考及相同执行接口，零Provider。"""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_recovery_harness_repaired_comparison as comparison  # noqa: E402

from deerflow.compile.plan_workflow import PlanContractError, _digest  # noqa: E402
from deerflow.compile.recovery_harness import RecoveryHarness  # noqa: E402
from deerflow.compile.simple_build_task import SIMPLE_PROMPT  # noqa: E402


def test_rebinds_only_common_prompt_and_keeps_old_guard():
    original = comparison.base.shared.load(comparison.previous.REVIEWED / "candidate.json")
    old = RecoveryHarness.model_validate(original)
    with pytest.raises(PlanContractError, match="底座已变化"):
        old.prompt(SIMPLE_PROMPT)
    rebound = comparison.harnesses()
    assert rebound["H0"].prompt(SIMPLE_PROMPT) == SIMPLE_PROMPT
    actual = rebound["R2_system_context"].model_dump(mode="json")
    assert actual == original | dict(base_prompt_sha256=_digest(SIMPLE_PROMPT))
    assert rebound["R2_system_context"].fingerprint() != old.fingerprint()
    assert actual["recovery_guidance"] in rebound["R2_system_context"].prompt(SIMPLE_PROMPT)


def test_same_18_tasks_only_masscan_native_reference_changes():
    before = comparison.base.shared.load(comparison.previous.MANIFEST)["projects"]
    after = comparison.projects()
    assert len(before) == len(after) == 18
    for old, new in zip(before, after, strict=True):
        for key in old.keys() - {"exposure", "reference"}:
            assert old[key] == new[key]
        if new["name"] != "masscan":
            assert old["reference"] == new["reference"]
        else:
            assert new["reference"]["executable_smokes"][0]["accepted_exit_codes"] == [1]
            assert old["reference"]["components"] == new["reference"]["components"]
            assert old["reference"]["executable_smokes"][0]["step"]["command"] == new["reference"]["executable_smokes"][0]["step"]["command"]


def test_new_manifest_and_runtime_guard_reject_changes(monkeypatch):
    value = comparison.base.shared.load(comparison.MANIFEST)
    # CI没有本机原始归档；仅用固定摘要模拟该外部输入，仓库组件仍实际核验。
    source_hashes = {Path(p["source_archive"]): p["task"]["source_archive_sha256"] for p in value["projects"]}
    real_digest = comparison.digest
    monkeypatch.setattr(comparison, "digest", lambda path: source_hashes[path] if path in source_hashes else real_digest(path))
    comparison.validate(value)
    bad = copy.deepcopy(value)
    bad["recovery_harnesses"]["R2_system_context"]["recovery_guidance"] += "变更"
    with pytest.raises(PlanContractError, match="恢复指导"):
        comparison.validate(bad)
    bad = copy.deepcopy(value)
    bad["components"]["backend/packages/harness/deerflow/compile/simple_build_task.py"] = "0" * 64
    with pytest.raises(PlanContractError, match="固定组件"):
        comparison.validate(bad)


def test_callback_uses_both_current_harnesses_and_correct_reference(tmp_path, monkeypatch):
    value = comparison.base.shared.load(comparison.MANIFEST)
    item = next(p for p in value["projects"] if p["name"] == "masscan")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "zero-provider-test")
    monkeypatch.setattr(comparison.base, "PlanThinkingDeepSeek", lambda **kw: None)
    captured = []
    monkeypatch.setattr(comparison.base.shared, "run_simple_system", lambda **kw: captured.append(kw) or {})
    auth = dict(credentials_env_file=str(tmp_path / "not-present.env"))
    _, execute = comparison.base.paid_callbacks(value, auth)
    for method in comparison.METHODS:
        execute(slot=dict(method=method), item=item, folder=tmp_path / method, available="0.40", deadline="2099-01-01T00:00:00+00:00", initial_plan={"same": True})
        call = captured[-1]
        assert call["recovery_harness"] == comparison.harnesses()[method]
        assert call["reference"].executable_smokes[0].accepted_exit_codes == (1,)
        assert call["initial_plan"] == {"same": True}
        assert call["state_router"].method == "rule"
        assert call["validation_scope"] == "main_build"


def test_old_authorization_does_not_admit_new_identity():
    auth = dict(identity=comparison.previous.IDENTITY, user_reply="授权", candidate_sha256="old")
    with pytest.raises(PlanContractError, match="确切身份"):
        comparison.base.shared.validate_authorization(auth, "new", identity=comparison.IDENTITY, maximum_hours=4)
