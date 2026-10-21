#!/usr/bin/env python3
"""独立核验Autotools生成参数形式；不构建、不调用模型，不改变旧任务。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.generated_file_boundary import FileBoundary, guarded_command  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402

IDENTITY = "cpp-build-rtorrent-bootstrap-alias-qualification-v1"


def alias_boundary(original):
    """精确预声明-fi两个调用；沿用同一40输出SHA，不扩大作者文件权限。"""
    value = copy.deepcopy(original)
    aliases = []
    for rule in value["generations"]:
        if rule["command"] not in ("cd vendor-libtorrent && autoreconf -ivf", "autoreconf -ivf"):
            raise ValueError("不是已固定的两条标准bootstrap")
        alternate = copy.deepcopy(rule)
        alternate["command"] = rule["command"].replace("-ivf", "-fi")
        aliases.append(alternate)
    if len(aliases) != 2:
        raise ValueError("必须有两个完整生成关系")
    value["generations"].extend(aliases)
    return FileBoundary.model_validate(value)


def validate(spec):
    if spec["identity"] != IDENTITY or spec["cases"] != ["fi", "ivf"] or spec["provider_calls"] != 0 or spec["credentials_read"] is not False:
        raise ValueError("固定资格身份/队列/零Provider边界变化")
    parent = Path(spec["parent_raw"])
    if audit(parent)["inventory_canonical_sha256"] != spec["parent_inventory_sha256"]:
        raise ValueError("参考父证据变化")
    original = json.loads((parent / "protocol.json").read_text())
    if spec["file_boundary"] != alias_boundary(original["file_boundary"]).model_dump(mode="json") or spec["image_id"] != original["plan"]["image_id"]:
        raise ValueError("生成范围或镜像变化")
    if digest(Path(spec["source_archive"])) != original["plan"]["source_archive_sha256"]:
        raise ValueError("固定源码归档变化")
    for name, expected in spec["components"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("冻结组件变化:" + name)


def run_case(spec, root, case):
    before_deadline(spec["deadline_utc"], 420)
    folder = root / case
    source = folder / "workspace"
    source.mkdir(parents=True)
    with tarfile.open(spec["source_archive"]) as archive:
        archive.extractall(source, filter="data")
    boundary = FileBoundary.model_validate(spec["file_boundary"])
    name = "forge-rtorrent-alias-" + uuid.uuid4().hex[:12]
    row = dict(case=case, qualified=False, container_name=name, commands=[], cleanup=False)
    try:
        created = subprocess.run(
            [
                "docker",
                "create",
                "--name",
                name,
                "--network",
                "none",
                "--cpus",
                "2",
                "--label",
                "forge.research.identity=" + IDENTITY,
                "--mount",
                f"type=bind,src={source},dst=/workspace/repo",
                "--workdir",
                "/workspace/repo",
                "--entrypoint",
                "/bin/bash",
                spec["image_id"],
                "-c",
                "sleep infinity",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        row["container_id"] = created.stdout.strip()
        subprocess.run(["docker", "start", name], capture_output=True, check=True, timeout=30)
        inspected = json.loads(subprocess.check_output(["docker", "inspect", name], text=True))[0]
        assert inspected["Image"] == spec["image_id"] and inspected["HostConfig"]["NetworkMode"] == "none" and inspected["HostConfig"]["NanoCpus"] == 2_000_000_000
        row["runtime"] = dict(image_id=inspected["Image"], network="none", nano_cpus=inspected["HostConfig"]["NanoCpus"])
        for index, template in enumerate(("cd vendor-libtorrent && autoreconf -FLAG", "autoreconf -FLAG"), 1):
            command = template.replace("FLAG", case)
            wrapped = guarded_command(boundary, command, "/workspace/repo")
            try:
                result = subprocess.run(["docker", "exec", name, "bash", "-c", "set -euo pipefail\n" + wrapped], capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired as exc:
                partial = (exc.stdout or b"") + (exc.stderr or b"")
                (folder / f"command-{index}.log").write_bytes(partial)
                row["commands"].append(dict(command=command, exit_code=None, timed_out=True, log=f"command-{index}.log"))
                raise
            (folder / f"command-{index}.log").write_text(result.stdout + result.stderr)
            row["commands"].append(dict(command=command, exit_code=result.returncode, log=f"command-{index}.log"))
            if result.returncode != 0:
                raise ValueError("标准生成命令未满足同一原文件/生成SHA合同")
        for name, expected in boundary.baseline.items():
            if digest(source / name) != expected:
                raise ValueError("原作者文件被改写")
        outputs = {p: h for r in boundary.generations for p, h in r.outputs.items()}
        if len(outputs) != 40 or any(digest(source / p) != expected for p, expected in outputs.items()):
            raise ValueError("40标准输出并非参考中的精确内容")
        row.update(qualified=True, author_files_unchanged=818, exact_generated_files=len(outputs), output_hashes=outputs)
    except Exception as exc:
        row.update(error_class=type(exc).__name__, error=str(exc)[:1200])
    finally:
        # 名称来自本次创建，失败也只清理该资格容器，不触碰其他服务。
        identifier = row["container_name"]
        removed = subprocess.run(["docker", "rm", "-f", identifier], capture_output=True, timeout=120)
        absent = subprocess.run(["docker", "inspect", identifier], capture_output=True, timeout=30).returncode != 0
        row["cleanup"] = absent and (removed.returncode == 0 or "container_id" not in row)
        row["qualified"] = row["qualified"] and row["cleanup"]
        write_json(folder / "result.json", row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.protocol.read_text())
    validate(spec)
    before_deadline(spec["deadline_utc"], 420)
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", spec)
    write_json(root / "execution.json", dict(release=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()))
    rows = []
    try:
        for case in spec["cases"]:
            row = run_case(spec, root, case)
            rows.append(row)
            if not row["qualified"]:
                break
    finally:
        write_json(
            root / "result.json",
            dict(
                identity=IDENTITY,
                rows=rows,
                unobserved=spec["cases"][len(rows) :],
                qualified=len(rows) == 2 and all(r["qualified"] for r in rows),
                provider_calls=0,
                scope="仅标准生成输出等价资格；未运行构建/作者测试/交付/replay；不回填旧门禁或真实方法效果",
            ),
        )
        print(json.dumps(seal(root, spec, ROOT)), flush=True)
    return 0 if len(rows) == 2 and all(r["qualified"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
