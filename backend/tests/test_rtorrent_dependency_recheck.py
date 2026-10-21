"""冻结来源复核应容纳实际M4引用，但不能放宽版本与项目约束。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_dependency_recheck import require_version  # noqa: E402


@pytest.mark.parametrize("declaration", ["AC_INIT(libtorrent,0.16.25,mail)", "AC_INIT([libtorrent],[0.16.25],[mail])", "AC_INIT([[libtorrent]],[[0.16.25]],[[mail]])"])
def test_original_autoconf_quoting_preserves_exact_version(declaration):
    assert require_version(declaration, "0.16.25") == "0.16.25"


@pytest.mark.parametrize(
    "declaration",
    [
        "# AC_INIT([[libtorrent]],[[0.16.25]],[[mail]])",
        "AC_INIT([[libtorrent]],[[0.16.26]],[[mail]])",
        "AC_INIT([[libtorrent]],[[0.16.25-rc1]],[[mail]])",
        "AC_INIT([[rtorrent]],[[0.16.25]],[[mail]])",
        "AC_INIT([[libtorrent],[[0.16.25]],[[mail]])",
        "AC_INIT([[libtorrent]],[[0.16.25],[mail])",
        "AC_INIT(libtorrent,0.16.250,mail)",
        "AC_INIT(libtorrent,0.16.25extra,mail)",
    ],
)
def test_recheck_does_not_admit_comments_malformed_or_nearby_versions(declaration):
    with pytest.raises(ValueError):
        require_version(declaration, "0.16.25")
