"""原测试身份不能被空计数、重复输出或缩小子集替代。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_contract import author_tests, validate_cppunit_output  # noqa: E402


def test_all_original_leaf_tests_and_cppunit_total_are_required():
    assert validate_cppunit_output("Suite::a : OK\nSuite::b : OK\nOK (2)\n", ["Suite::a", "Suite::b"]) == 2


@pytest.mark.parametrize("output", ["OK (0)\n", "Suite::a : OK\nOK (1)\n", "Suite::a : OK\nSuite::a : OK\nOK (2)\n", "Suite::a : OK\nSuite::b : error\nOK (2)\n", "Suite::a : OK\nSuite::b : OK\nOK (2)\nOK (2)\n"])
def test_empty_subset_duplicate_failed_or_ambiguous_test_reports_fail(output):
    with pytest.raises(ValueError):
        validate_cppunit_output(output, ["Suite::a", "Suite::b"])


def test_denominator_is_taken_from_author_programs_and_sources(tmp_path):
    (tmp_path / "test").mkdir()
    (tmp_path / "test/Makefile.am").write_text("TESTS = Core Rpc\nCommon = helper.h\nCore_SOURCES = $(Common) core.h\nRpc_SOURCES = $(Common) rpc.h\n")
    (tmp_path / "test/helper.h").write_text("// no tests\n")
    (tmp_path / "test/core.h").write_text("CPPUNIT_TEST_SUITE(Core); CPPUNIT_TEST(a); // CPPUNIT_TEST(fake);\n")
    (tmp_path / "test/rpc.h").write_text("CPPUNIT_TEST_SUITE(Rpc); CPPUNIT_TEST(b); CPPUNIT_TEST(c);\n")
    assert author_tests(tmp_path) == {"Core": ["Core::a"], "Rpc": ["Rpc::b", "Rpc::c"]}
