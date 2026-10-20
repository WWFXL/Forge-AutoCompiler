"""Git对象与归档逐字节、链接及权限对应；拒绝不完整来源。"""

import copy
import io
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_cxx_cross_source as source


def fixture(tmp_path):
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w") as handle:
        for name, data, mode in [("CMakeLists.txt", b"project(arbitrary)\n", 0o644), ("run.sh", b"#!/bin/sh\n", 0o755)]:
            item = tarfile.TarInfo(name)
            item.mode = mode
            item.size = len(data)
            handle.addfile(item, io.BytesIO(data))
        link = tarfile.TarInfo("alias")
        link.type = tarfile.SYMTYPE
        link.linkname = "run.sh"
        handle.addfile(link)
    tree = dict(
        truncated=False,
        tree=[
            dict(path="CMakeLists.txt", type="blob", mode="100644", sha=source.blob_hash(b"project(arbitrary)\n")),
            dict(path="run.sh", type="blob", mode="100755", sha=source.blob_hash(b"#!/bin/sh\n")),
            dict(path="alias", type="blob", mode="120000", sha=source.blob_hash(b"run.sh")),
        ],
    )
    return archive, tree


def test_real_tar_file_bytes_symlink_text_and_executable_mode_match_git_objects(tmp_path):
    archive, tree = fixture(tmp_path)
    assert source.check_tree(archive, tree) == dict(git_blob_correspondence_verified=True, files_and_links=3, symlinks=1)


@pytest.mark.parametrize("change", ["truncated", "gitlink", "missing", "extra", "content", "mode", "link"])
def test_incomplete_or_different_source_cannot_qualify(tmp_path, change):
    archive, tree = fixture(tmp_path)
    tree = copy.deepcopy(tree)
    if change == "truncated":
        tree["truncated"] = True
    elif change == "gitlink":
        tree["tree"].append(dict(path="dependency", type="commit", mode="160000", sha="a" * 40))
    elif change == "missing":
        tree["tree"].pop()
    elif change == "extra":
        tree["tree"].append(dict(path="new", type="blob", mode="100644", sha=source.blob_hash(b"")))
    elif change == "content":
        tree["tree"][0]["sha"] = "a" * 40
    elif change == "mode":
        tree["tree"][1]["mode"] = "100644"
    else:
        tree["tree"][2]["sha"] = source.blob_hash(b"other")
    with pytest.raises(ValueError):
        source.check_tree(archive, tree)
