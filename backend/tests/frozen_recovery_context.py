"""仅测试使用：在已核对哈希的历史源码上回放冻结提案，不改变生产版本门禁。"""

import hashlib
import json
import subprocess
from pathlib import Path

PRE_REPAIR_REVISION = "292a4ca882ab3b07f2fd838b968a5647c44a95b8"
ROOT = Path(__file__).resolve().parents[2]


def install_frozen_recovery_context(monkeypatch, tmp_path, script, test_module, *, scoped=False):
    request = json.loads((ROOT / "benchmarks/fixtures/recovery-harness-proposal-r2-v1/request.json").read_text())
    prompt = request["packet"]["base_prompt"]
    from deerflow.compile import simple_build_task

    monkeypatch.setattr(simple_build_task, "SIMPLE_PROMPT", prompt)
    monkeypatch.setattr(script, "SIMPLE_PROMPT", prompt)
    if hasattr(test_module, "SIMPLE_PROMPT"):
        monkeypatch.setattr(test_module, "SIMPLE_PROMPT", prompt)
    if not scoped:
        return
    scope = json.loads((script.FIXTURE / "scope.json").read_text())
    target = tmp_path / "frozen-source"
    for name, expected in scope["components"].items():
        data = (ROOT / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            data = subprocess.check_output(["git", "show", f"{PRE_REPAIR_REVISION}:{name}"], cwd=ROOT)
        assert hashlib.sha256(data).hexdigest() == expected, name
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.setattr(script, "ROOT", target)
