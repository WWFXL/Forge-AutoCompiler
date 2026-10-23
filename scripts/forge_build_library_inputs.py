#!/usr/bin/env python3
"""固定库任务的源码依赖图；只组装归档，不执行上游构建。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import tarfile
from pathlib import Path

from forge_build_reference_expansion import normalized_source
from forge_build_source_expansion import download, inspect_archive, require_time
from forge_typed_evidence import audit, digest, seal, write_json

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-library-inputs-v1"


def append_dependency(archive, dependency_archive, destination, limits):
    inspected = inspect_archive(dependency_archive, limits)
    prefix = inspected["archive_root"] + "/"
    with tarfile.open(dependency_archive) as source, tarfile.open(archive, "a") as target:
        present = {m.name.rstrip("/") for m in target.getmembers()}
        for member in source:
            if member.name.rstrip("/") == prefix.rstrip("/"):
                continue
            adjusted = copy.copy(member)
            adjusted.name = destination + "/" + member.name[len(prefix) :]
            if adjusted.name.rstrip("/") in present:
                raise ValueError("依赖覆盖既有源码")
            adjusted.pax_headers = {}
            if member.islnk():
                adjusted.linkname = destination + "/" + member.linkname[len(prefix) :]
            target.addfile(adjusted, source.extractfile(member) if member.isfile() else None)
    return {destination + "/" + row["path"]: row["sha256"] for row in inspected["entries"] if row["type"] == "file"}


def prepare(item, folder, protocol):
    folder.mkdir()
    parent = Path(protocol["parent_raw"]) / item["repository"].replace("/", "--")
    archive = folder / "source.tar"
    hashes = normalized_source(parent / "source.tar.gz", archive, protocol["limits"])
    dependencies = []
    for dep in item["dependencies"]:
        require_time(protocol["deadline_utc"])
        response = subprocess.run(["gh", "api", f"repos/{dep['repository']}/commits/{dep['ref']}"], capture_output=True, timeout=60, check=True)
        (folder / (dep["name"] + "-commit.json")).write_bytes(response.stdout)
        resolved = json.loads(response.stdout)["sha"]
        if len(dep["ref"]) == 40 and resolved != dep["ref"]:
            raise ValueError("依赖精确commit变化")
        path = folder / (dep["name"] + ".tar.gz")
        download(f"https://codeload.github.com/{dep['repository']}/tar.gz/{resolved}", path, protocol["limits"]["max_compressed_bytes"])
        hashes.update(append_dependency(archive, path, ".forge-deps/" + dep["name"], protocol["limits"]))
        dependencies.append({**dep, "commit_sha": resolved, "archive_sha256": digest(path)})
    if item.get("cpm"):
        dep = item["cpm"]
        path = folder / "CPM.cmake"
        download(dep["url"], path, 1024 * 1024)
        if digest(path) != dep["sha256"]:
            raise ValueError("CPM原作者声明SHA不匹配")
        with tarfile.open(archive, "a") as target:
            target.add(path, arcname=".forge-deps/cpm-cache/cpm/CPM_0.42.3.cmake")
        hashes[".forge-deps/cpm-cache/cpm/CPM_0.42.3.cmake"] = digest(path)
    write_json(folder / "source-hashes.json", hashes)
    write_json(folder / "dependency-index.json", dependencies)
    return {
        "name": item["name"],
        "repository": item["repository"],
        "commit_sha": item["commit_sha"],
        "status": "inputs_prepared",
        "archive": str(archive.relative_to(folder.parent)),
        "source_archive_sha256": digest(archive),
        "source_file_hashes_sha256": digest(folder / "source-hashes.json"),
        "dependencies": dependencies,
        "original_and_dependency_files": len(hashes),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != IDENTITY or protocol["provider_calls"] != 0:
        raise ValueError("输入身份变化")
    require_time(protocol["deadline_utc"])
    if audit(Path(protocol["parent_raw"]))["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("父归档身份变化")
    for name, expected in protocol["components"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("输入准备组件变化")
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    write_json(root / "release.json", {"revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()})
    rows = []
    try:
        for item in protocol["projects"]:
            require_time(protocol["deadline_utc"])
            try:
                row = prepare(item, root / item["name"], protocol)
            except Exception as exc:
                row = {"name": item["name"], "status": "inputs_failed", "error_class": type(exc).__name__, "error": str(exc)[:1000]}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        write_json(root / "result.json", {"identity": IDENTITY, "provider_calls": 0, "build_commands": 0, "projects": rows})
        print(json.dumps(seal(root, protocol, ROOT)), flush=True)
    return 0 if len(rows) == 3 and all(row["status"] == "inputs_prepared" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
