"""依赖装配保持来源字节、独立路径与作者文件保护。"""

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_prepare import combined_archive, protected_unchanged  # noqa: E402


def source(tmp_path, name, prefix):
    data = (name + "\n").encode()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    # Git tree长度按实际字节计算，避免夹具依赖手写常量。
    body = b"100644 file\0" + bytes.fromhex(blob)
    tree = hashlib.sha1(b"tree " + str(len(body)).encode() + b"\0" + body).hexdigest()
    path = tmp_path / (name + ".json")
    path.write_text(json.dumps({"sha": tree, "tree": [{"path": "file", "sha": blob, "mode": "100644", "type": "blob"}], "truncated": False}))
    archive = tmp_path / (name + ".tar.gz")
    with tarfile.open(archive, "w:gz") as t:
        directory = tarfile.TarInfo("upstream")
        directory.type = tarfile.DIRTYPE
        t.addfile(directory)
        member = tarfile.TarInfo("upstream/file")
        member.size = len(data)
        member.mode = 0o644
        t.addfile(member, io.BytesIO(data))
    return {"tree": str(path), "tree_sha": tree, "archive": str(archive), "prefix": prefix}, data


def test_combined_archive_keeps_both_original_bytes_and_dependency_namespace(tmp_path):
    main, a = source(tmp_path, "main", "")
    dep, b = source(tmp_path, "dependency", "vendor-libtorrent/")
    target = tmp_path / "source.tar"
    baseline = combined_archive([main, dep], target)
    with tarfile.open(target) as t:
        assert t.extractfile("file").read() == a
        assert t.extractfile("vendor-libtorrent/file").read() == b
    assert set(baseline) == {"file", "vendor-libtorrent/file"}


def test_conflicting_dependency_paths_are_rejected(tmp_path):
    a, _ = source(tmp_path, "a", "")
    b, _ = source(tmp_path, "b", "")
    with pytest.raises(ValueError, match="路径冲突"):
        combined_archive([a, b], tmp_path / "conflict.tar")


def test_bootstrap_cannot_change_author_source_even_when_new_outputs_are_expected(tmp_path):
    p = tmp_path / "configure.ac"
    p.write_text("original")
    baseline = {"configure.ac": hashlib.sha256(p.read_bytes()).hexdigest()}
    (tmp_path / "configure").write_text("generated")
    assert "configure" in protected_unchanged(tmp_path, baseline)
    p.write_text("changed")
    with pytest.raises(ValueError, match="改写作者"):
        protected_unchanged(tmp_path, baseline)
