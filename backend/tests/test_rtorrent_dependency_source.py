"""同版本依赖约束不能被默认分支或近似版本静默替代。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_dependency_source import require_version  # noqa: E402


def test_libtorrent_requires_exact_author_version():
    assert require_version("AC_INIT([libtorrent],[0.16.25],[mail])", "0.16.25") == "0.16.25"


@pytest.mark.parametrize("text", ["AC_INIT([libtorrent],[0.16.26],[mail])", "AC_INIT([libtorrent],[0.16.25-rc1],[mail])", "AC_INIT([rtorrent],[0.16.25],[mail])", "# no project version", "# AC_INIT([libtorrent],[0.16.25],[mail])"])
def test_default_head_cannot_replace_required_dependency_version(text):
    with pytest.raises(ValueError, match="所需精确版本"):
        require_version(text, "0.16.25")
