#!/usr/bin/env python3
"""固定三个 C++ 候选的来源资格；复用归档检查，不执行上游代码。"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from forge_build_source_expansion import collect_all, freeze_heads, require_time
from forge_typed_evidence import digest, seal, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = ("jbeder/yaml-cpp", "simdutf/simdutf", "google/snappy")


def validate(protocol):
    if (
        protocol["identity"] != "cpp-build-cxx-source-qualification-v1"
        or tuple(row["repository"] for row in protocol["candidates"]) != REPOSITORIES
        or protocol["provider_calls"] != 0
        or protocol["build_commands"] != 0
    ):
        raise ValueError("新增C++来源身份、固定候选或零执行边界不符")
    require_time(protocol["deadline_utc"])
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise ValueError("来源组件变化")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    results = []
    try:
        # 保存所有可达Git历史的有限路径/精确名称检索，不声称训练或外部历史未见。
        for repository in REPOSITORIES:
            history = subprocess.run(
                ["git", "log", "--all", "--format=%H", "--name-only", "-i", "-G", repository, "--", "benchmarks", "docs/research"],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=True,
            )
            write_json(root / (repository.replace("/", "--") + "-reachable-history.json"), {"query": repository, "matches": history.stdout, "scope": "本机可达Git历史benchmarks/docs/research精确owner/name正则；不是外部/训练未见证明"})
        freeze_heads(protocol, root)
        results = collect_all(protocol, root)
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "provider_calls": 0, "build_commands": 0, "projects": results})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(results) == len(REPOSITORIES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
