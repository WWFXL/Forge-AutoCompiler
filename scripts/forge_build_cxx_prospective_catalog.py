#!/usr/bin/env python3
"""前瞻固定来源目录；只读GitHub元数据和根树，不读取源码或运行构建。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from forge_typed_evidence import digest, seal, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-cxx-prospective-source-catalog-v1"
QUERY = "language:C++ archived:false fork:false stars:500..5000"
LIMIT = 30


def before_deadline(protocol):
    deadline = datetime.fromisoformat(protocol["deadline_utc"].replace("Z", "+00:00"))
    if (deadline - datetime.now(timezone.utc)).total_seconds() < 60:
        raise ValueError("原绝对截止前预留60秒封存，停止新元数据请求")


def validate(protocol):
    if (
        protocol["identity"] != IDENTITY
        or protocol["query"] != QUERY
        or protocol["limit"] != LIMIT
    ):
        raise ValueError("来源目录身份或固定检索框变化")
    if (
        protocol["deadline_utc"] != "2026-10-20T22:07:35Z"
        or any(
            protocol[k] != 0
            for k in (
                "provider_calls",
                "model_cost_usd",
                "build_commands",
                "docker_calls",
            )
        )
        or protocol["credentials_read"] is not False
    ):
        raise ValueError("零Provider/源码执行/费用或原窗口变化")
    for name, sha in protocol["components"].items():
        if digest(REPO_ROOT / name) != sha:
            raise ValueError("来源目录组件变化")
    before_deadline(protocol)


def search_items(response):
    items = response["items"]
    if (
        response["incomplete_results"]
        or len(items) != LIMIT
        or len({x["id"] for x in items}) != LIMIT
        or len({x["full_name"].casefold() for x in items}) != LIMIT
    ):
        raise ValueError("检索未完整取得固定30项或出现重复；不补页替换")
    if any(
        x["language"] != "C++"
        or x["archived"]
        or x["fork"]
        or not 500 <= x["stargazers_count"] <= 5000
        for x in items
    ):
        raise ValueError("检索元数据与前瞻条件不符")
    if [x["stargazers_count"] for x in items] != sorted(
        (x["stargazers_count"] for x in items), reverse=True
    ):
        raise ValueError("固定stars降序变化")
    return items


def root_signals(tree):
    entries = tree["tree"]
    if tree.get("truncated") or len({x["path"] for x in entries}) != len(entries):
        raise ValueError("根树不完整或路径重复")
    names = {
        x["path"]
        for x in entries
        if x["type"] == "blob" and x["mode"] in ("100644", "100755")
    }
    systems = []
    for system, markers in (
        ("cmake", {"CMakeLists.txt"}),
        ("make", {"Makefile", "makefile", "GNUmakefile"}),
        ("autotools", {"configure.ac", "configure.in", "configure"}),
        ("meson", {"meson.build"}),
    ):
        if names & markers:
            systems.append(system)
    return dict(
        root_entry_names=sorted(x["path"] for x in entries),
        candidate_build_systems=systems,
        task_qualified=False,
        linux_target_applicability="not_observed",
        build_result="not_observed",
        holdout=False,
    )


def api(arguments, output, protocol):
    before_deadline(protocol)
    result = subprocess.run(["gh", "api", *arguments], capture_output=True, timeout=25)
    if result.returncode:
        write_json(
            output.with_suffix(".failure.json"),
            dict(
                exit_code=result.returncode,
                stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),
                stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
            ),
        )
        raise ValueError("GitHub元数据请求失败；不重试、不补槽")
    output.write_bytes(result.stdout)
    return json.loads(result.stdout)


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
    paths = (
        subprocess.run(
            ["git", "ls-files", "-z", "benchmarks", "docs/research"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            timeout=20,
        )
        .stdout.decode()
        .split("\0")[:-1]
    )
    texts = [
        (name, (REPO_ROOT / name).read_text(errors="replace"))
        for name in paths
        if (REPO_ROOT / name).is_file()
    ]
    write_json(
        root / "exposure-scan-scope.json",
        dict(
            release=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
            ).strip(),
            files={name: digest(REPO_ROOT / name) for name, _ in texts},
            scope="当前跟踪benchmarks/docs/research精确owner/name；不证明全部历史、训练或外部未见",
        ),
    )
    rows = []
    items = []
    reason = None
    try:
        response = api(
            [
                "-X",
                "GET",
                "search/repositories",
                "-f",
                "q=" + QUERY,
                "-f",
                "sort=stars",
                "-f",
                "order=desc",
                "-f",
                "per_page=30",
                "-f",
                "page=1",
            ],
            root / "search-response.json",
            protocol,
        )
        items = search_items(response)
        write_json(
            root / "frozen-ranks.json",
            [
                dict(
                    rank=i + 1,
                    repository=x["full_name"],
                    repository_id=x["id"],
                    stars=x["stargazers_count"],
                )
                for i, x in enumerate(items)
            ],
        )
        for rank, item in enumerate(items, 1):
            try:
                before_deadline(protocol)
            except ValueError:
                reason = "deadline_reservation"
                break
            folder = root / f"{rank:02d}"
            folder.mkdir()
            row = dict(
                rank=rank,
                repository=item["full_name"],
                repository_id=item["id"],
                stars=item["stargazers_count"],
                role="source_only_future_candidate",
                current_tracked_exact_name_matches=[
                    n for n, t in texts if item["full_name"].casefold() in t.casefold()
                ],
                holdout=False,
            )
            try:
                owner = item["full_name"]
                branch = quote(item["default_branch"], safe="")
                commit = api(
                    [f"repos/{owner}/commits/{branch}"],
                    folder / "commit.json",
                    protocol,
                )
                sha = commit["sha"]
                tree_sha = commit["commit"]["tree"]["sha"]
                if not re.fullmatch("[0-9a-f]{40}", sha) or not re.fullmatch(
                    "[0-9a-f]{40}", tree_sha
                ):
                    raise ValueError("缺少精确commit/tree身份")
                tree = api(
                    [f"repos/{owner}/git/trees/{tree_sha}"],
                    folder / "root-tree.json",
                    protocol,
                )
                if tree["sha"] != tree_sha:
                    raise ValueError("根tree身份不符")
                row.update(
                    status="metadata_observed",
                    commit_sha=sha,
                    root_tree_sha=tree_sha,
                    **root_signals(tree),
                )
            except (ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                row.update(
                    status="metadata_failed",
                    error_class=type(exc).__name__,
                    task_qualified=False,
                    build_result="not_observed",
                )
            rows.append(row)
    except (ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        reason = type(exc).__name__
    finally:
        unseen = [
            dict(
                rank=i + 1,
                repository=x["full_name"],
                status="not_observed",
                reason=reason,
            )
            for i, x in enumerate(items)
            if i >= len(rows)
        ]
        write_json(
            root / "result.json",
            dict(
                identity=IDENTITY,
                kind="prospective_metadata_catalog_not_build_qualification",
                provider_calls=0,
                model_cost_usd=0,
                build_commands=0,
                docker_calls=0,
                rows=rows,
                not_observed=unseen,
                stop_reason=reason,
            ),
        )
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(rows) == LIMIT and reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
