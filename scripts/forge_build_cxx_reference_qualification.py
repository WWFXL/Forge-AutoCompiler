#!/usr/bin/env python3
"""新增C++完整参考资格：来源图准备与一次性严格执行，禁止模型调用。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_cxx_source_qualification import REPOSITORIES  # noqa: E402
from forge_build_reference_expansion import normalized_source, run_reference  # noqa: E402
from forge_build_reference_repair_qualification import execute_schedule  # noqa: E402
from forge_build_source_expansion import download, inspect_archive, require_time  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.plan_workflow import BuildPlan  # noqa: E402

NAMES = ("yaml-cpp", "simdutf", "snappy")


def validate(protocol, phase):
    expected = f"cpp-build-cxx-{'reference-inputs' if phase == 'prepare' else 'reference-qualification'}-v1"
    if protocol["identity"] != expected or protocol["provider_calls"] != 0 or protocol["credentials_read"] is not False:
        raise ValueError("参考资格身份或零费用边界不符")
    require_time(protocol["deadline_utc"])
    for name, expected_hash in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected_hash:
            raise ValueError("冻结组件变化")
    parent = audit(Path(protocol["parent_evidence"]))
    if parent["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("父证据变化")
    if phase == "run":
        if tuple(item["name"] for item in protocol["projects"]) != NAMES:
            raise ValueError("固定三项目不可删除、重排或替换")
        parent_root = Path(protocol["parent_evidence"])
        prepared = json.loads((parent_root / "result.json").read_text())["projects"]
        for item, original in zip(protocol["projects"], prepared, strict=True):
            plan = BuildPlan.model_validate(item["plan"])
            if (plan.repository_url, plan.commit_sha, plan.source_archive_sha256) != (original["repository_url"], original["commit_sha"], original["source_archive_sha256"]):
                raise ValueError("参考方案与冻结来源图不同")
            if Path(item["source_archive"]).resolve() != (parent_root / original["archive"]).resolve() or digest(Path(item["source_archive"])) != plan.source_archive_sha256:
                raise ValueError("参考归档不是父来源图")
            if digest(Path(item["source_file_hashes_path"])) != item["source_file_hashes_sha256"] or item["source_file_hashes_sha256"] != original["source_file_hashes_sha256"]:
                raise ValueError("源码hash索引变化")
    elif tuple(item["repository"] for item in protocol["candidates"]) != REPOSITORIES:
        raise ValueError("固定来源候选变化")


def prepare(protocol, root, rows):
    source_root = Path(protocol["parent_evidence"])
    for item in protocol["candidates"]:
        require_time(protocol["deadline_utc"])
        repository = item["repository"]
        source = source_root / repository.replace("/", "--")
        folder = root / item["name"]
        folder.mkdir()
        commit = json.loads((source / "head.json").read_text())["commit_sha"]
        metadata = subprocess.run(["gh", "api", f"repos/{repository}"], capture_output=True, check=True, timeout=60)
        (folder / "repository-metadata.json").write_bytes(metadata.stdout)
        tree = subprocess.run(["gh", "api", f"repos/{repository}/git/trees/{commit}?recursive=1"], capture_output=True, check=True, timeout=60)
        (folder / "git-tree.json").write_bytes(tree.stdout)
        tree_data = json.loads(tree.stdout)
        if tree_data.get("truncated"):
            raise ValueError("源码图被截断")
        observed = sorted((row["path"], row["sha"]) for row in tree_data["tree"] if row["mode"] == "160000")
        expected = sorted((row["path"], row["commit"]) for row in item["dependencies"])
        if observed != expected:
            raise ValueError("未登记或变化的gitlink；禁止静默遗漏依赖")
        archive = folder / "source.tar"
        hashes = normalized_source(source / "source.tar.gz", archive, protocol["limits"])
        for dependency in item["dependencies"]:
            target = folder / (dependency["path"].replace("/", "--") + ".tar.gz")
            download(f"https://codeload.github.com/{dependency['repository']}/tar.gz/{dependency['commit']}", target, protocol["limits"]["max_compressed_bytes"])
            inspected = inspect_archive(target, protocol["limits"])
            write_json(target.with_suffix(".index.json"), inspected)
            prefix = inspected["archive_root"] + "/"
            with tarfile.open(target) as original, tarfile.open(archive, "a") as output:
                present = {member.name for member in output.getmembers()}
                for member in original:
                    if member.name.rstrip("/") == prefix.rstrip("/"):
                        continue
                    adjusted = copy.copy(member)
                    adjusted.name = dependency["path"] + "/" + member.name[len(prefix) :]
                    if adjusted.name in present:
                        raise ValueError("依赖覆盖原源码路径")
                    adjusted.pax_headers = {}
                    if member.islnk():
                        adjusted.linkname = dependency["path"] + "/" + member.linkname[len(prefix) :]
                    output.addfile(adjusted, original.extractfile(member) if member.isfile() else None)
            hashes.update({dependency["path"] + "/" + row["path"]: row["sha256"] for row in inspected["entries"] if row["type"] == "file"})
        hashes_path = folder / "source-hashes.json"
        write_json(hashes_path, hashes)
        rows.append(
            {
                "name": item["name"],
                "repository_url": f"https://github.com/{repository}",
                "commit_sha": commit,
                "archive": str(archive.relative_to(root)),
                "source_archive_sha256": digest(archive),
                "source_file_hashes_sha256": digest(hashes_path),
                "dependencies": item["dependencies"],
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run"))
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol, args.phase)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    if args.phase == "run":
        subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    rows, unobserved, reason = [], [], "initialization_not_completed"
    try:
        if args.phase == "prepare":
            rows = prepare(protocol, root, rows)
            reason = None
        else:
            rows, unobserved, reason = execute_schedule(protocol, root, executor=run_reference)
    except BaseException as exc:
        reason = type(exc).__name__
        unobserved = [{"name": name, "status": "not_observed_or_unclosed"} for name in NAMES[len(rows) :]]
        raise
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "provider_calls": 0, "projects": rows, "unobserved_schedule": unobserved, "stopping_reason": reason})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == 3 and not unobserved else 1


if __name__ == "__main__":
    raise SystemExit(main())
