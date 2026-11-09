#!/usr/bin/env python3
"""从三篇论文原始清单整理项目池；仅查元数据，不执行构建或选择模型成功样本。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PAPERS = {
    "compileagent": ("https://arxiv.org/html/2505.04254v1", ["A3.T4"]),
    "buildbench": ("https://arxiv.org/html/2509.25248v2", ["A9.T7", "A9.T8", "A9.T9"]),
    "cxxcrafter": ("https://arxiv.org/html/2505.21069v1", ["S2.T1"]),
}
# 根据论文项目身份与构建系统多样性提出，未看任何新模型结果。
PROPOSED = (
    ("cglm", "recp/cglm", "cmake"),
    ("tini", "krallin/tini", "cmake"),
    ("wasm3", "wasm3/wasm3", "cmake"),
    ("libhv", "ithewei/libhv", "cmake"),
    ("ggmorse", "ggerganov/ggmorse", "cmake"),
    ("DuckX", "amiremohamadi/DuckX", "cmake"),
    ("massdns", "blechschmidt/massdns", "make"),
    ("redsocks", "darkk/redsocks", "make"),
    ("beanstalkd", "beanstalkd/beanstalkd", "make"),
    ("no-more-secrets", "bartobri/no-more-secrets", "make"),
    ("berkeley-softfloat-3", "ucb-bar/berkeley-softfloat-3", "make"),
    ("Turbo-Base64", "powturbo/Turbo-Base64", "make"),
    ("libmodbus", "stephane/libmodbus", "autotools"),
    ("freesasa", "mittinatten/freesasa", "autotools"),
    ("fsarchiver", "fdupoux/fsarchiver", "autotools"),
    ("fastq-tools", "dcjones/fastq-tools", "autotools"),
    ("munge", "dun/munge", "autotools"),
    ("twemproxy", "twitter/twemproxy", "autotools"),
)


def normalized(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def extract(paper, path):
    soup = BeautifulSoup(path.read_text(), "html.parser")
    url, ids = PAPERS[paper]
    result = []
    for identifier in ids:
        table = soup.find(id=identifier)
        if table is None:
            raise ValueError("论文表格缺失：" + identifier)
        for row_index, row in enumerate(table.select("tr"), 1):
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td", recursive=False)]
            groups = []
            if paper == "compileagent" and len(cells) == 10:
                groups = [cells[:5], cells[5:]]
            elif paper == "buildbench" and len(cells) == 5 and cells[0]:
                groups = [cells]
            elif paper == "cxxcrafter" and len(cells) == 2:
                groups = [[n.strip(), cells[0]] for n in cells[1].split(",") if n.strip()]
            for group in groups:
                guide = None
                if len(group) == 5:
                    guide = next((label for label, cell in zip(("in_repo", "outside_repo", "no_guide"), group[2:]) if "✓" in cell), "unresolved")
                result.append(dict(name=group[0], topic=group[1], guide=guide, source=paper, source_url=url + "#" + identifier, row=row_index, source_html_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return result


def historic_exposure():
    names, urls = {}, {}

    def walk(obj, path):
        if isinstance(obj, dict):
            url = obj.get("repository_url")
            if isinstance(url, str) and "github.com/" in url:
                canonical = url.lower().rstrip("/").removesuffix(".git")
                urls.setdefault(canonical, set()).add(path)
                names.setdefault(normalized(canonical.rsplit("/", 1)[-1]), set()).add(path)
            for key, value in obj.items():
                if key in {"projects", "evaluation_projects", "training_projects"} and isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            names.setdefault(normalized(item), set()).add(path)
                        elif isinstance(item, dict) and isinstance(item.get("name"), str):
                            names.setdefault(normalized(item["name"]), set()).add(path)
                walk(value, path)
        elif isinstance(obj, list):
            for value in obj:
                walk(value, path)

    for directory in ("benchmarks/manifests", "benchmarks/fixtures"):
        for path in sorted((ROOT / directory).rglob("*.json")):
            walk(json.loads(path.read_text()), str(path.relative_to(ROOT)))
    return names, urls


def github(path):
    result = subprocess.run(["gh", "api", path], check=True, text=True, capture_output=True, timeout=40)
    return json.loads(result.stdout)


def resolve_candidate(item):
    name, repository, system = item
    try:
        commit = github(f"repos/{repository}/commits/HEAD")
        tree = github(f"repos/{repository}/git/trees/{commit['commit']['tree']['sha']}")
        names = [e["path"] for e in tree["tree"]]
        return dict(name=name, repository_url=commit["html_url"].split("/commit/")[0], commit_sha=commit["sha"], root_tree_sha=tree["sha"], proposed_build_system=system, root_entries=names, resolved=True, build_run=False)
    except subprocess.SubprocessError:
        return dict(name=name, repository_url="https://github.com/" + repository, proposed_build_system=system, resolved=False, reason="metadata_lookup_failed", build_run=False)


def build(paper_directory, output):
    rows = [row for paper in PAPERS for row in extract(paper, paper_directory / (paper + ".html"))]
    names, urls = historic_exposure()
    merged = {}
    for row in rows:
        key = normalized(row["name"])
        merged.setdefault(key, dict(name=row["name"], name_key=key, sources=[]))["sources"].append(row)
    for key, value in merged.items():
        value["historical_exposure_pointers"] = sorted(names.get(key, ()))
        value["identity_resolution"] = "name_dedup_only_until_repository_resolved"
    with ThreadPoolExecutor(max_workers=4) as pool:
        candidates = list(pool.map(resolve_candidate, PROPOSED))
    for row in candidates:
        key = normalized(row["name"])
        if key not in merged:
            raise ValueError("候选没有论文清单来源：" + row["name"])
        source = merged[key]
        row["sources"] = source["sources"]
        row["historical_exposure_pointers"] = sorted(set(source["historical_exposure_pointers"]) | urls.get(row["repository_url"].lower(), set()))
        row["selection_status"] = "prior_exposure_exclude_from_new_set" if row["historical_exposure_pointers"] else "new_candidate_pending_user_review"
        row["root_entry_matches_system"] = {
            "cmake": "CMakeLists.txt" in row.get("root_entries", []),
            "make": any(n.lower() in {"makefile", "gnumakefile"} for n in row.get("root_entries", [])),
            "autotools": any(n in {"configure.ac", "configure.in"} for n in row.get("root_entries", [])),
        }[row["proposed_build_system"]]
        # SoftFloat的作者入口在build平台目录；只记录，当前不读取源码或实建。
        if row["name"] == "berkeley-softfloat-3":
            row["entry_note"] = "作者Make入口位于build下平台目录，根目录无Makefile；后续固定任务时确认。"
    result = dict(
        format="paper-source-project-pool-v1",
        purpose="development_candidates_not_final_holdout",
        model_runs=0,
        source_counts=dict(Counter(r["source"] for r in rows)),
        raw_entries=len(rows),
        normalized_name_groups=len(merged),
        dedup_boundary="名称规范化仅初步去重，可能仍有别名/同名不同仓库；18候选另核验仓库URL。不得把总名称数称独立仓库数。",
        source_discrepancy="BUILD-BENCH v2正文148测试项目，但附录表7—9实际提取149条名称；原样保留，不能把该清单称已完整复现的148项目官方数据包。CXX仅Top100表，不冒称包含全部Awesome-CPP。",
        exposure_boundary="已扫描当前仓库全部版本化manifest/fixture；无命中不等于模型训练未见，也不保证未在未登记手工工作中出现。新增候选仍须与来源项目按仓库族隔离。",
        projects=list(merged.values()),
        proposed_evaluation=candidates,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.papers, args.output)
    print(json.dumps({k: result[k] for k in ("source_counts", "raw_entries", "normalized_name_groups")}, ensure_ascii=False))
    print(json.dumps([dict(name=r["name"], resolved=r["resolved"], selection_status=r["selection_status"], root_entry_matches_system=r["root_entry_matches_system"]) for r in result["proposed_evaluation"]], ensure_ascii=False))
