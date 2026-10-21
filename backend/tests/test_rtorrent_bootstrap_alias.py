"""只扩展精确标准生成命令形式，不能扩大作者文件或输出内容权限。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_bootstrap_alias import alias_boundary  # noqa: E402


def test_alias_keeps_every_input_and_exact_output_hash():
    root = Path(__file__).resolve().parents[2]
    original = json.loads((root / "benchmarks/manifests/cpp-build-rtorrent-reference-v5.json").read_text())["file_boundary"]
    value = alias_boundary(original).model_dump(mode="json")
    assert {k: v for k, v in value.items() if k != "generations"} == {k: v for k, v in original.items() if k != "generations"}
    assert value["generations"][:2] == original["generations"]
    for old, new in zip(original["generations"], value["generations"][2:], strict=True):
        assert {k: v for k, v in old.items() if k != "command"} == {k: v for k, v in new.items() if k != "command"}
        assert new["command"] == old["command"].replace("-ivf", "-fi")


def test_unreviewed_bootstrap_cannot_be_normalized():
    with pytest.raises(ValueError):
        alias_boundary({"generations": [{"command": "autoreconf --other-options"}]})
