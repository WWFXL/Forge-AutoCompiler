"""第二批来源不能以第一批身份续写，也不能把失败候选换掉。"""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
spec = importlib.util.spec_from_file_location("make_source_catalog", Path(__file__).resolve().parents[2] / "scripts/forge_build_make_source_catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def protocol():
    return {
        "identity": "cpp-build-make-source-catalog-v1",
        "provider_calls": 0,
        "build_commands": 0,
        "deadline_utc": "2099-01-01T00:00:00Z",
        "components": {},
        "candidates": [{"repository": name} for name in ["kokke/tiny-AES-c", "libcrc/libcrc", "h2o/picohttpparser", "jedisct1/libhydrogen", "clibs/buffer", "clibs/commander"]],
    }


def test_replacement_candidate_or_reused_identity_is_rejected():
    valid = protocol()
    catalog.validate(valid)
    valid["candidates"][0]["repository"] = "substitute/project"
    with pytest.raises(ValueError, match="替换"):
        catalog.validate(valid)
    valid = protocol()
    valid["identity"] = "cpp-build-source-expansion-v1"
    with pytest.raises(ValueError, match="身份"):
        catalog.validate(valid)


@pytest.mark.parametrize("field", ["provider_calls", "build_commands"])
def test_no_provider_or_build_boundary_cannot_be_expanded(field):
    valid = protocol()
    valid[field] = 1
    with pytest.raises(ValueError, match="零执行"):
        catalog.validate(valid)
