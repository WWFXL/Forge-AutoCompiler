#!/usr/bin/env python3
"""固定rtorrent依赖镜像与标准bootstrap输出；不构建项目，不调用模型。"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend/packages/harness")]
from forge_build_task_contract_sources import LIMITS, verify_archive, verify_recursive_tree  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

IDENTITY = "cpp-build-rtorrent-reference-preparation-v1"


def hashes(root):
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("本任务归档/生成阶段不接纳链接")
    return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file()}


def protected_unchanged(root, baseline):
    current = hashes(root)
    if any(current.get(p) != h for p, h in baseline.items()):
        raise ValueError("标准生成改写作者文件；不能放行")
    return current


def combined_archive(sources, target):
    """只移除codeload外层目录；依赖置于显式独立子目录，字节/模式保持。"""
    baseline = {}
    with tarfile.open(target, "x") as output:
        for source in sources:
            tree = json.loads(Path(source["tree"]).read_text())
            verify_recursive_tree(tree, source["tree_sha"])
            inspected, proof = verify_archive(Path(source["archive"]), tree, LIMITS)
            if proof["gitlinks"]:
                raise ValueError("来源还有未获取gitlink")
            prefix = inspected["archive_root"] + "/"
            with tarfile.open(source["archive"]) as original:
                for member in original:
                    if member.name.rstrip("/") == prefix.rstrip("/"):
                        continue
                    if member.issym() or member.islnk():
                        raise ValueError("本任务源归档不接纳链接")
                    adjusted = copy.copy(member)
                    adjusted.name = source["prefix"] + member.name[len(prefix) :]
                    adjusted.pax_headers = {}
                    if adjusted.name in baseline:
                        raise ValueError("两来源路径冲突")
                    output.addfile(adjusted, original.extractfile(member) if member.isfile() else None)
                    if member.isfile():
                        baseline[adjusted.name] = proof["file_index"][member.name[len(prefix) :]]["sha256"]
    return baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.protocol.read_text())
    if spec["identity"] != IDENTITY or spec["provider_calls"] != 0 or spec["build_commands"] != 0:
        raise ValueError("准备身份/边界变化")
    if (datetime.fromisoformat(spec["deadline_utc"].replace("Z", "+00:00")) - datetime.now(UTC)).total_seconds() < 900:
        raise ValueError("不足准备/清理预留")
    for name, h in spec["components"].items():
        if digest(ROOT / name) != h:
            raise ValueError("冻结组件变化")
    for parent in spec["parents"]:
        if audit(Path(parent["path"]))["inventory_canonical_sha256"] != parent["sha256"]:
            raise ValueError("父证据变化")
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", spec)
    write_json(root / "execution.json", {"release": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "provider_calls": 0, "build_commands": 0})
    result = {"identity": IDENTITY, "qualified": False, "task_qualified": False, "provider_calls": 0, "model_cost_usd": 0, "project_builds": 0, "cleanup": False}
    container = "forge-rtorrent-bootstrap-581"
    try:
        base_id = subprocess.check_output(["docker", "image", "inspect", "autocompiler:gcc13", "--format", "{{.Id}}"], text=True).strip()
        if base_id != spec["base_image_id"]:
            raise ValueError("依赖基础镜像漂移")
        subprocess.run(["docker", "tag", base_id, "forge-rtorrent-reference-base:581-d27a6ab733c7"], check=True, timeout=30)
        with (root / "environment-build.log").open("x") as log:
            subprocess.run(
                ["docker", "build", "--network=default", "--iidfile", str(root / "image-id"), "-f", str(ROOT / spec["dockerfile"]), str(ROOT / "benchmarks/recipes/rtorrent")], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600
            )
        image = (root / "image-id").read_text().strip()
        source = root / "source.tar"
        baseline = combined_archive(spec["sources"], source)
        write_json(root / "original-source-hashes.json", baseline)
        workspace = root / "bootstrap-workspace"
        workspace.mkdir()
        with tarfile.open(source) as handle:
            handle.extractall(workspace, filter="data")
        protected_unchanged(workspace, baseline)
        subprocess.run(
            [
                "docker",
                "create",
                "--name",
                container,
                "--network",
                "none",
                "--cpus",
                "2",
                "--memory",
                "8g",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--label",
                "forge.research=rtorrent-581",
                "-v",
                f"{workspace}:/workspace/repo",
                "-w",
                "/workspace/repo",
                "--entrypoint",
                "sleep",
                image,
                "infinity",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(["docker", "start", container], check=True, capture_output=True, timeout=30)
        with (root / "packages.tsv").open("x") as output:
            subprocess.run(["docker", "exec", container, "dpkg-query", "-W"], check=True, stdout=output, timeout=30)
        with (root / "toolchain.log").open("x") as output:
            subprocess.run(
                ["docker", "exec", container, "bash", "-c", "set -euo pipefail; g++ --version; autoreconf --version; automake --version; libtoolize --version; pkg-config --modversion cppunit libcurl openssl ncursesw zlib"],
                check=True,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=30,
            )
        generations = []
        before = hashes(workspace)
        for index, command in enumerate(spec["bootstrap_commands"]):
            with (root / f"bootstrap-{index + 1}.log").open("x") as output:
                subprocess.run(["docker", "exec", "-w", "/workspace/repo", container, "bash", "-c", "set -euo pipefail\n" + command], stdout=output, stderr=subprocess.STDOUT, check=True, timeout=180)
            after = protected_unchanged(workspace, baseline)
            # Autoconf cache为中间目录，不给原作者文件写权限；最终生成输出逐路径固定。
            changed = {p: h for p, h in after.items() if before.get(p) != h and "autom4te.cache/" not in p}
            if not changed:
                raise ValueError("bootstrap没有产生预期文件")
            generations.append(
                {
                    "command": command,
                    "workdir": "/workspace/repo",
                    "inputs": [p for p in baseline if p.endswith(("configure.ac", "Makefile.am", ".m4"))],
                    "outputs": changed,
                    "evidence": "独立标准bootstrap校准，两个原树/全部作者文件保持；原日志见bootstrap收据",
                }
            )
            before = after
        write_json(root / "generation-rules.json", generations)
        write_json(root / "generated-file-hashes.json", {p: h for p, h in before.items() if p not in baseline})
        result.update(
            qualified=True,
            image_id=image,
            source_archive_sha256=digest(source),
            baseline_files=len(baseline),
            bootstrap_generated_files=len(before) - len(baseline),
            author_files_unchanged=True,
            package_manifest_sha256=digest(root / "packages.tsv"),
        )
    except Exception as exc:
        result.update(error_class=type(exc).__name__, error=str(exc)[:1000])
    finally:
        removal = subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)
        absent = subprocess.run(["docker", "inspect", container], capture_output=True, timeout=30)
        result["cleanup"] = absent.returncode != 0 and (removal.returncode == 0 or b"No such container" in removal.stderr)
        write_json(root / "result.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        print(json.dumps(seal(root, spec, ROOT)), flush=True)
    return 0 if result["qualified"] and result["cleanup"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
