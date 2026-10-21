#!/usr/bin/env python3
"""精确生成输出清理/顺序重建资格；不授予作者文件删除权限。"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/packages/harness"), str(ROOT / "scripts")]
from forge_build_rtorrent_template_gate import task_boundary  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile.generated_file_boundary import FileBoundary, guarded_command  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import PlanContractError  # noqa: E402

IDENTITY = "cpp-build-rtorrent-bootstrap-reset-qualification-v1"


def reset_boundary(original):
    value = task_boundary(original).model_dump(mode="json")
    rules = value["generations"][:2]
    outputs = {p: h for r in rules for p, h in r["outputs"].items()}
    if len(outputs) != 40:
        raise PlanContractError("重置范围必须是原40生成输出")
    paths = " ".join(shlex.quote(p) for p in sorted(outputs))
    command = "rm -f -- " + paths + "\n(cd vendor-libtorrent && autoreconf -ivf)\nautoreconf -ivf"
    value["generations"].append(
        dict(command=command, workdir="/workspace/repo", inputs=sorted({p for r in rules for p in r["inputs"]}), outputs=outputs, evidence="本身份只清理原精确生成集合，再按完整参考的依赖→主项目顺序生成；保持原40最终SHA")
    )
    return FileBoundary.model_validate(value)


def reset_recovery(reference, boundary):
    from forge_build_rtorrent_template_gate import recovery_actions

    value = recovery_actions(reference)
    value["steps"] = [s for s in value["steps"] if s["step_id"] not in ("bootstrap-libtorrent", "bootstrap-rtorrent")]
    value["steps"].insert(
        1,
        dict(
            step_id="bootstrap-reset",
            role="dependency",
            command=boundary.generations[-1].command,
            source="仅清理任务40个声明生成输出；依赖优先完整重建",
            expected="818作者文件保持、40生成SHA恢复原值",
            requires=["cleanup-template"],
            workdir="/workspace/repo",
        ),
    )
    next(s for s in value["steps"] if s["step_id"] == "configure-libtorrent")["requires"] = ["bootstrap-reset"]
    value["reason"] = "仅脚本工程恢复：明确清理失败日志与全部声明生成输出，按依赖先、主项目后生成，原源码/测试/输出SHA不变。"
    return value


def validate(spec):
    if spec["identity"] != IDENTITY or spec["provider_calls"] != 0 or spec["credentials_read"] is not False or spec["max_model_cost_usd"] != 0:
        raise PlanContractError("零Provider身份变化")
    parent = Path(spec["reference_evidence"]["root"])
    if audit(parent)["inventory_canonical_sha256"] != spec["reference_evidence"]["inventory_sha256"]:
        raise PlanContractError("完整参考变化")
    original = json.loads((parent / "protocol.json").read_text())
    if spec["file_boundary"] != reset_boundary(original["file_boundary"]).model_dump(mode="json") or spec["image_id"] != original["plan"]["image_id"] or digest(Path(spec["source_archive"])) != original["plan"]["source_archive_sha256"]:
        raise PlanContractError("生成清理/重建、镜像或源变化")
    for p, h in spec["components"].items():
        if digest(ROOT / p) != h:
            raise PlanContractError("冻结组件变化：" + p)


def run_case(spec, root):
    folder = root / "root-first-reset"
    source = folder / "workspace"
    source.mkdir(parents=True)
    with tarfile.open(spec["source_archive"]) as archive:
        archive.extractall(source, filter="data")
    boundary = FileBoundary.model_validate(spec["file_boundary"])
    name = "forge-rtorrent-reset-" + uuid.uuid4().hex[:12]
    row = dict(qualified=False, container_name=name, commands=[], cleanup=False)
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
                "--user",
                f"{os.getuid()}:{os.getgid()}",
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
        for i, command in enumerate(("autoreconf -fi", boundary.generations[-1].command), 1):
            value = subprocess.run(["docker", "exec", name, "bash", "-c", "set -euo pipefail\n" + guarded_command(boundary, command, "/workspace/repo")], capture_output=True, text=True, timeout=180)
            (folder / f"command-{i}.log").write_text(value.stdout + value.stderr)
            row["commands"].append(dict(command=command, exit_code=value.returncode))
            if value.returncode:
                raise PlanContractError("生成顺序重建资格失败")
        if any(digest(source / p) != h for p, h in boundary.baseline.items()):
            raise PlanContractError("原作者文件变化")
        outputs = boundary.generations[-1].outputs
        if any(digest(source / p) != h for p, h in outputs.items()):
            raise PlanContractError("最终40输出SHA变化")
        row.update(qualified=True, author_files_unchanged=818, exact_generated_files=40)
    except Exception as exc:
        row.update(error_class=type(exc).__name__, error=str(exc)[:1500])
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=120)
        row["cleanup"] = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=30).returncode != 0
        row["qualified"] &= row["cleanup"]
        write_json(folder / "result.json", row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.protocol.read_text())
    validate(spec)
    before_deadline(spec["deadline_utc"], 600)
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", spec)
    write_json(root / "execution.json", dict(release=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()))
    row = run_case(spec, root)
    write_json(root / "result.json", dict(identity=IDENTITY, qualified=row["qualified"], rows=[row], provider_calls=0, full_build="not_observed"))
    print(json.dumps(seal(root, spec, ROOT)), flush=True)
    return 0 if row["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
