"""原CppUnit开始/结束事件允许中间诊断，身份与总数保持严格。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_contract_v3 import validate_cppunit_output  # noqa: E402


def test_diagnostic_between_start_and_end_matches_author_listener():
    output = "torrent/net::Suite::a\nai_ref_err got wrong error, expected x, got y\n\n : OK\ntorrent/net::Suite::b : OK\nOK (2)\n"
    assert validate_cppunit_output(output, ["torrent/net::Suite::a", "torrent/net::Suite::b"]) == 2


@pytest.mark.parametrize(
    "output",
    [
        " : OK\nOK (1)\n",
        "torrent/net::Suite::a\nOK (1)\n",
        "torrent/net::Suite::a\ntorrent/net::Suite::a : OK\nOK (1)\n",
        "torrent/net::Suite::a : OK\ntorrent/net::Suite::a : OK\nOK (1)\n",
        "wrong::Suite::a : OK\nOK (1)\n",
        "torrent/net::Suite::a\n : assertion\n : OK\nOK (1)\n",
        "torrent/net::Suite::a : OK\nOK (0)\n",
        "torrent/net::Suite::a : OK\nOK (1)\nOK (1)\n",
        "torrent/net::Suite::a arbitrary\n : OK\nOK (1)\n",
    ],
)
def test_missing_duplicate_unknown_failure_or_wrong_total_rejected(output):
    with pytest.raises(ValueError):
        validate_cppunit_output(output, ["torrent/net::Suite::a"])
