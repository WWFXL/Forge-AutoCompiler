#!/usr/bin/env python3
"""固定候选的只读来源采集：不解包、不执行、不替换项目。"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import subprocess
import sys
import tarfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from forge_typed_evidence import digest, seal, write_json  # noqa: E402


def require_time(deadline):
    if datetime.now(UTC) >= datetime.fromisoformat(deadline.replace("Z", "+00:00")):
        raise ValueError("来源采集已到截止时间")


def inspect_archive(path, limits):
    """只通过 tarfile 读取普通成员；所有成员先验证，再读取任何内容。"""
    rows, snippets, members = [], [], []
    total, prefix, seen = 0, None, set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            parts = PurePosixPath(member.name).parts
            if not parts or member.name.startswith("/") or ".." in parts or "\\" in member.name or ".git" in parts:
                raise ValueError("来源成员路径越界或包含Git元数据")
            if member.name in seen or len(seen) >= limits["max_entries"]:
                raise ValueError("重复成员或成员数超限")
            seen.add(member.name)
            prefix = prefix or parts[0]
            if parts[0] != prefix:
                raise ValueError("来源归档不是单一项目根")
            if member.issym() or member.islnk():
                link = member.linkname
                target = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), link) if member.issym() else link)
                if link.startswith("/") or "\\" in link or target == ".." or not target.startswith(prefix + "/"):
                    raise ValueError("来源链接逃逸项目根")
            elif not (member.isdir() or member.isfile()):
                raise ValueError("来源包含特殊文件")
            if member.size < 0 or member.size > limits["max_file_bytes"]:
                raise ValueError("来源单文件超限")
            total += member.size
            if total > limits["max_uncompressed_bytes"]:
                raise ValueError("来源展开体积超限")
            members.append(member)
        for member in members:
            relative = PurePosixPath(member.name).relative_to(prefix).as_posix()
            row = {"path": relative, "size": member.size, "type": "directory" if member.isdir() else "symlink" if member.issym() else "hardlink" if member.islnk() else "file"}
            if member.issym() or member.islnk():
                row["target"] = member.linkname
            elif member.isfile():
                data = archive.extractfile(member).read(limits["max_file_bytes"] + 1)
                if len(data) != member.size:
                    raise ValueError("来源文件不完整")
                row["sha256"] = hashlib.sha256(data).hexdigest()
                name = PurePosixPath(relative).name.lower()
                if (
                    name in ("cmakelists.txt", "makefile", "makefile.am", "configure.ac", "autogen.sh", "bootstrap", "bootstrap.sh", ".gitmodules")
                    or name.startswith(("readme", "install", "testing"))
                    or relative.startswith(".github/workflows/")
                ):
                    text = data[: limits["snippet_bytes"]].decode("utf-8", errors="replace")
                    snippets.append({"path": relative, "sha256": row["sha256"], "truncated": len(data) > limits["snippet_bytes"], "content": "\n".join(f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1))})
            rows.append(row)
    return {"archive_root": prefix, "entries": rows, "uncompressed_bytes": total, "source_excerpts": snippets}


def download(url, path, limit):
    """精确commit归档；失败保留已下载的部分文件，不自动重试。"""
    request = urllib.request.Request(url, headers={"User-Agent": "Forge-source-catalog"})
    with urllib.request.urlopen(request, timeout=60) as response, path.open("xb") as output:
        total = 0
        while block := response.read(1024 * 1024):
            total += len(block)
            if total > limit:
                raise ValueError("压缩来源归档超限")
            output.write(block)


def collect_one(item, root, protocol):
    folder = root / item["repository"].replace("/", "--")
    frozen = json.loads((folder / "head.json").read_text())
    if frozen.get("status") != "head_frozen":
        return {**item, "status": "metadata_failed", "head_record": str(folder.relative_to(root) / "head.json")}
    commit = frozen["commit_sha"]
    archive = folder / "source.tar.gz"
    download(f"https://codeload.github.com/{item['repository']}/tar.gz/{commit}", archive, protocol["limits"]["max_compressed_bytes"])
    inspected = inspect_archive(archive, protocol["limits"])
    write_json(folder / "source-index.json", inspected)
    entries = {row["path"] for row in inspected["entries"]}
    roots = sorted(entries & {"CMakeLists.txt", "Makefile", "makefile", "configure", "configure.ac", "autogen.sh", "bootstrap", "bootstrap.sh"})
    test_entries = sorted(path for path in entries if re.search(r"(^|/)(test|tests|testing|check)(/|\.|$)", path, re.I) and not path.endswith((".c", ".h", ".cpp", ".cc")))
    return {
        **item,
        "status": "source_collected_pending_review",
        "commit_sha": commit,
        "source_archive_sha256": digest(archive),
        "archive": str(archive.relative_to(root)),
        "root_entries": roots,
        "test_entry_candidates": test_entries[:200],
        "has_gitmodules": ".gitmodules" in entries,
        "entries": len(entries),
        "uncompressed_bytes": inspected["uncompressed_bytes"],
    }


def collect_all(protocol, root, collector=collect_one):
    results = []
    for item in protocol["candidates"]:
        require_time(protocol["deadline_utc"])
        try:
            result = collector(item, root, protocol)
        except Exception as exc:
            result = {**item, "status": "source_collection_failed", "error_class": type(exc).__name__, "error": str(exc)[:500]}
        results.append(result)
        write_json(root / (item["repository"].replace("/", "--") + "-result.json"), result)
        print(json.dumps({key: result[key] for key in ("repository", "status")}), flush=True)
    return results


def freeze_heads(protocol, root):
    """先冻结全部heads；后续归档结果不影响项目选择或commit。"""
    for item in protocol["candidates"]:
        require_time(protocol["deadline_utc"])
        folder = root / item["repository"].replace("/", "--")
        folder.mkdir()
        try:
            response = subprocess.run(["gh", "api", f"repos/{item['repository']}/commits/HEAD"], capture_output=True, timeout=60, check=False)
            (folder / "head-response.json").write_bytes(response.stdout)
            if response.returncode:
                raise ValueError("GitHub精确head请求失败")
            payload = json.loads(response.stdout)
            commit = payload["sha"]
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ValueError("GitHub未返回完整commit")
            result = {"status": "head_frozen", "commit_sha": commit, "observed_utc": datetime.now(UTC).isoformat()}
        except Exception as exc:
            result = {"status": "metadata_failed", "error_class": type(exc).__name__, "error": str(exc)[:500]}
        write_json(folder / "head.json", result)
        history = []
        for revision in protocol["history_revisions"]:
            response = subprocess.run(["git", "grep", "-n", "-i", "-F", item["repository"], revision, "--", "benchmarks", "docs/research"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, check=False)
            history.append({"revision": revision, "exit_code": response.returncode, "matches": response.stdout, "scope": "仅指定提交的benchmarks和docs/research；URL命中不等于实际开发暴露，未命中不证明全历史未见"})
        write_json(folder / "history-url-search.json", history)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != "cpp-build-source-expansion-v1" or protocol["provider_calls"] != 0 or protocol["build_commands"] != 0 or len(protocol["candidates"]) != 12:
        raise ValueError("来源身份或零执行边界不匹配")
    require_time(protocol["deadline_utc"])
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise ValueError("来源采集组件变化")
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    results = []
    try:
        freeze_heads(protocol, root)
        results = collect_all(protocol, root)
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "provider_calls": 0, "build_commands": 0, "projects": results})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(results) == 12 else 1


if __name__ == "__main__":
    raise SystemExit(main())
