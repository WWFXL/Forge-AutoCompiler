"""来源对象核验与不执行边界；使用真实Git对象而非实现生成的期望值。"""

import base64
import copy
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_build_task_source_screen as screen  # noqa: E402


def test_blob_identity_matches_git_and_rejects_tampering(tmp_path):
    raw = "上游文档\n".encode()
    p = tmp_path / "file"
    p.write_bytes(raw)
    expected = subprocess.check_output(["git", "hash-object", str(p)], text=True).strip()
    response = {"sha": expected, "size": len(raw), "encoding": "base64", "content": base64.b64encode(raw).decode()}
    assert screen.decode_blob(response, expected, len(raw)) == raw
    response["content"] = base64.b64encode(b"tamper").decode()
    with pytest.raises(ValueError, match="内容身份"):
        screen.decode_blob(response, expected, len(raw))


def test_tree_sorting_and_directory_modes_match_git(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a").mkdir()
    (tmp_path / "a/child").write_text("nested")
    (tmp_path / "a.c").write_text("author")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    sha = subprocess.check_output(["git", "-C", str(tmp_path), "write-tree"], text=True).strip()
    output = subprocess.check_output(["git", "-C", str(tmp_path), "ls-tree", sha], text=True)
    entries = []
    for line in output.splitlines():
        fields, name = line.split("\t")
        mode, kind, object_sha = fields.split()
        entries.append({"path": name, "mode": mode, "type": kind, "sha": object_sha})
    tree = {"sha": sha, "tree": list(reversed(entries)), "truncated": False}
    assert set(screen.verify_tree(tree, sha)) == {"a", "a.c"}
    bad = copy.deepcopy(tree)
    bad["tree"][0]["sha"] = "0" * 40
    with pytest.raises(ValueError, match="字节重建"):
        screen.verify_tree(bad, sha)


@pytest.mark.parametrize("problem", ["truncated", "duplicate", "traversal"])
def test_untrusted_tree_is_rejected_before_reading_files(problem):
    row = {"path": "README.md", "mode": "100644", "type": "blob", "sha": "b" * 40}
    tree = {"sha": "a" * 40, "tree": [row], "truncated": problem == "truncated"}
    if problem == "duplicate":
        tree["tree"].append(row)
    if problem == "traversal":
        row["path"] = "../README.md"
    with pytest.raises(ValueError):
        screen.verify_tree(tree, tree["sha"])


def test_same_object_is_not_requested_twice(tmp_path, monkeypatch):
    target = tmp_path / "saved.json"
    target.write_text('{"cached":true}')
    monkeypatch.setattr(screen.subprocess, "run", lambda *a, **k: pytest.fail("不应重复请求相同对象"))
    assert screen.fetch("unused", target, {}) == {"cached": True}
