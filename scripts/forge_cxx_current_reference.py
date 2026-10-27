#!/usr/bin/env python3
"""以当前社区版原生Dockerfile闭环作阶段性参考，不冒充论文原版或最终排名。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import forge_build_flash_paper_experiments as flash
import forge_build_strategy_replication as replication
from forge_typed_evidence import seal

from deerflow.compile.plan_delivery_equivalent import equivalent_delivery_command
from deerflow.compile.operations import _classify_artifact

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-current-cxx-reference-flash-v1"
BASELINE = Path("/home/yiwei/work/CXXCrafter-Community-Edition")
SESSION = Path(
    "/home/yiwei/.codex/outputs/forge-cxx-current-reference-session-2026-10-27"
)
OUTPUT = SESSION.parent / "forge-cxx-current-reference-v1"
MANIFEST = ROOT / "benchmarks/manifests" / (IDENTITY + ".json")
PARENT = ROOT / "benchmarks/manifests/cpp-build-strategy-replication-v1.json"
PREREGISTRATION = (
    "benchmarks/preregistrations/cpp-build-current-cxx-reference-flash-v1.md"
)
DEADLINE = "2026-10-27T12:44:30+00:00"
PRIOR_COST = Decimal("0.4366236")
STAGE_CAP = Decimal("4.00")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def remaining():
    return (datetime.fromisoformat(DEADLINE) - datetime.now(UTC)).total_seconds()


class StopPaid(RuntimeError):
    """未知用量、身份或费用边界阻止后续付费。"""


class SDKMeter:
    def __init__(self, folder, available):
        self.folder = folder
        self.folder.mkdir(parents=True)
        self.available = Decimal(str(available))
        self.cost = Decimal(0)
        self.requests = self.input = self.output = self.unknown = 0
        self.stopped = False

    def request(self, call, kwargs):
        if self.stopped or remaining() < 900:
            raise StopPaid("付费停止或请求时间不足")
        kwargs = {
            **kwargs,
            "model": "deepseek-flash",
            "max_tokens": 32768,
            "reasoning_effort": "low",
            "extra_body": {"thinking": {"type": "enabled"}},
        }
        reserve = (
            Decimal(len(json.dumps(kwargs).encode()) + 8192) * Decimal("0.30")
            + Decimal(32768) * Decimal("1.20")
        ) / 1_000_000
        if self.cost + reserve > self.available:
            raise StopPaid("请求前费用上界不足")
        self.requests += 1
        stem = self.folder / f"request-{self.requests:03d}"
        save(stem.with_suffix(".json"), kwargs)
        try:
            response = call(**kwargs)
        except Exception:
            self.unknown += 1
            self.stopped = True
            save(stem.with_suffix(".failure.json"), {"unknown_usage": True})
            raise
        save(stem.with_suffix(".response.json"), response.model_dump(mode="json"))
        usage = response.usage
        if (
            usage is None
            or usage.prompt_tokens is None
            or usage.completion_tokens is None
        ):
            self.unknown += 1
            self.stopped = True
            raise StopPaid("响应用量不完整")
        self.input += usage.prompt_tokens
        self.output += usage.completion_tokens
        self.cost += (
            Decimal(usage.prompt_tokens) * Decimal("0.30")
            + Decimal(usage.completion_tokens) * Decimal("1.20")
        ) / 1_000_000
        save(self.folder / "usage.json", self.summary())
        if response.model not in flash.PROVIDER["accepted_response_models"]:
            self.stopped = True
            raise StopPaid("响应模型身份不符")
        if response.choices[0].finish_reason == "length":
            raise StopPaid("输出截断；已记录费用，不自动重试")
        return response

    def summary(self):
        return dict(
            provider_requests=self.requests,
            input_tokens=self.input,
            output_tokens=self.output,
            total_tokens=self.input + self.output,
            estimated_cost_usd_completed_responses=str(self.cost),
            unknown_usage_requests=self.unknown,
        )


def prepare():
    if MANIFEST.exists() or OUTPUT.exists():
        raise RuntimeError("身份已存在，不覆盖或续跑")
    SESSION.mkdir(parents=True, exist_ok=False)
    snapshot = SESSION / "baseline-source"
    shutil.copytree(
        BASELINE / "src",
        snapshot / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    source_files = {
        str(p.relative_to(snapshot)): sha(p)
        for p in sorted(snapshot.rglob("*"))
        if p.is_file()
    }
    parent = json.loads(PARENT.read_text())
    names = ("simdutf", "tinyxml2", "check")
    projects = [next(p for p in parent["projects"] if p["name"] == n) for n in names]
    schedule = [
        dict(project=n, method=m, repetition=1)
        for n, methods in zip(
            names,
            (
                ("model_plan_workflow", "cxxcrafter_community_reference"),
                ("cxxcrafter_community_reference", "model_plan_workflow"),
                ("model_plan_workflow", "cxxcrafter_community_reference"),
            ),
            strict=True,
        )
        for m in methods
    ]
    manifest = {
        **parent,
        "identity": IDENTITY,
        "issue": 629,
        "projects": projects,
        "schedule": schedule,
        "provider": flash.PROVIDER,
        "pricing": flash.PRICING,
        "deadline_utc": DEADLINE,
        "stage_max_cost_usd": str(STAGE_CAP),
        "user_cumulative_cap_usd": "10.00",
        "prior_cost_usd": str(PRIOR_COST),
        "authorization": "用户在22槽完成后明确要求继续后续实验；沿用原10美元累计上限和原截止，无自动重试。",
        "interpretation": "当前实现的探索性参考；三个已见项目各一次，不评价最终系统、论文原版或单独状态感知因果。",
        "baseline": {
            "path": str(snapshot),
            "upstream_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=BASELINE, text=True
            ).strip(),
            "files": source_files,
        },
        "adaptations": [
            "冻结当前社区版含既有运行修复，不修改原目录",
            "统一Flash thinking low及完整SDK用量，无SDK自动重试",
            "原生Parser/Generator/Modifier/两级Judge保留；追加共同用户任务、固定镜像、源码路径和2CPU约束",
            "只把文档选择eval收窄为literal_eval",
            "原生Docker API增加tag、rm及2CPU；外部完整测试/源码/交付/无缓存Dockerfile重建独立报告",
            "外部验收不反馈给CXXCrafter继续修订；其内部Judge与Forge固定测试恢复能力不同，禁止据此作纯算法排名",
        ],
        "new_slot_minimum_seconds": 1800,
        "baseline_max_dockerfile_versions": 10,
    }
    manifest["components"] = {
        **parent["components"],
        str(Path(__file__).relative_to(ROOT)): sha(__file__),
        PREREGISTRATION: sha(ROOT / PREREGISTRATION),
    }
    save(MANIFEST, manifest)
    save(
        SESSION / "authorization.json",
        {
            k: manifest[k]
            for k in (
                "identity",
                "authorization",
                "deadline_utc",
                "stage_max_cost_usd",
                "user_cumulative_cap_usd",
                "prior_cost_usd",
            )
        },
    )
    save(
        SESSION / "baseline-original-status.json",
        {
            "status": subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=BASELINE, text=True
            ),
            "source_files": source_files,
        },
    )
    print(json.dumps(dict(prepared=True, slots=len(schedule), provider_calls=0)))


def command(argv, folder, name, timeout=600):
    with (folder / (name + ".log")).open("w") as out:
        result = subprocess.run(
            argv,
            stdout=out,
            stderr=subprocess.STDOUT,
            timeout=min(timeout, max(1, remaining() - 120)),
            text=True,
        )
    return result.returncode


def source_hashes(root):
    rows = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            rows[str(p.relative_to(root))] = {"link": os.readlink(p)}
        elif p.is_file():
            rows[str(p.relative_to(root))] = {"sha256": sha(p)}
    return rows


def source_check(rows):
    script = """import hashlib,json,os,pathlib,sys
root=pathlib.Path('/workspace/repo'); expected=json.loads(sys.argv[1]); bad=[]
for name,identity in expected.items():
 p=root/name
 good=(p.is_symlink() and os.readlink(p)==identity['link']) if 'link' in identity else (p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==identity['sha256'])
 if not good: bad.append(name)
print(json.dumps({'source_unchanged':not bad,'changed':bad},sort_keys=True));sys.exit(bool(bad))
"""
    return ["python3", "-c", script, json.dumps(rows)]


def external_check(image, item, folder, frozen):
    folder.mkdir()
    artifacts = folder / "artifacts"
    artifacts.mkdir()
    name = "forge-cxx-ref-" + folder.parent.name + "-" + folder.name
    result = dict(
        source_unchanged=None,
        fixed_tests=None,
        artifact_stage=None,
        artifacts=None,
        cleanup=False,
    )
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--cpus",
                "2",
                "--entrypoint",
                "sleep",
                "-v",
                f"{artifacts}:/artifacts",
                image,
                "1800",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        prefix = [
            "docker",
            "exec",
            "-w",
            "/workspace/repo",
            "-e",
            "CMAKE_BUILD_PARALLEL_LEVEL=2",
            "-e",
            "CTEST_PARALLEL_LEVEL=2",
            "-e",
            "MAKEFLAGS=-j2",
            name,
        ]
        result["source_unchanged"] = (
            command([*prefix, *source_check(frozen)], folder, "source-before", 60) == 0
        )
        checks = []
        for index, step in enumerate(item["task"]["verification_steps"]):
            code = command(
                [
                    "docker",
                    "exec",
                    "-w",
                    step["workdir"],
                    name,
                    "bash",
                    "-euo",
                    "pipefail",
                    "-c",
                    step["command"],
                ],
                folder,
                f"test-{index}",
            )
            text = (folder / f"test-{index}.log").read_text(errors="replace")
            checks.append(code == 0 and all(x in text for x in step["required_output"]))
            if not checks[-1]:
                break
        result["fixed_tests"] = all(checks) and len(checks) == len(
            item["task"]["verification_steps"]
        )
        if result["fixed_tests"] and result["source_unchanged"]:
            code = command(
                [
                    *prefix,
                    "bash",
                    "-euo",
                    "pipefail",
                    "-c",
                    equivalent_delivery_command(tuple(item["task"]["artifact_paths"])),
                ],
                folder,
                "stage",
                60,
            )
            result["artifact_stage"] = code == 0
            rows = {
                str(p.relative_to(artifacts)): dict(
                    sha256=sha(p),
                    size=p.stat().st_size,
                    artifact_type=_classify_artifact(p),
                )
                for p in artifacts.rglob("*")
                if p.is_file()
            }
            result["artifacts"] = rows
            result["artifact_stage"] &= set(rows) == set(
                item["task"]["artifact_paths"]
            ) and all(
                r["size"] and r["artifact_type"] not in (None, "support_file")
                for r in rows.values()
            )
        result["source_unchanged"] &= (
            command([*prefix, *source_check(frozen)], folder, "source-after", 60) == 0
        )
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
        result["cleanup"] = (
            subprocess.run(
                ["docker", "inspect", name], capture_output=True, timeout=30
            ).returncode
            != 0
        )
        save(folder / "result.json", result)
    return result


def run_cxx(protocol, item, folder, available):
    # 复用已有社区版安装的Docker SDK；追加路径不替换Forge现有依赖。
    sdk_paths = list(
        BASELINE.glob(".venv/lib/python*/site-packages/docker/__init__.py")
    )
    if not sdk_paths:
        raise RuntimeError("缺少社区版已有Docker SDK")
    sys.path.append(str(sdk_paths[0].parents[1]))
    import docker
    import openai
    from openai.resources.chat.completions import Completions

    meter = SDKMeter(folder / "agent", min(Decimal("1.00"), available))
    sys.path.insert(0, str(Path(protocol["baseline"]["path"]) / "src"))
    os.environ["CXXCRAFTER_LLM_MODEL"] = "deepseek-flash"
    os.environ["CXXCRAFTER_API_KEY"] = os.environ["DEEPSEEK_API_KEY"]
    os.environ["CXXCRAFTER_BASE_URL"] = "https://api.deepseek.com/v1"
    import cxxcrafter.init as init
    import cxxcrafter.cli as cli
    import cxxcrafter.generation_module as generation
    import cxxcrafter.parsing_module.doc_parser as docs
    import cxxcrafter.execution_module.docker_manager as dm

    source = folder / "input" / item["name"]
    source.mkdir(parents=True)
    with tarfile.open(item["source_archive"]) as archive:
        archive.extractall(source, filter="data")
    frozen = source_hashes(source)
    save(folder / "original-source-hashes.json", frozen)
    # 与Forge相同，只建立原归档索引，不制造HEAD或源码提交。
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "-f", "--", "."], check=True)
    client = docker.APIClient(
        base_url="unix:///var/run/docker.sock",
        timeout=min(1200, max(1, int(remaining() - 180))),
    )
    tag = "forge-cxx-ref:" + folder.name
    task = {
        k: item["task"][k]
        for k in (
            "repository_url",
            "commit_sha",
            "build_system",
            "artifact_paths",
            "verification_steps",
        )
    }
    task["common_test_preparation"] = item["common_test_preparation"]
    constraint = (
        "\nAuthoritative user task overrides the illustrative Dockerfile template: "
        + json.dumps(task, ensure_ascii=False)
        + "\nUse FROM autocompiler:gcc13 (already provided fixed image); COPY the supplied project into /workspace/repo and WORKDIR /workspace/repo. Do not clone another revision or edit original source/tests. Build every required original test program before the evaluator runs its fixed commands. All jobs must use 2 workers. Do not run apt upgrade. Existing frozen dependency sources, when present, are under .forge-deps. Exact deliverables must be generated; the external evaluator performs staging."
    )
    original_prompt, original_create, original_init = (
        generation.get_initial_prompt,
        Completions.create,
        openai.OpenAI.__init__,
    )
    versions, build_containers = [], set()
    original_copytree = shutil.copytree

    def prompt(*a, **kw):
        return original_prompt(*a, **kw) + constraint

    def create(self, *args, **kwargs):
        return meter.request(lambda **kw: original_create(self, *args, **kw), kwargs)

    def sdk_init(self, *args, **kwargs):
        return original_init(
            self, *args, **{**kwargs, "max_retries": 0, "timeout": 240}
        )

    def preserve_links(*args, **kwargs):
        if len(args) > 2:  # shutil内部递归已按位置传递symlinks。
            return original_copytree(*args, **kwargs)
        return original_copytree(*args, **{**kwargs, "symlinks": True})

    def build_client():
        class Limited:
            def build(self, **kwargs):
                if meter.stopped:
                    raise StopPaid("Provider已停止")
                path = Path(kwargs["path"])
                versions.append((path / "Dockerfile").read_text())
                save(
                    folder / f"dockerfile-{len(versions)}.json",
                    {"content": versions[-1]},
                )
                stream = client.build(
                    **{
                        **kwargs,
                        "tag": tag,
                        "rm": True,
                        "forcerm": True,
                        "nocache": True,
                        "container_limits": {
                            "cpusetcpus": ",".join(
                                map(str, sorted(os.sched_getaffinity(0))[:2])
                            )
                        },
                    }
                )
                for chunk in stream:
                    line = chunk.get("stream", "").strip()
                    if line.startswith("---> Running in "):
                        build_containers.add(line.rsplit(" ", 1)[-1])
                    yield chunk

        return Limited()

    init_root = folder / "native-runtime"
    init_root.mkdir()
    error = None
    reported = False
    evaluations = []
    started = time.monotonic()
    try:
        with (
            patch.object(init, "get_base_dir", lambda: str(init_root)),
            patch.object(generation, "get_initial_prompt", prompt),
            patch.object(Completions, "create", create),
            patch.object(openai.OpenAI, "__init__", sdk_init),
            patch.object(dm, "_get_docker_client", build_client),
            patch.object(docs, "eval", ast.literal_eval, create=True),
            patch.object(generation.shutil, "copytree", preserve_links),
        ):
            init.ensure_all_directories_exist()
            native = cli.CXXCrafter(str(source))
            _, reported = native.run()
        if reported and not meter.stopped:
            image = client.inspect_image(tag)["Id"]
            evaluations.append(external_check(image, item, folder / "original", frozen))
            if (
                evaluations[0]["fixed_tests"]
                and evaluations[0]["artifact_stage"]
                and evaluations[0]["source_unchanged"]
                and remaining() > 900
            ):
                chunks = list(
                    client.build(
                        path=str(Path(native.dockerfile_path).parent),
                        tag=tag + "-replay",
                        decode=True,
                        rm=True,
                        forcerm=True,
                        nocache=True,
                        container_limits={
                            "cpusetcpus": ",".join(
                                map(str, sorted(os.sched_getaffinity(0))[:2])
                            )
                        },
                    )
                )
                save(folder / "replay-build.json", chunks)
                if not any("error" in c or "errorDetail" in c for c in chunks):
                    replay_image = client.inspect_image(tag + "-replay")["Id"]
                    evaluations.append(
                        external_check(replay_image, item, folder / "replay", frozen)
                    )
    except Exception as exc:
        error = dict(error_class=type(exc).__name__, error_message=str(exc)[:1500])
    finally:
        cleanup = True
        for container in build_containers:
            try:
                client.remove_container(container, force=True)
            except docker.errors.NotFound:
                pass
            except docker.errors.APIError:
                cleanup = False
        for value in (tag, tag + "-replay"):
            try:
                client.remove_image(value, force=False)
            except docker.errors.ImageNotFound:
                pass
            except docker.errors.APIError:
                cleanup = False
        save(folder / "agent/usage.json", meter.summary())
    strict = (
        len(evaluations) == 2
        and all(
            e["fixed_tests"]
            and e["artifact_stage"]
            and e["source_unchanged"]
            and e["cleanup"]
            for e in evaluations
        )
        and evaluations[0]["artifacts"] == evaluations[1]["artifacts"]
        and cleanup
    )
    return dict(
        name=item["name"],
        method="cxxcrafter_community_reference",
        reported_success=reported,
        strict_completed=strict,
        evaluations=evaluations,
        agent_usage=meter.summary(),
        cleanup=dict(succeeded=cleanup),
        versions=len(versions),
        arm_total_wall_seconds=time.monotonic() - started,
        provider_stop=meter.stopped,
        **(error or {}),
    )


@contextmanager
def execution_patch():
    with (
        patch.object(flash.base, "PROVIDER", flash.PROVIDER),
        patch.object(flash.base, "PreparationMeter", flash.FlashMeter),
        patch.object(flash.base, "execution_window", flash.bounded.execution_window),
    ):
        yield


def run():
    protocol = json.loads(MANIFEST.read_text())
    for name, expected in protocol["components"].items():
        if sha(ROOT / name) != expected:
            raise RuntimeError("运行代码变化：" + name)
    for name, expected in protocol["baseline"]["files"].items():
        if sha(Path(protocol["baseline"]["path"]) / name) != expected:
            raise RuntimeError("基线快照变化")
    image = subprocess.check_output(
        ["docker", "image", "inspect", "autocompiler:gcc13", "--format", "{{.Id}}"],
        text=True,
    ).strip()
    for item in protocol["projects"]:
        if (
            sha(item["source_archive"]) != item["task"]["source_archive_sha256"]
            or image != item["task"]["image_id"]
        ):
            raise RuntimeError("原归档或固定镜像变化")
    if remaining() < 1800 or PRIOR_COST + STAGE_CAP > Decimal("10.00"):
        raise RuntimeError("原时窗或累计预算不足")
    subprocess.run(
        ["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True
    )
    OUTPUT.mkdir(exist_ok=False)
    save(OUTPUT / "protocol.json", protocol)
    save(
        OUTPUT / "execution.json",
        {
            "release": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
        },
    )
    from dotenv import load_dotenv

    for path in (ROOT / ".env", ROOT / "backend/.env"):
        if not os.environ.get("DEEPSEEK_API_KEY"):
            load_dotenv(path, override=False)
    model = flash.base.PlanThinkingDeepSeek(
        model="deepseek-flash",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
        max_tokens=32768,
        max_retries=0,
        timeout=240,
        reasoning_effort="low",
        extra_body={"thinking": {"type": "enabled"}},
    )
    rows, stop = [], None
    try:
        for index, slot in enumerate(protocol["schedule"], 1):
            known = sum(
                (
                    Decimal(
                        str(r["agent_usage"]["estimated_cost_usd_completed_responses"])
                    )
                    for r in rows
                ),
                Decimal(0),
            )
            reserve = (
                Decimal("1.00")
                if slot["method"] == "cxxcrafter_community_reference"
                else Decimal("3.00")
            )
            if remaining() < 1800 or known + reserve > STAGE_CAP:
                stop = "remaining_time_or_budget"
                break
            folder = OUTPUT / f"slot-{index}"
            folder.mkdir()
            item = next(i for i in protocol["projects"] if i["name"] == slot["project"])
            try:
                if slot["method"] == "cxxcrafter_community_reference":
                    row = run_cxx(protocol, item, folder, STAGE_CAP - known)
                else:
                    with execution_patch():
                        row = replication.run_slot(
                            protocol=protocol, slot=slot, root=folder, model=model
                        )
            except Exception as exc:
                usage = folder / "agent/usage.json"
                row = dict(
                    strict_completed=False,
                    error_class=type(exc).__name__,
                    error_message=str(exc)[:1500],
                    agent_usage=json.loads(usage.read_text())
                    if usage.exists()
                    else dict(
                        provider_requests=0,
                        total_tokens=0,
                        estimated_cost_usd_completed_responses="0",
                        unknown_usage_requests=0,
                    ),
                    cleanup=dict(succeeded=False),
                    provider_stop=True,
                )
            rows.append({**row, **slot})
            save(OUTPUT / f"progress-{index}.json", rows[-1])
            print(
                json.dumps(
                    {
                        k: rows[-1].get(k)
                        for k in (
                            "project",
                            "method",
                            "strict_completed",
                            "reported_success",
                            "agent_usage",
                            "error_message",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if (
                row["agent_usage"]["unknown_usage_requests"]
                or not row["cleanup"]["succeeded"]
                or row.get("provider_stop")
            ):
                stop = "unknown_usage_cleanup_or_provider_identity"
                break
    finally:
        known, unknown = flash.base.charges(rows)
        save(
            OUTPUT / "result.json",
            dict(
                identity=IDENTITY,
                rows=rows,
                unobserved_schedule=protocol["schedule"][len(rows) :],
                stop_reason=stop,
                known_estimated_cost_usd=str(known),
                unknown_usage_reservation_usd=str(unknown),
                cumulative_known_cost_usd=str(PRIOR_COST + known),
            ),
        )
        seal(
            OUTPUT,
            protocol,
            ROOT,
            sum(r["agent_usage"]["unknown_usage_requests"] for r in rows),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    args = parser.parse_args()
    if args.mode == "run":

        def timeout(signum, frame):
            raise StopPaid("原运行时窗截止，预留清理")

        signal.signal(signal.SIGALRM, timeout)
        signal.setitimer(signal.ITIMER_REAL, max(1, remaining() - 180))
        run()
    else:
        prepare()
