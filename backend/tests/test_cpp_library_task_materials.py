"""防止新材料阶段缩小或改写固定来源分母。"""

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
screen = importlib.import_module("forge_build_cpp_library_task_materials")


def test_parent_fixed_denominator_and_snapshot_are_required(tmp_path):
    rows = [dict(rank=i, status="metadata_observed", task_qualified=False) for i in range(1, 21)]
    parent = tmp_path / "result.json"
    parent.write_text(json.dumps(dict(identity="cpp-build-cpp-library-source-catalog-v1", rows=rows)))
    protocol = dict(
        identity=screen.IDENTITY,
        rules=screen.RULES,
        deadline_utc="2026-10-22T19:37:37+00:00",
        provider_calls=0,
        model_cost_usd=0,
        build_commands=0,
        docker_calls=0,
        provider_credentials_read=False,
        parent_raw=str(tmp_path),
        parent_files={"result.json": screen.digest(parent)},
        candidates=rows,
        components={},
    )
    assert screen.validate(protocol)[1] == rows
    protocol["candidates"] = rows[:-1]
    with pytest.raises(ValueError, match="固定20项"):
        screen.validate(protocol)
    protocol["candidates"] = rows
    parent.write_text("{}")
    with pytest.raises(ValueError, match="父来源冻结"):
        screen.validate(protocol)
