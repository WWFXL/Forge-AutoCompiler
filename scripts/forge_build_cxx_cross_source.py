#!/usr/bin/env python3
"""固定C++ Make/Autotools来源；归档逐blob对应，不执行上游代码。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import tarfile

from forge_build_reference_expansion import normalized_source
from forge_build_source_expansion import download, inspect_archive, require_time
from forge_typed_evidence import digest, seal, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-cxx-cross-system-source-v1"
SOURCES = (
    {
        "name": "tinyxml2",
        "repository": "leethomason/tinyxml2",
        "commit": "321ea883b7190d4e85cae5512a12e5eaa8f8731f",
        "tag": "10.0.0",
        "requested_build_system": "make",
    },
    {
        "name": "libconfig",
        "repository": "hyperrealm/libconfig",
        "commit": "a42cb47c1526a4f2ed025fcbb2289863375bc898",
        "tag": "v1.8.2",
        "requested_build_system": "autotools",
    },
)


def blob_hash(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def check_tree(archive, tree):
    if tree.get("truncated") or any(r["mode"] == "160000" for r in tree["tree"]):
        raise ValueError("来源树不完整或包含未登记gitlink")
    wanted = {r["path"]: r for r in tree["tree"] if r["type"] == "blob"}
    actual = {}
    with tarfile.open(archive) as handle:
        for member in handle:
            if member.isdir():
                continue
            if member.issym():
                raw, mode = member.linkname.encode(), "120000"
            elif member.isfile():
                raw, mode = (
                    handle.extractfile(member).read(),
                    "100755" if member.mode & 0o111 else "100644",
                )
            else:
                raise ValueError("来源图不接受硬链接或特殊成员")
            if member.name in actual:
                raise ValueError("来源路径重复")
            actual[member.name] = {"sha": blob_hash(raw), "mode": mode}
    if set(wanted) != set(actual) or any(
        (actual[n]["sha"], actual[n]["mode"]) != (wanted[n]["sha"], wanted[n]["mode"])
        for n in actual
    ):
        raise ValueError("归档文件/链接/执行权限与固定commit的Git blob不一致")
    return {
        "git_blob_correspondence_verified": True,
        "files_and_links": len(actual),
        "symlinks": sum(r["mode"] == "120000" for r in actual.values()),
    }


def validate(protocol):
    if (
        protocol["identity"] != IDENTITY
        or protocol["candidates"] != list(SOURCES)
        or protocol["provider_calls"] != 0
        or protocol["build_commands"] != 0
        or protocol["credentials_read"] is not False
        or protocol["max_new_provider_cost_usd"] != 0
    ):
        raise ValueError("固定双来源、身份或零执行/费用边界不符")
    require_time(protocol["deadline_utc"])
    for name, h in protocol["components"].items():
        if digest(REPO_ROOT / name) != h:
            raise ValueError("来源组件变化：" + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    rows = []
    reason = "initialization_not_completed"
    try:
        for item in protocol["candidates"]:
            require_time(protocol["deadline_utc"])
            folder = root / item["name"]
            folder.mkdir()
            try:
                for label, endpoint in [
                    ("repository-metadata", f"repos/{item['repository']}"),
                    ("tag", f"repos/{item['repository']}/git/ref/tags/{item['tag']}"),
                    (
                        "commit",
                        f"repos/{item['repository']}/git/commits/{item['commit']}",
                    ),
                    (
                        "tree",
                        f"repos/{item['repository']}/git/trees/{item['commit']}?recursive=1",
                    ),
                ]:
                    response = subprocess.run(
                        ["gh", "api", endpoint],
                        capture_output=True,
                        check=True,
                        timeout=60,
                    )
                    with (folder / (label + ".json")).open("xb") as f:
                        f.write(response.stdout)
                commit = json.loads((folder / "commit.json").read_text())
                assert commit["sha"] == item["commit"]
                tag = json.loads((folder / "tag.json").read_text())
                assert (
                    tag["object"]["type"] == "commit"
                    and tag["object"]["sha"] == item["commit"]
                )
                compressed = folder / "source.tar.gz"
                download(
                    f"https://codeload.github.com/{item['repository']}/tar.gz/{item['commit']}",
                    compressed,
                    protocol["limits"]["max_compressed_bytes"],
                )
                inspected = inspect_archive(compressed, protocol["limits"])
                write_json(folder / "archive-inspection.json", inspected)
                normalized = folder / "source.tar"
                hashes = normalized_source(compressed, normalized, protocol["limits"])
                write_json(folder / "source-file-hashes.json", hashes)
                proof = check_tree(
                    normalized, json.loads((folder / "tree.json").read_text())
                )
                rows.append(
                    {
                        **item,
                        "qualified": True,
                        "source_archive": str(normalized),
                        "source_archive_sha256": digest(normalized),
                        "source_file_hashes_path": str(
                            folder / "source-file-hashes.json"
                        ),
                        "source_file_hashes_sha256": digest(
                            folder / "source-file-hashes.json"
                        ),
                        **proof,
                    }
                )
                print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
            except Exception as exc:
                rows.append(
                    {
                        **item,
                        "qualified": False,
                        "error_class": type(exc).__name__,
                        "error": str(exc)[:1000],
                    }
                )
                reason = "source_qualification_failed"
                break
        else:
            reason = None
    finally:
        write_json(
            root / "result.json",
            dict(
                identity=IDENTITY,
                provider_calls=0,
                build_commands=0,
                projects=rows,
                not_observed=protocol["candidates"][len(rows) :],
                stop_reason=reason,
            ),
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
