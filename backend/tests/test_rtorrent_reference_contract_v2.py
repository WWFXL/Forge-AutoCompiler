"""实际CppUnit命名registry属于原测试身份，不能误拒或放行错误前缀。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_contract_v2 import author_tests, validate_cppunit_output  # noqa: E402


def test_named_author_registry_with_slash_is_part_of_exact_leaf_identity():
    names = ["torrent/net::Suite::a", "torrent/net::Suite::b"]
    assert validate_cppunit_output("torrent/net::Suite::a : OK\ntorrent/net::Suite::b : OK\nOK (2)\n", names) == 2


@pytest.mark.parametrize("output", ["torrent/utils::Suite::a : OK\nOK (1)\n", "Suite::a : OK\nOK (1)\n", "torrent/net::Suite::a : OK\ntorrent/net::Suite::a : OK\nOK (1)\n", "OK (0)\n"])
def test_wrong_registry_missing_duplicate_or_empty_are_rejected(output):
    with pytest.raises(ValueError):
        validate_cppunit_output(output, ["torrent/net::Suite::a"])


def test_registry_is_read_from_author_source_not_inferred_from_outcome(tmp_path):
    (tmp_path / "test").mkdir()
    (tmp_path / "test/Makefile.am").write_text("TESTS = Net\nNet_SOURCES = net.h net.cc\n")
    (tmp_path / "test/net.h").write_text("CPPUNIT_TEST_SUITE(Suite); CPPUNIT_TEST(a);\n")
    (tmp_path / "test/net.cc").write_text('CPPUNIT_TEST_SUITE_NAMED_REGISTRATION(Suite, "torrent/net");\n')
    assert author_tests(tmp_path) == {"Net": ["torrent/net::Suite::a"]}
