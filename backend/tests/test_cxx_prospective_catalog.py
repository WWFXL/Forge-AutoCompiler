"""前瞻目录保留不合格/未知，不把文件名信号写成构建资格。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_cxx_prospective_catalog as catalog  # noqa: E402


def test_multiple_regular_root_signals_remain_unqualified():
    tree = {"tree": [{"path": p, "type": "blob", "mode": "100644"} for p in ("CMakeLists.txt", "Makefile", "configure.ac")]}
    result = catalog.root_signals(tree)
    assert result["candidate_build_systems"] == ["cmake", "make", "autotools"]
    assert result["task_qualified"] is False and result["holdout"] is False
    assert result["build_result"] == result["linux_target_applicability"] == "not_observed"


def test_symlink_entry_is_not_a_regular_build_signal():
    assert not catalog.root_signals({"tree": [{"path": "Makefile", "type": "blob", "mode": "120000"}]})["candidate_build_systems"]


@pytest.mark.parametrize("kind", ["incomplete", "duplicate", "wrong_language"])
def test_invalid_search_frame_cannot_be_replaced(kind):
    items = [dict(id=i, full_name=f"owner/repo{i}", language="C++", archived=False, fork=False, stargazers_count=1000 - i) for i in range(30)]
    response = dict(items=items, incomplete_results=kind == "incomplete")
    if kind == "duplicate":
        items[-1] = items[0]
    if kind == "wrong_language":
        items[-1]["language"] = "C"
    with pytest.raises(ValueError):
        catalog.search_items(response)
