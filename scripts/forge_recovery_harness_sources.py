#!/usr/bin/env python3
"""固定18个论文来源新项目：只读采集及独立主目标装配，不调用模型。"""

from __future__ import annotations

import argparse
import json
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from forge_build_reference_expansion import normalized_source
from forge_build_simple_task import save
from forge_build_source_expansion import download
from forge_simple_system import ROOT
from forge_typed_evidence import digest

from deerflow.compile.plan_workflow import _digest
from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask

POOL = ROOT / "benchmarks/fixtures/recovery-harness-proposal-v1/project-pool.json"
FIXTURE = ROOT / "benchmarks/fixtures/recovery-harness-comparison-v1/tasks.json"
LIMITS = dict(max_entries=50000, max_file_bytes=64 * 1024**2, max_uncompressed_bytes=512 * 1024**2, snippet_bytes=16000)


def collect_one(item, output):
    folder = output / item["name"]
    folder.mkdir()
    result = dict(name=item["name"], commit_sha=item["commit_sha"], status="started")
    try:
        repository = item["repository_url"].removeprefix("https://github.com/")
        compressed = folder / "original.tar.gz"
        download(f"https://codeload.github.com/{repository}/tar.gz/{item['commit_sha']}", compressed, 64 * 1024**2)
        archive = folder / "source.tar"
        hashes = normalized_source(compressed, archive, LIMITS)
        source = folder / "source"
        source.mkdir()
        with tarfile.open(archive) as handle:
            handle.extractall(source, filter="data")
        save(folder / "source-file-hashes.json", hashes)
        result.update(status="collected", source_archive=str(archive), source_archive_sha256=digest(archive), compressed_sha256=digest(compressed), source_root=str(source), original_files=len(hashes))
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
    save(folder / "result.json", result)
    return result


def collect(output):
    output.mkdir(parents=True, exist_ok=False)
    pool = json.loads(POOL.read_text())
    save(
        output / "scope.json",
        dict(
            identity="cpp-build-recovery-harness-source-preparation-v1",
            kind="zero_provider_source_preparation",
            authorization="用户已审核R1并要求开始比较实现；只读源码采集",
            provider_calls=0,
            maximum_cost_usd="0",
            retry=False,
            project_pool_sha256=digest(POOL),
            projects=pool["proposed_evaluation"],
        ),
    )
    rows = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(collect_one, p, output): p for p in pool["proposed_evaluation"]}
        for future in as_completed(futures):
            row = future.result()
            rows[row["name"]] = row
            print(row["name"], row["status"], flush=True)
    result = dict(projects=[rows[p["name"]] for p in pool["proposed_evaluation"]], provider_calls=0, automatic_retry=False)
    save(output / "result.json", result)
    return result


def freeze(sources, definitions, image_id):
    """独立定义来自作者声明；参考命令和产物名单不进入模型任务。"""
    if FIXTURE.exists():
        raise ValueError("不覆盖已固定任务；修订须新身份")
    pool = json.loads(POOL.read_text())["proposed_evaluation"]
    collected = {r["name"]: r for r in json.loads((sources / "result.json").read_text())["projects"]}
    authored = json.loads(definitions.read_text())
    if set(authored) != {p["name"] for p in pool}:
        raise ValueError("独立定义须保留原18个候选，不按方法结果换项目")
    projects = []
    for p in pool:
        row, definition = collected[p["name"]], authored[p["name"]]
        if row["status"] != "collected" or digest(Path(row["source_archive"])) != row["source_archive_sha256"]:
            raise ValueError("来源未完整采集：" + p["name"])
        root = Path(row["source_root"])
        evidence = []
        for item in definition["source_evidence"]:
            path = root / item["path"]
            if not path.resolve().is_relative_to(root.resolve()) or item["quote"] not in path.read_text(errors="replace"):
                raise ValueError("作者声明引用不匹配：" + p["name"])
            evidence.append(item | dict(sha256=digest(path)))
        task = PublicBuildTask(
            task_version="main-build-v1",
            plan_id="recovery-" + p["name"].lower(),
            repository_url=p["repository_url"],
            commit_sha=p["commit_sha"],
            image_id=image_id,
            source_archive_sha256=row["source_archive_sha256"],
            build_system=p["proposed_build_system"],
        )
        reference = BuildReference(
            task_sha256=_digest(task.model_dump(mode="json")),
            components=definition["components"],
            executable_smokes=definition.get("executable_smokes", []),
            tests_not_applicable_reason="main-build-v1不要求完整作者测试；轻量验证及干净重放另列",
        )
        projects.append(
            dict(
                name=p["name"],
                family=p["repository_url"].lower(),
                task=task.model_dump(mode="json"),
                reference=reference.model_dump(mode="json"),
                source_archive=row["source_archive"],
                source_evidence=evidence,
                reference_actions=definition["reference_actions"],
                paper_sources=p["sources"],
                exposure="新论文来源开发项目；只读准备暴露，非最终holdout；未送优化器",
            )
        )
    result = dict(
        identity="cpp-build-recovery-harness-comparison-fixture-v1",
        project_pool_sha256=digest(POOL),
        source_collection=str(sources),
        definition_sha256=digest(definitions),
        projects=projects,
        boundary="保留全部18候选；作者普通主目标；不依据方法成绩筛选；独立参考不送模型",
    )
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    save(FIXTURE, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--collect", type=Path)
    group.add_argument("--freeze", action="store_true")
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--definitions", type=Path)
    parser.add_argument("--image-id")
    args = parser.parse_args()
    if args.collect:
        collect(args.collect.resolve())
    else:
        if not all((args.sources, args.definitions, args.image_id)):
            parser.error("固定任务需要--sources、--definitions和--image-id")
        result = freeze(args.sources.resolve(), args.definitions, args.image_id)
        print(json.dumps(dict(projects=len(result["projects"]), fixture_sha256=digest(FIXTURE), provider_calls=0)))


if __name__ == "__main__":
    main()
