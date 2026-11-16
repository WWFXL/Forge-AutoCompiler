#!/usr/bin/env python3
"""本轮18项目只读来源采集；不调用模型、不执行构建。"""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from forge_build_simple_task import save
from forge_recovery_harness_sources import collect_one
from forge_typed_evidence import digest

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "benchmarks/fixtures/harness-update-comparison-v1/selection.json"


def collect(output):
    output.mkdir(parents=True, exist_ok=False)
    projects = json.loads(SELECTION.read_text())["projects"]
    save(
        output / "scope.json",
        dict(
            kind="zero_provider_source_preparation",
            issue=809,
            provider_calls=0,
            automatic_retry=False,
            selection_sha256=digest(SELECTION),
        ),
    )

    def head(item):
        row = dict(item)
        if row["name"] == "libffi":
            row["commit_sha"] = "3d0ce1e6fcf19f853894862abcbac0ae78a7be60"
        else:
            repo = row["repository_url"].removeprefix("https://github.com/")
            response = subprocess.run(
                ["gh", "api", f"repos/{repo}/commits/HEAD", "--jq", ".sha"],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            row["commit_sha"] = response.stdout.strip()
            if len(row["commit_sha"]) != 40 or any(c not in "0123456789abcdef" for c in row["commit_sha"]):
                raise ValueError("精确commit无效：" + row["name"])
        return row

    with ThreadPoolExecutor(max_workers=3) as pool:
        resolved = list(pool.map(head, projects))
    save(output / "resolved.json", dict(projects=resolved))
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(lambda item: collect_one(item, output), resolved))
    result = dict(projects=rows, provider_calls=0, automatic_retry=False)
    save(output / "source-index-final.json", result)
    for row in rows:
        print(row["name"], row["status"], row.get("error", ""), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(args.output.resolve())


if __name__ == "__main__":
    main()
