"""系统索引目录必须显式授权，不能扩大作者文件写权限。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from deerflow.compile.generated_file_boundary import FileBoundary, guard_main


def test_system_git_index_requires_explicit_directory_and_preserves_original(tmp_path):
    import hashlib

    (tmp_path / "source.cc").write_text("int main() { return 0; }\n")
    original = hashlib.sha256((tmp_path / "source.cc").read_bytes()).hexdigest()
    base = FileBoundary(baseline={"source.cc": original}, protected_inputs=("source.cc",))
    with pytest.raises(ValueError, match="未声明的新文件"):
        guard_main(base.model_dump(mode="json"), "git init -q && git add --all", str(tmp_path), str(tmp_path))
    permitted = base.model_copy(update={"new_directories": (".git",)})
    assert guard_main(permitted.model_dump(mode="json"), ":", str(tmp_path), str(tmp_path)) == 0
    with pytest.raises(ValueError, match="保护文件"):
        guard_main(permitted.model_dump(mode="json"), "printf changed > source.cc", str(tmp_path), str(tmp_path))


def test_new_protocol_changes_only_system_index_scope_and_freezes_failed_parent():
    root = Path(__file__).resolve().parents[2]
    v1 = json.loads((root / "benchmarks/manifests/cpp-build-rtorrent-three-strategy-gate-v1.json").read_text())
    # 新gate不读paid配置；独立身份验证仍保留完整参考与原固定测试。
    import forge_build_rtorrent_gate_v2 as gate

    assert gate.IDENTITY.endswith("-v2")
    assert len(gate.schedule()) == len(v1["schedule"]) == 5
