"""源码元数据准备必须保留原测试和冻结身份。"""

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("cxx_metadata", ROOT / "scripts/forge_build_cxx_reference_metadata_qualification.py")
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


def test_index_preparation_does_not_modify_source_config_test_or_delivery():
    old = {"projects": [{"name": "simdutf", "plan": {"steps": [{"role": "dependency", "command": "cmake --version"}, {"role": "configure", "command": "cmake -S . -B build"}, {"role": "smoke", "command": "ctest --no-tests=error"}]}}]}
    saved = copy.deepcopy(old)
    new = metadata.prepared_project(old)
    assert old == saved
    assert new["plan"]["steps"][1:] == saved["projects"][0]["plan"]["steps"][1:]
    assert new["plan"]["steps"][0]["command"] == "cmake --version && git init -q && git add --force --all"


def test_cannot_repeat_existing_metadata_preparation():
    old = {"projects": [{"name": "simdutf", "plan": {"steps": [{"role": "dependency", "command": "git init -q"}]}}]}
    with pytest.raises(ValueError, match="重复追加"):
        metadata.prepared_project(old)
