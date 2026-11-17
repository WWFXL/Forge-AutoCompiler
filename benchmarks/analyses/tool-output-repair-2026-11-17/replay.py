"""只读真实libass错误，比较封存观察器和修复实现；不连接Provider。"""
import importlib.util
import json
from pathlib import Path

from deerflow.compile.simple_planning_context import PlanningContext

ROOT = Path(__file__).resolve().parents[3]
fixture = json.loads((ROOT / "benchmarks/fixtures/e59-output-errors.json").read_text())
original = fixture["tool_error"]
old_file = Path(fixture["source_root"]) / "source-snapshot/backend/packages/harness/deerflow/compile/simple_planning_context.py"
spec = importlib.util.spec_from_file_location("e59_frozen_planning_context", old_file)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
try:
    module.PlanningContext({}).observe(original["name"], original["arguments"], original["content"])
except json.JSONDecodeError as error:
    old_result = dict(error=type(error).__name__, detail=str(error))
else:
    raise AssertionError("封存观察器未重现原失败")
context = PlanningContext({})
context.observe(original["name"], original["arguments"], original["content"], status="error")
assert context.pending_reads == [False] and not context.reads
result = dict(provider_calls=0, original_event=original["path"], original_event_file_sha256=original["sha256"], frozen_observer=old_result, repaired_observer=dict(exception=None, new_evidence=False), note="真实Agent图的后续响应由脚本提供；不证明Flash自主纠正或成功率提升。")
print(json.dumps(result, ensure_ascii=False, indent=2))
