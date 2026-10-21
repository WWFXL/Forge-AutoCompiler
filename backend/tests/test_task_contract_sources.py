"""真实Git来源夹具覆盖递归对象/权限/链接/未闭合依赖，避免将归档当构建资格。"""

import copy
import io
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_task_contract_sources as sources  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "src").mkdir()
    (root / "src/hello.cc").write_text("int main() { return 0; }\n")
    (root / "build.sh").write_text("#!/bin/sh\nexit 0\n")
    (root / "build.sh").chmod(0o755)
    (root / "link").symlink_to("src/hello.cc")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "update-index", "--add", "--cacheinfo", "160000," + "a" * 40 + ",dependency"], check=True)
    tree = subprocess.check_output(["git", "-C", str(root), "write-tree"], text=True).strip()
    entries = []
    output = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-r", "-t", tree], text=True)
    for line in output.splitlines():
        fields, path = line.split("\t")
        mode, kind, sha = fields.split()
        entries.append({"path": path, "mode": mode, "type": kind, "sha": sha})
    return root, {"sha": tree, "tree": entries, "truncated": False}


def archive_fixture(root, target, tamper=None):
    with tarfile.open(target, "w:gz") as output:
        output.add(root, arcname="snapshot", filter=lambda member: None if "/.git" in member.name else member)
        if tamper:
            data = b"untracked"
            member = tarfile.TarInfo("snapshot/extra.cc")
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))


def test_complete_tree_and_archive_match_real_git_with_unfilled_gitlink(repo, tmp_path):
    root, tree = repo
    sources.verify_recursive_tree(tree, tree["sha"])
    archive = tmp_path / "source.tar.gz"
    archive_fixture(root, archive)
    _, proof = sources.verify_archive(archive, tree, sources.LIMITS)
    assert proof["root_archive_verified"]
    assert proof["gitlinks"] == [{"path": "dependency", "commit": "a" * 40}]
    assert proof["dependency_graph_complete"] is False
    assert proof["root_blobs"] == 3


@pytest.mark.parametrize("problem", ["tamper", "missing_subtree", "truncated", "duplicate", "traversal"])
def test_recursive_tree_cannot_hide_invalid_or_missing_source(repo, problem):
    _, original = repo
    tree = copy.deepcopy(original)
    if problem == "tamper":
        tree["tree"][0]["sha"] = "0" * 40
    elif problem == "missing_subtree":
        tree["tree"] = [r for r in tree["tree"] if r["type"] != "tree"]
    elif problem == "truncated":
        tree["truncated"] = True
    elif problem == "duplicate":
        tree["tree"].append(tree["tree"][0])
    else:
        tree["tree"][0]["path"] = "../escape"
    with pytest.raises(ValueError):
        sources.verify_recursive_tree(tree, tree["sha"])


@pytest.mark.parametrize("problem", ["content", "mode", "extra"])
def test_archive_content_and_executable_contract_are_enforced(repo, tmp_path, problem):
    root, tree = repo
    if problem == "content":
        (root / "src/hello.cc").write_text("changed")
    if problem == "mode":
        (root / "build.sh").chmod(0o644)
    archive = tmp_path / "source.tar.gz"
    archive_fixture(root, archive, tamper=problem == "extra")
    with pytest.raises(ValueError, match="归档与完整Git"):
        sources.verify_archive(archive, tree, sources.LIMITS)
