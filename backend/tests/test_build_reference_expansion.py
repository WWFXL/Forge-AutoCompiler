"""参考任务只移动归档根；项目失败保留、清理失败停止。"""

import importlib.util
import io
import tarfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("reference_expansion", Path(__file__).resolve().parents[2] / "scripts/forge_build_reference_expansion.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def test_normalized_archive_preserves_file_bytes_and_parent_relative_link(tmp_path):
    raw, output = tmp_path / "raw.tar.gz", tmp_path / "normalized.tar"
    with tarfile.open(raw, "w:gz") as handle:
        member = tarfile.TarInfo("repo/README.md")
        member.size = 6
        handle.addfile(member, io.BytesIO(b"source"))
        member = tarfile.TarInfo("repo/sub/readme")
        member.type, member.linkname = tarfile.SYMTYPE, "../README.md"
        handle.addfile(member)
    hashes = reference.normalized_source(raw, output, {"max_entries": 10, "max_file_bytes": 1000, "max_uncompressed_bytes": 2000, "snippet_bytes": 500})
    assert list(hashes) == ["README.md"]
    with tarfile.open(output) as handle:
        assert handle.extractfile("README.md").read() == b"source"
        assert handle.getmember("sub/readme").linkname == "../README.md"
        handle.extractall(tmp_path / "tree", filter="data")
    assert (tmp_path / "tree/sub/readme").read_bytes() == b"source"


def test_build_failure_does_not_replace_or_skip_following_project(tmp_path):
    called = []

    def execute(item, folder, protocol):
        called.append(item["name"])
        return {"name": item["name"], "status": "stopped" if item["name"] == "first" else "verified", "qualified": item["name"] != "first", "cleanup": {"succeeded": True}}

    rows = reference.execute_schedule({"deadline_utc": "2099-01-01T00:00:00Z", "projects": [{"name": "first"}, {"name": "second"}]}, tmp_path, execute)
    assert called == ["first", "second"]
    assert [row["qualified"] for row in rows] == [False, True]


def test_cleanup_failure_stops_before_next_project(tmp_path):
    def execute(item, folder, protocol):
        return {"name": item["name"], "status": "stopped", "qualified": False, "cleanup": {"succeeded": False}}

    rows = reference.execute_schedule({"deadline_utc": "2099-01-01T00:00:00Z", "projects": [{"name": "first"}, {"name": "second"}]}, tmp_path, execute)
    assert len(rows) == 1 and not rows[0]["qualified"]
