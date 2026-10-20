"""容器目录信任必须限于确切工作目录，不改变其他任务。"""

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("cxx_metadata_v2", ROOT / "scripts/forge_build_cxx_reference_metadata_qualification_v2.py")
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


def test_only_exact_container_directory_is_trusted():
    old = {"projects": [{"name": "simdutf", "plan": {"steps": [{"role": "dependency", "command": "cmake --version && git init -q && git add --force --all"}, {"role": "smoke", "command": "ctest --no-tests=error"}]}}]}
    saved = copy.deepcopy(old)
    new = metadata.trusted_project(old)
    assert old == saved and new["plan"]["steps"][1:] == saved["projects"][0]["plan"]["steps"][1:]
    command = new["plan"]["steps"][0]["command"]
    assert command == "cmake --version && git init -q && git config --global --add safe.directory /workspace/repo && git add --force --all"
    assert "*" not in command


def test_parent_without_expected_index_command_is_rejected():
    old = {"projects": [{"name": "simdutf", "plan": {"steps": [{"role": "dependency", "command": "git add --all"}]}}]}
    with pytest.raises(ValueError, match="唯一目录信任"):
        metadata.trusted_project(old)
