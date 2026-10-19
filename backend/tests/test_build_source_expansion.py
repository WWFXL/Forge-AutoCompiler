"""来源目录拒绝危险归档，单项目失败不能隐藏其余候选。"""

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("source_expansion", Path(__file__).resolve().parents[2] / "scripts/forge_build_source_expansion.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)
LIMITS = {"max_entries": 20, "max_file_bytes": 1000, "max_uncompressed_bytes": 2000, "snippet_bytes": 500}


def archive_at(path, names):
    with tarfile.open(path, "w:gz") as archive:
        for name, kind, content in names:
            member = tarfile.TarInfo(name)
            if kind == "file":
                raw = content.encode()
                member.size = len(raw)
                archive.addfile(member, io.BytesIO(raw))
            else:
                member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.FIFOTYPE
                member.linkname = content
                archive.addfile(member)


def test_readonly_source_index_records_recipe_clues_without_extraction(tmp_path):
    path = tmp_path / "source.tar.gz"
    archive_at(path, [("repo/CMakeLists.txt", "file", "add_test(NAME real COMMAND runner)"), ("repo/sub/readme", "symlink", "../CMakeLists.txt")])
    inspected = catalog.inspect_archive(path, LIMITS)
    assert len(inspected["entries"]) == 2
    assert "add_test" in inspected["source_excerpts"][0]["content"]
    assert inspected["entries"][1]["target"] == "../CMakeLists.txt"
    assert not (tmp_path / "repo").exists()


@pytest.mark.parametrize(
    "members",
    [
        [("/repo/file", "file", "x")],
        [("repo/../file", "file", "x")],
        [("repo/link", "symlink", "../../outside")],
        [("repo/pipe", "fifo", "")],
        [("repo/file", "file", "x"), ("repo/file", "file", "y")],
        [("repo/file", "file", "x"), ("other/file", "file", "y")],
        [("repo/file", "file", "x" * 1001)],
    ],
)
def test_unsafe_or_overlimit_archive_rejected_before_read(tmp_path, members):
    path = tmp_path / "source.tar.gz"
    archive_at(path, members)
    with pytest.raises(ValueError):
        catalog.inspect_archive(path, LIMITS)


def test_source_failure_preserved_and_next_candidate_still_collected(tmp_path):
    def collector(item, root, protocol):
        if item["repository"] == "first/fails":
            raise ValueError("受控来源失败")
        return {**item, "status": "source_collected_pending_review"}

    results = catalog.collect_all({"deadline_utc": "2099-01-01T00:00:00Z", "candidates": [{"repository": "first/fails"}, {"repository": "second/works"}]}, tmp_path, collector)
    assert [row["status"] for row in results] == ["source_collection_failed", "source_collected_pending_review"]
    assert (tmp_path / "first--fails-result.json").exists()
    assert (tmp_path / "second--works-result.json").exists()
