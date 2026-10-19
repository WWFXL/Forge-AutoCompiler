"""Make参考不能扩展模型授权或替换失败来源。"""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
spec = importlib.util.spec_from_file_location("make_reference", Path(__file__).resolve().parents[2] / "scripts/forge_build_make_reference.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def test_alternative_identity_cannot_write_make_reference_evidence():
    with pytest.raises(ValueError, match="身份"):
        reference.validate({"identity": "cpp-build-reference-expansion-v1", "provider_calls": 0})


def test_provider_call_is_outside_reference_boundary():
    with pytest.raises(ValueError, match="Provider"):
        reference.validate({"identity": "cpp-build-make-reference-v1", "provider_calls": 1})


def test_make_candidates_cannot_be_replaced():
    with pytest.raises(ValueError, match="替换"):
        reference.validate({"identity": "cpp-build-make-reference-v1", "provider_calls": 0, "projects": [{"name": "libhydrogen"}, {"name": "commander"}]})
