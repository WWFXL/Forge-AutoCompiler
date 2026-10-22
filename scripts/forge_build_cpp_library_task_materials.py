#!/usr/bin/env python3
"""沿固定20项来源采集原合同材料；不执行上游或授予构建资格。"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import forge_build_task_source_screen as source
from forge_typed_evidence import digest, seal, write_json

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-cpp-library-task-materials-v1"
RULES = dict(
    root_names=list(source.ROOT_NAMES),
    child_names=list(source.CHILD_NAMES),
    subtrees=list(source.SUBTREES),
    max_blob_bytes=source.MAX_BLOB_BYTES,
    max_blobs_per_repository=source.MAX_BLOBS,
    max_workflows=4,
)


def validate(protocol):
    if (
        protocol["identity"] != IDENTITY
        or protocol["rules"] != RULES
        or protocol["deadline_utc"] != "2026-10-22T19:37:37+00:00"
    ):
        raise ValueError("身份、原材料规则或共享截止变化")
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
        raise ValueError("零模型/执行边界变化")
    parent = Path(protocol["parent_raw"])
    for name, expected in protocol["parent_files"].items():
        if digest(parent / name) != expected:
            raise ValueError("父来源冻结材料改变:" + name)
    result = json.loads((parent / "result.json").read_text())
    rows = result["rows"]
    if (
        result["identity"] != "cpp-build-cpp-library-source-catalog-v1"
        or [r["rank"] for r in rows] != list(range(1, 21))
        or rows != protocol["candidates"]
    ):
        raise ValueError("固定20项分母、排名或完整身份变化，不补位")
    if any(
        r["status"] != "metadata_observed" or r["task_qualified"] is not False
        for r in rows
    ):
        raise ValueError("父元数据状态或未资格角色变化")
    for name, expected in protocol["components"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("冻结组件改变:" + name)
    return parent, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    parent, candidates = validate(protocol)
    source.before_request(protocol)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    write_json(
        root / "execution.json",
        dict(
            release=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            identity=IDENTITY,
            provider_calls=0,
            upstream_execution=False,
        ),
    )
    rows, reason = [], None
    try:
        for candidate in candidates:
            try:
                source.before_request(protocol)
            except TimeoutError:
                reason = "deadline_reservation"
                break
            folder = root / f"{candidate['rank']:02d}"
            folder.mkdir()
            row = {
                **candidate,
                "role": "source_contract_review_only",
                "task_qualified": False,
                "build_result": "not_observed",
                "holdout": False,
            }
            try:
                row.update(
                    **source.collect(candidate, parent, folder, protocol),
                    source_material_status="observed",
                )
            except (
                ValueError,
                KeyError,
                UnicodeError,
                subprocess.TimeoutExpired,
                TimeoutError,
            ) as exc:
                row.update(
                    source_material_status="failed",
                    error_class=type(exc).__name__,
                    error_message=str(exc)[:300],
                )
            write_json(folder / "result.json", row)
            rows.append(row)
            print(
                json.dumps(
                    dict(
                        rank=row["rank"],
                        repository=row["repository"],
                        status=row["source_material_status"],
                        files=len(row.get("materials", [])),
                    )
                ),
                flush=True,
            )
    finally:
        write_json(
            root / "result.json",
            dict(
                identity=IDENTITY,
                rows=rows,
                unobserved=candidates[len(rows) :],
                stop_reason=reason,
                provider_calls=0,
                model_cost_usd=0,
                provider_credentials_read=False,
                build_commands=0,
                docker_calls=0,
            ),
        )
        print(json.dumps(seal(root, protocol, ROOT)), flush=True)
    return (
        0
        if len(rows) == 20
        and all(r["source_material_status"] == "observed" for r in rows)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
