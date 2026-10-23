"""防止新来源阶段偷偷更换已冻结版本或候选。"""

import copy
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sources = importlib.import_module("forge_build_library_sources")


def test_fixed_parent_versions_cannot_be_replaced(tmp_path):
    rows = [dict(rank=i, repository=f"owner/r{i}", commit_sha="a" * 40) for i in range(1, 21)]
    parent = tmp_path / "result.json"
    parent.write_text(json.dumps({"rows": rows}))
    protocol = dict(
        identity=sources.IDENTITY,
        provider_calls=0,
        deadline_utc="2099-01-01T00:00:00Z",
        components={},
        parent_raw=str(tmp_path),
        parent_files={"result.json": sources.digest(parent)},
        candidates=[r for r in rows if r["rank"] in sources.RANKS],
    )
    sources.validate(protocol)
    changed = copy.deepcopy(protocol)
    changed["candidates"][0]["commit_sha"] = "b" * 40
    with pytest.raises(ValueError, match="父目录固定"):
        sources.validate(changed)
    parent.write_text("{}")
    with pytest.raises(ValueError, match="父目录身份"):
        sources.validate(protocol)
