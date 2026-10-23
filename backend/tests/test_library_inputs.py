"""依赖归档组装保留源码字节，并拒绝覆盖。"""

import importlib
import io
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
inputs = importlib.import_module("forge_build_library_inputs")


def test_dependency_bytes_and_collision(tmp_path):
    dependency = tmp_path / "dep.tar.gz"
    with tarfile.open(dependency, "w:gz") as archive:
        member = tarfile.TarInfo("dep-revision/include/dep.hpp")
        member.size = 8
        archive.addfile(member, io.BytesIO(b"original"))
    assembled = tmp_path / "source.tar"
    with tarfile.open(assembled, "w"):
        pass
    limits = dict(max_entries=10, max_file_bytes=100, max_uncompressed_bytes=1000, snippet_bytes=100)
    hashes = inputs.append_dependency(assembled, dependency, ".forge-deps/dep", limits)
    with tarfile.open(assembled) as archive:
        assert archive.extractfile(".forge-deps/dep/include/dep.hpp").read() == b"original"
    assert hashes[".forge-deps/dep/include/dep.hpp"]
    with pytest.raises(ValueError, match="覆盖"):
        inputs.append_dependency(assembled, dependency, ".forge-deps/dep", limits)
