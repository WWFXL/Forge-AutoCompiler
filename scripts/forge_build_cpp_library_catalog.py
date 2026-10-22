#!/usr/bin/env python3
"""固定C++库检索框，仅采集不带patch的Git对象元数据。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

from forge_build_cxx_prospective_catalog import api, before_deadline, root_signals
from forge_typed_evidence import digest, seal, write_json

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-cpp-library-source-catalog-v1"
QUERY = "language:C++ archived:false fork:false topic:cpp-library stars:100..5000"
LIMIT = 20
DEADLINE = "2026-10-22T19:37:37+00:00"


def name_matches(repository, text):
    pattern = r"(?<![\w.-])" + re.escape(repository) + r"(?:\.git)?(?![\w.-])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def fixed_items(response):
    items = response["items"]
    if response["incomplete_results"] or len(items) != LIMIT:
        raise ValueError("检索不足固定20项，不翻页或补位")
    if (
        len({x["id"] for x in items}) != LIMIT
        or len({x["full_name"].casefold() for x in items}) != LIMIT
    ):
        raise ValueError("固定目录重复")
    if any(
        x["language"] != "C++"
        or x["archived"]
        or x["fork"]
        or not 100 <= x["stargazers_count"] <= 5000
        or "cpp-library" not in x["topics"]
        or not re.fullmatch(r"[\w.-]+/[\w.-]+", x["full_name"])
        for x in items
    ):
        raise ValueError("检索结果不符合预定义范围")
    if [x["stargazers_count"] for x in items] != sorted(
        (x["stargazers_count"] for x in items), reverse=True
    ):
        raise ValueError("星数顺序变化")
    return items


def metadata(item, folder, protocol):
    owner = item["full_name"]
    branch = quote(item["default_branch"], safe="")
    ref = api([f"repos/{owner}/git/ref/heads/{branch}"], folder / "ref.json", protocol)
    sha = ref["object"]["sha"]
    if ref["object"]["type"] != "commit" or not re.fullmatch("[0-9a-f]{40}", sha):
        raise ValueError("默认分支不指向精确commit")
    # Git对象接口没有patch，避免旧commits接口附带源码差异。
    commit = api(
        [f"repos/{owner}/git/commits/{sha}"], folder / "git-commit.json", protocol
    )
    tree_sha = commit["tree"]["sha"]
    if (
        commit["sha"] != sha
        or "files" in commit
        or not re.fullmatch("[0-9a-f]{40}", tree_sha)
    ):
        raise ValueError("Git commit/tree身份或无patch约定不符")
    tree = api(
        [f"repos/{owner}/git/trees/{tree_sha}"], folder / "root-tree.json", protocol
    )
    if tree["sha"] != tree_sha:
        raise ValueError("根tree身份不符")
    return dict(commit_sha=sha, root_tree_sha=tree_sha, **root_signals(tree))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if (
        protocol["identity"] != IDENTITY
        or protocol["query"] != QUERY
        or protocol["limit"] != LIMIT
        or protocol["deadline_utc"] != DEADLINE
    ):
        raise ValueError("身份/检索框/原共享时窗变化")
    if (
        any(
            protocol[k] != 0
            for k in (
                "provider_calls",
                "model_cost_usd",
                "build_commands",
                "docker_calls",
            )
        )
        or protocol["provider_credentials_read"] is not False
    ):
        raise ValueError("不允许模型调用、模型凭据或源码执行")
    for name, expected in protocol["components"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("冻结组件变化")
    before_deadline(protocol)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "benchmarks", "docs/research"], cwd=ROOT
        )
        .decode()
        .split("\0")[:-1]
    )
    texts = {
        n: (ROOT / n).read_text(errors="replace") for n in names if (ROOT / n).is_file()
    }
    write_json(
        root / "exposure-scan-scope.json",
        dict(
            release=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            files={n: digest(ROOT / n) for n in texts},
            scope="当前跟踪benchmarks/docs/research精确owner/name；不是全部历史/训练未见性证明",
        ),
    )
    rows, items, reason = [], [], None
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
                "per_page=20",
                "-f",
                "page=1",
            ],
            root / "search-response.json",
            protocol,
        )
        items = fixed_items(response)
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
                role="source_metadata_only",
                task_qualified=False,
                holdout=False,
                build_result="not_observed",
                current_tracked_exact_name_matches=[
                    n
                    for n, text in texts.items()
                    if name_matches(item["full_name"], text)
                ],
            )
            try:
                row.update(metadata(item, folder, protocol), status="metadata_observed")
            except (ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                row.update(
                    status="metadata_failed",
                    error_class=type(exc).__name__,
                    error_message=str(exc),
                )
            write_json(folder / "result.json", row)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    except (ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        reason = type(exc).__name__ + ": " + str(exc)
    finally:
        write_json(
            root / "result.json",
            dict(
                identity=IDENTITY,
                rows=rows,
                not_observed=LIMIT - len(rows),
                frozen_ranks_observed=len(items),
                stop_reason=reason,
                provider_calls=0,
                model_cost_usd=0,
                provider_credentials_read=False,
                build_commands=0,
                docker_calls=0,
            ),
        )
        seal(root, protocol, ROOT, 0)
    return 0 if len(rows) == LIMIT else 1


if __name__ == "__main__":
    raise SystemExit(main())
