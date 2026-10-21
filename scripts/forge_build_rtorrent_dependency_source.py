#!/usr/bin/env python3
"""冻结同版本libtorrent的当前默认分支精确身份；不构建，不接受版本替换。"""

from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from forge_build_source_expansion import download
from forge_build_task_contract_sources import LIMITS, verify_archive, verify_recursive_tree
from forge_typed_evidence import audit, digest, seal, write_json

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-rtorrent-dependency-source-v1"
REPOSITORY = "rakshasa/libtorrent"


def require_version(text, required):
    match = re.search(r"(?m)^\s*AC_INIT\s*\(\s*\[?libtorrent\]?\s*,\s*\[?([0-9][\w.+-]*)", text)
    if not match or match.group(1) != required:
        raise ValueError("默认分支libtorrent不是所需精确版本；保留但不换版本")
    return match.group(1)


def fetch(endpoint, target, protocol):
    if (datetime.fromisoformat(protocol["deadline_utc"]) - datetime.now(UTC)).total_seconds() < 60:
        raise ValueError("截止保留60秒，不开始新请求")
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, timeout=60, check=True)
    with target.open("xb") as output:
        output.write(result.stdout)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != IDENTITY or protocol["repository"] != REPOSITORY or protocol["required_version"] != "0.16.25" or protocol["provider_calls"] != 0 or protocol["build_commands"] != 0 or protocol["limits"] != LIMITS:
        raise ValueError("身份、版本或零执行边界不符")
    for path, expected in protocol["components"].items():
        if digest(ROOT / path) != expected:
            raise ValueError("冻结组件变化")
    if audit(Path(protocol["parent_raw"]))["inventory_canonical_sha256"] != protocol["parent_inventory_sha256"]:
        raise ValueError("父证据改变")
    remaining = (datetime.fromisoformat(protocol["deadline_utc"]) - datetime.now(UTC)).total_seconds()
    if remaining < 360:
        raise ValueError("不足300秒采集及60秒封存，不启动身份")
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(root / "execution.json", {"release": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "provider_calls": 0, "upstream_execution": False})
    result = {"identity": IDENTITY, "repository": REPOSITORY, "source_qualified": False, "task_qualified": False, "build_result": "not_observed", "provider_calls": 0, "retry": False}

    def stop_on_timeout(signum, frame):
        raise TimeoutError("依赖来源300秒总时限")

    signal.signal(signal.SIGALRM, stop_on_timeout)
    signal.alarm(300)
    try:
        metadata = fetch(f"repos/{REPOSITORY}", root / "repository.json", protocol)
        ref = fetch(f"repos/{REPOSITORY}/git/ref/heads/{quote(metadata['default_branch'], safe='')}", root / "ref.json", protocol)
        if ref["object"]["type"] != "commit":
            raise ValueError("默认分支未指向commit")
        commit_sha = ref["object"]["sha"]
        commit = fetch(f"repos/{REPOSITORY}/git/commits/{commit_sha}", root / "commit.json", protocol)
        if commit["sha"] != commit_sha:
            raise ValueError("commit身份不符")
        result.update(commit_sha=commit_sha, root_tree_sha=commit["tree"]["sha"])
        write_json(root / "frozen-identity.json", {"repository": REPOSITORY, "branch": metadata["default_branch"], "commit_sha": commit_sha, "root_tree_sha": commit["tree"]["sha"]})
        tree = fetch(f"repos/{REPOSITORY}/git/trees/{commit['tree']['sha']}?recursive=1", root / "git-tree.json", protocol)
        verify_recursive_tree(tree, commit["tree"]["sha"])
        archive = root / "source.tar.gz"
        download(f"https://codeload.github.com/{REPOSITORY}/tar.gz/{commit_sha}", archive, LIMITS["max_compressed_bytes"])
        inspected, proof = verify_archive(archive, tree, LIMITS)
        with tarfile.open(archive) as handle:
            text = handle.extractfile(inspected["archive_root"] + "/configure.ac").read().decode()
        version = require_version(text, protocol["required_version"])
        write_json(root / "file-index.json", proof.pop("file_index"))
        write_json(root / "archive-inspection.json", inspected)
        result.update(**proof, version=version, source_qualified=not proof["gitlinks"], source_archive_sha256=digest(archive), note="仅依赖根源码/版本资格，系统包/完整测试/生成关系/真实构建仍待独立参考；不是策略效果")
    except Exception as exc:
        result.update(error_class=type(exc).__name__, error=str(exc)[:500])
    finally:
        signal.alarm(0)
        write_json(root / "result.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        print(json.dumps(seal(root, protocol, ROOT)), flush=True)
    return 0 if result["source_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
