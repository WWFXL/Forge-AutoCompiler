#!/usr/bin/env python3
"""固定来源池的只读合同材料采集；不运行上游源码，不把静态信号当构建资格。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from forge_typed_evidence import digest, seal, write_json

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-prospective-task-source-screen-v1"
ROOT_NAMES = (
    "README.md",
    "README.rst",
    "README",
    "README.txt",
    "INSTALL.md",
    "INSTALL",
    "BUILD.md",
    "BUILDING.md",
    "CMakeLists.txt",
    "Makefile",
    "makefile",
    "GNUmakefile",
    "Makefile.am",
    "configure.ac",
    "configure.in",
    ".gitmodules",
    "meson.build",
    "xmake.lua",
)
CHILD_NAMES = ("CMakeLists.txt", "Makefile.am", "Makefile", "meson.build", "README.md", "README")
SUBTREES = ("test", "tests", "testing", "unittests", ".github")
MAX_BLOB_BYTES = 262144
MAX_BLOBS = 24


def git_object(kind, raw):
    return hashlib.sha1(kind.encode() + b" " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def verify_tree(tree, expected):
    if tree.get("truncated") or tree["sha"] != expected:
        raise ValueError("Git tree缺失/截断/身份不符")
    rows = tree["tree"]
    names = [r["path"] for r in rows]
    if len(set(names)) != len(names) or any(not n or "/" in n or n in (".", "..") for n in names):
        raise ValueError("Git非递归tree路径不合法")
    ordered = sorted(rows, key=lambda r: (r["path"] + ("/" if r["type"] == "tree" else "")).encode())
    raw = b"".join((r["mode"].lstrip("0") + " " + r["path"]).encode() + b"\0" + bytes.fromhex(r["sha"]) for r in ordered)
    if git_object("tree", raw) != expected:
        raise ValueError("Git tree对象字节重建不符")
    return {r["path"]: r for r in rows}


def decode_blob(response, expected, size):
    if response["encoding"] != "base64" or response["sha"] != expected:
        raise ValueError("Git blob编码或身份不符")
    raw = base64.b64decode(response["content"].replace("\n", ""), validate=True)
    if len(raw) != size or response["size"] != size or git_object("blob", raw) != expected:
        raise ValueError("Git blob内容身份或长度不符")
    raw.decode("utf-8")
    return raw


def before_request(protocol):
    remaining = (datetime.fromisoformat(protocol["deadline_utc"]) - datetime.now(UTC)).total_seconds()
    if remaining < 60:
        raise TimeoutError("截止前保留60秒封存；不开始新请求")


def fetch(endpoint, target, protocol):
    if target.exists():
        return json.loads(target.read_text())
    before_request(protocol)
    try:
        result = subprocess.run(["gh", "api", endpoint], capture_output=True, timeout=25)
    except subprocess.TimeoutExpired:
        write_json(target.with_suffix(".failure.json"), {"kind": "TimeoutExpired", "retry": False})
        raise
    if result.returncode:
        write_json(target.with_suffix(".failure.json"), {"returncode": result.returncode, "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(), "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(), "retry": False})
        raise ValueError("GitHub请求失败，无自动重试")
    with target.open("xb") as handle:
        handle.write(result.stdout)
    return json.loads(result.stdout)


def collect(row, parent_root, folder, protocol):
    tree = json.loads((parent_root / f"{row['rank']:02d}" / "root-tree.json").read_text())
    entries = verify_tree(tree, row["root_tree_sha"])
    write_json(folder / "root-tree.json", tree)
    requested, material, skipped, subtrees = {}, [], [], []

    def read_file(path, entry):
        if entry["type"] != "blob" or entry["mode"] not in ("100644", "100755"):
            skipped.append({"path": path, "reason": "not_ordinary_blob"})
            return
        if entry["size"] > MAX_BLOB_BYTES or len(material) >= MAX_BLOBS:
            skipped.append({"path": path, "reason": "predeclared_size_or_file_cap", "sha": entry["sha"], "size": entry["size"]})
            return
        sha = entry["sha"]
        if sha not in requested:
            response = fetch(f"repos/{row['repository']}/git/blobs/{sha}", folder / f"blob-{sha}.json", protocol)
            raw = decode_blob(response, sha, entry["size"])
            (folder / f"blob-{sha}.txt").write_bytes(raw)
            requested[sha] = raw
        material.append({"path": path, "git_blob_sha": sha, "sha256": hashlib.sha256(requested[sha]).hexdigest(), "bytes": len(requested[sha]), "local_text": f"blob-{sha}.txt"})

    for name in ROOT_NAMES:
        if name in entries:
            read_file(name, entries[name])
    for name in SUBTREES:
        if name not in entries or entries[name]["type"] != "tree":
            continue
        sha = entries[name]["sha"]
        child = fetch(f"repos/{row['repository']}/git/trees/{sha}", folder / f"tree-{sha}.json", protocol)
        items = verify_tree(child, sha)
        subtrees.append({"path": name, "sha": sha, "entries": child["tree"]})
        for child_name in CHILD_NAMES:
            if child_name in items:
                read_file(name + "/" + child_name, items[child_name])
        if name == ".github" and "workflows" in items and items["workflows"]["type"] == "tree":
            workflow_sha = items["workflows"]["sha"]
            workflow = fetch(f"repos/{row['repository']}/git/trees/{workflow_sha}", folder / f"tree-{workflow_sha}.json", protocol)
            workflow_items = verify_tree(workflow, workflow_sha)
            subtrees.append({"path": ".github/workflows", "sha": workflow_sha, "entries": workflow["tree"]})
            for path in sorted(n for n in workflow_items if n.endswith((".yml", ".yaml")))[:4]:
                read_file(".github/workflows/" + path, workflow_items[path])
    return {"materials": material, "skipped_materials": skipped, "subtrees": subtrees}


def validate(protocol):
    if protocol["identity"] != IDENTITY or protocol["rules"] != {
        "root_names": list(ROOT_NAMES),
        "child_names": list(CHILD_NAMES),
        "subtrees": list(SUBTREES),
        "max_blob_bytes": MAX_BLOB_BYTES,
        "max_blobs_per_repository": MAX_BLOBS,
        "max_workflows": 4,
    }:
        raise ValueError("身份或采集规则不符")
    if any(protocol[k] != 0 for k in ("provider_calls", "model_cost_usd", "build_commands", "docker_calls")) or protocol["provider_credentials_read"] is not False:
        raise ValueError("零费用/上游执行边界变化")
    parent = Path(protocol["parent_raw"])
    for rel, expected in protocol["parent_files"].items():
        if digest(parent / rel) != expected:
            raise ValueError("父冻结来源改变:" + rel)
    result = json.loads((parent / "result.json").read_text())
    rows = result["rows"]
    if [r["rank"] for r in rows] != list(range(1, 31)) or protocol["candidates"] != rows:
        raise ValueError("原30项完整排名/身份改变，不补位")
    for name, expected in protocol["components"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("采集组件改变:" + name)
    return parent, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    parent, candidates = validate(protocol)
    before_request(protocol)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "execution.json", {"release": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "identity": IDENTITY, "provider_calls": 0, "upstream_execution": False})
    rows, reason = [], None
    try:
        for candidate in candidates:
            try:
                before_request(protocol)
            except TimeoutError:
                reason = "deadline_reservation"
                break
            folder = root / f"{candidate['rank']:02d}"
            folder.mkdir()
            row = {**candidate, "role": "source_contract_review_only", "task_qualified": False, "build_result": "not_observed", "holdout": False}
            try:
                row.update(**collect(candidate, parent, folder, protocol), source_material_status="observed")
            except (ValueError, KeyError, UnicodeError, subprocess.TimeoutExpired, TimeoutError) as exc:
                row.update(source_material_status="failed", error_class=type(exc).__name__, error_message=str(exc)[:300])
            write_json(folder / "result.json", row)
            rows.append(row)
            print(json.dumps({"rank": row["rank"], "repository": row["repository"], "status": row["source_material_status"], "files": len(row.get("materials", []))}), flush=True)
    finally:
        write_json(root / "result.json", {"identity": IDENTITY, "rows": rows, "unobserved": candidates[len(rows) :], "stop_reason": reason, "provider_calls": 0, "build_commands": 0, "docker_calls": 0})
        print(json.dumps(seal(root, protocol, ROOT)), flush=True)
    return 0 if len(rows) == 30 and all(r["source_material_status"] == "observed" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
