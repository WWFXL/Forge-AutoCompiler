"""门禁固定覆盖及只使用本地脚本模型的边界。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_plan_predicate_gate as gate


def test_gate_fixed_coverage_and_negative():
    rows = gate.schedule()
    assert len(rows) == 14
    assert {(r["project"], r["method"]) for r in rows if r["case"] == "normal"} == {(p, m) for p in ("buffer", "uncrustify", "libverto") for m in gate.METHODS}
    assert sum(r["case"] == "missing_path_rejected" for r in rows) == 1


def test_gate_correction_changes_only_false_stdout_into_real_file_check():
    original = gate.reference_actions({"steps": [{"step_id": "build", "role": "build", "command": "make -j2", "source": "Makefile", "expected": "成功"}]})
    before = gate.controlled_actions(original, "stdout_path_repair", initial=True)
    after = gate.controlled_actions(original, "stdout_path_repair", initial=False)
    assert before.steps[0].command == after.steps[0].command
    assert before.steps[0].stdout_contains == ("/workspace/repo/test",)
    assert after.steps[0].stdout_contains == () and after.steps[0].files_exist == ("test",)


def test_gate_model_is_local_zero_usage():
    response = gate.fake_model([{"reason": "夹具", "steps": []}]).invoke("不访问网络")
    assert response.response_metadata["model_name"] == "scripted-gate"
    assert response.usage_metadata["total_tokens"] == 0
