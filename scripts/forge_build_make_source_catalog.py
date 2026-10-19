#!/usr/bin/env python3
"""第二批Make来源的独立只读入口；复用已冻结来源边界。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forge_build_source_expansion import REPO_ROOT, collect_all, freeze_heads, require_time
from forge_typed_evidence import digest, seal, write_json


def validate(protocol):
    expected = ["kokke/tiny-AES-c", "libcrc/libcrc", "h2o/picohttpparser", "jedisct1/libhydrogen", "clibs/buffer", "clibs/commander"]
    if protocol["identity"] != "cpp-build-make-source-catalog-v1" or protocol["provider_calls"] != 0 or protocol["build_commands"] != 0:
        raise ValueError("独立Make来源身份或零执行边界不符")
    if [item["repository"] for item in protocol["candidates"]] != expected:
        raise ValueError("不得替换固定Make来源或顺序")
    require_time(protocol["deadline_utc"])
    for name, expected_sha in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected_sha:
            raise ValueError("Make来源采集组件变化")


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
        freeze_heads(protocol, root)
        results = collect_all(protocol, root)
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "provider_calls": 0, "build_commands": 0, "projects": results})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(results) == 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
