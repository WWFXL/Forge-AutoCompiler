#!/usr/bin/env python3
"""五个既定候选的完整根来源采集；只读归档，不取新HEAD、不执行源码。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from forge_build_source_expansion import download, inspect_archive
from forge_build_task_source_screen import verify_tree
from forge_typed_evidence import audit, digest, seal, write_json

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-prospective-task-contract-sources-v1"
RANKS = (9, 10, 14, 21, 30)
LIMITS = {"max_compressed_bytes": 128 * 1024**2, "max_uncompressed_bytes": 512 * 1024**2, "max_entries": 30000, "max_file_bytes": 32 * 1024**2, "snippet_bytes": 8192}


def verify_recursive_tree(tree, expected):
    """按完整递归条目重建每个子树，而非只信任API的根sha字段。"""
    if tree.get("truncated") or tree["sha"] != expected:
        raise ValueError("递归树截断或根身份变化")
    paths, groups, directories = {}, defaultdict(list), {"": expected}
    for row in tree["tree"]:
        path = row["path"]
        if not path or path.startswith("/") or any(p in ("", ".", "..", ".git") for p in path.split("/")) or "\\" in path or "\0" in path or path in paths:
            raise ValueError("递归树路径重复或越界")
        if (row["type"], row["mode"]) not in (("tree", "040000"), ("blob", "100644"), ("blob", "100755"), ("blob", "120000"), ("commit", "160000")):
            raise ValueError("递归树类型和权限不匹配")
        paths[path] = row
        parent, _, name = path.rpartition("/")
        groups[parent].append({**row, "path": name})
        if row["type"] == "tree":
            directories[path] = row["sha"]
    if set(groups) - set(directories):
        raise ValueError("递归树缺少父目录或在gitlink下伪造文件")
    for path, sha in directories.items():
        verify_tree({"sha": sha, "tree": groups[path], "truncated": False}, sha)
    return paths


def verify_archive(archive, tree, limits):
    inspected = inspect_archive(archive, limits)
    paths = verify_recursive_tree(tree, tree["sha"])
    wanted = {path: row for path, row in paths.items() if row["type"] == "blob"}
    prefix, actual = inspected["archive_root"] + "/", {}
    with tarfile.open(archive) as handle:
        for member in handle:
            if member.isdir():
                continue
            path = member.name[len(prefix) :]
            if member.issym():
                data, mode = member.linkname.encode(), "120000"
            elif member.isfile():
                data, mode = handle.extractfile(member).read(), "100755" if member.mode & 0o111 else "100644"
            else:
                raise ValueError("Git来源不接受硬链接或特殊文件")
            sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            actual[path] = {"sha": sha, "mode": mode, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    if set(actual) != set(wanted) or any((r["sha"], r["mode"]) != (wanted[p]["sha"], wanted[p]["mode"]) for p, r in actual.items()):
        raise ValueError("归档与完整Git blob/执行权限不对应")
    gitlinks = [{"path": p, "commit": r["sha"]} for p, r in paths.items() if r["mode"] == "160000"]
    return inspected, {"root_archive_verified": True, "root_blobs": len(actual), "root_subtrees": 1 + sum(r["type"] == "tree" for r in paths.values()), "gitlinks": gitlinks, "dependency_graph_complete": False, "file_index": actual}


def collect_one(protocol, row, folder):
    endpoint = f"repos/{row['repository']}/git/trees/{row['root_tree_sha']}?recursive=1"
    response = subprocess.run(["gh", "api", endpoint], capture_output=True, timeout=60, check=True)
    (folder / "git-tree.json").write_bytes(response.stdout)
    tree = json.loads(response.stdout)
    verify_recursive_tree(tree, row["root_tree_sha"])
    archive = folder / "source.tar.gz"
    download(f"https://codeload.github.com/{row['repository']}/tar.gz/{row['commit_sha']}", archive, protocol["limits"]["max_compressed_bytes"])
    inspected, proof = verify_archive(archive, tree, protocol["limits"])
    write_json(folder / "archive-inspection.json", inspected)
    write_json(folder / "file-index.json", proof.pop("file_index"))
    write_json(folder / "source-proof.json", {**proof, "archive_sha256": digest(archive), "archive_bytes": archive.stat().st_size, "uncompressed_bytes": inspected["uncompressed_bytes"]})


def validate(protocol):
    if protocol["identity"] != IDENTITY or tuple(r["rank"] for r in protocol["candidates"]) != RANKS or protocol["limits"] != LIMITS:
        raise ValueError("新来源身份、固定五项或资源界限变化")
    if any(protocol[k] != 0 for k in ("provider_calls", "model_cost_usd", "build_commands", "docker_calls")) or protocol["provider_credentials_read"] is not False:
        raise ValueError("零模型/执行边界变化")
    for name, expected in protocol["components"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("冻结组件变化:" + name)
    parent = Path(protocol["parent_raw"])
    if audit(parent)["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("父证据清单变化")
    original = json.loads((parent / "result.json").read_text())["rows"]
    expected = [{key: r[key] for key in ("rank", "repository", "commit_sha", "root_tree_sha")} for r in original if r["rank"] in RANKS]
    if protocol["candidates"] != expected:
        raise ValueError("不接受更换HEAD、排序或补位")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--worker-rank", type=int)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    if args.worker_rank is not None:
        row = next(r for r in protocol["candidates"] if r["rank"] == args.worker_rank)
        collect_one(protocol, row, args.output_root)
        return 0
    deadline = datetime.fromisoformat(protocol["deadline_utc"])
    if (deadline - datetime.now(UTC)).total_seconds() < 60:
        raise ValueError("免费准备时窗不足，不启动身份")
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "execution.json", {"release": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "identity": IDENTITY, "provider_calls": 0, "upstream_execution": False})
    rows, reason = [], None
    try:
        for item in protocol["candidates"]:
            remaining = (deadline - datetime.now(UTC)).total_seconds()
            if remaining < 60:
                reason = "deadline_reservation"
                break
            folder = root / f"{item['rank']:02d}"
            folder.mkdir()
            row = {**item, "task_qualified": False, "holdout": False, "build_result": "not_observed", "role": "development_contract_review_only"}
            try:
                with (folder / "worker.stdout.log").open("wb") as stdout, (folder / "worker.stderr.log").open("wb") as stderr:
                    subprocess.run(
                        [sys.executable, __file__, "--protocol", str(args.protocol.resolve()), "--output-root", str(folder), "--worker-rank", str(item["rank"])], stdout=stdout, stderr=stderr, timeout=min(300, remaining - 30), check=True
                    )
                row.update(json.loads((folder / "source-proof.json").read_text()), source_status="observed")
            except (subprocess.SubprocessError, OSError, ValueError) as exc:
                row.update(source_status="failed", error_class=type(exc).__name__, retry=False)
            write_json(folder / "result.json", row)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        write_json(root / "result.json", {"identity": IDENTITY, "rows": rows, "not_observed": protocol["candidates"][len(rows) :], "stop_reason": reason, "provider_calls": 0, "build_commands": 0, "docker_calls": 0})
        print(json.dumps(seal(root, protocol, ROOT)), flush=True)
    return 0 if len(rows) == 5 and all(r["source_status"] == "observed" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
