"""悬空链接必须保留在原源码索引中。"""

import io
import tarfile

import pytest

from deerflow.compile.archive_source_index import archive_index_contract, complete_index_fingerprint, observe_original_links
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.source_preparation import paths_fingerprint


def test_dangling_source_link_is_included_without_following_target(tmp_path):
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w") as handle:
        item = tarfile.TarInfo("Makefile.am")
        item.size = 1
        handle.addfile(item, io.BytesIO(b"x"))
        item = tarfile.TarInfo("examples/example.ts")
        item.type, item.linkname = tarfile.SYMTYPE, "../missing"
        handle.addfile(item)
    contract = archive_index_contract(archive)
    assert contract["symlinks"] == {"examples/example.ts": "../missing"}
    assert complete_index_fingerprint(["Makefile.am"], contract) == paths_fingerprint(["Makefile.am", "examples/example.ts"])
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples/example.ts").symlink_to("../missing")
    assert observe_original_links(tmp_path, contract)["examples/example.ts"]["passed"]
    (tmp_path / "examples/example.ts").unlink()
    (tmp_path / "examples/example.ts").write_text("替换链接应拒绝")
    assert not observe_original_links(tmp_path, contract)["examples/example.ts"]["passed"]


def test_complete_index_does_not_ignore_missing_regular_source():
    contract = dict(regular_paths=["a"], symlinks={"b": "a"}, complete_index_sha256=paths_fingerprint(["a", "b"]))
    with pytest.raises(PlanContractError, match="普通原文件集合"):
        complete_index_fingerprint([], contract)
