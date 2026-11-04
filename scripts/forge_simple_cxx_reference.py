"""CXXCrafter社区原生循环的简洁任务适配；保留Parser/Generator/Modifier/Judge。"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from forge_build_simple_task import full_completion, save

from deerflow.compile.operation_window import OperationWindow
from deerflow.compile.plan_workflow import PlanContractError, _digest
from deerflow.compile.simple_build_runtime import primary_artifacts, source_inventory

BASELINE = Path("/home/yiwei/work/CXXCrafter-Community-Edition")


def resource_dockerfile(text, image, jobs):
    """只替换固定环境与并行资源，不生成/修改基线构建命令。"""
    lines = text.splitlines()
    positions = [i for i, line in enumerate(lines) if line.strip().upper().startswith("FROM ")]
    if len(positions) != 1 or lines[positions[0]].split()[1] not in {"autocompiler:gcc13", image}:
        raise PlanContractError("CXX参考仅支持共同固定镜像的单阶段Dockerfile")
    lines[positions[0]] = "FROM " + image
    marker = f"ENV CMAKE_BUILD_PARALLEL_LEVEL={jobs} MAKEFLAGS=-j{jobs} CTEST_PARALLEL_LEVEL=1"
    if marker not in lines:
        lines.insert(positions[0] + 1, marker)
    return "\n".join(lines) + "\n"


def portable_source(rows):
    # Docker镜像快照会改变inode/ctime；内容、链接与权限仍与原输入逐项比对。
    return {name: dict(sha256=row["sha256"], link=row["link"], permissions=row["mode"] & 0o777) for name, row in rows.items()}


def check_original(root, expected):
    current = portable_source(source_inventory(root))
    if any(current.get(name) != row for name, row in expected.items()):
        raise PlanContractError("CXX产物镜像修改了原源码/测试")


def external_simple_check(*, image, task, reference, original_source, folder, author_test_seconds):
    """与Forge共享主要组件识别；测试/暂存是独立层，不回送原生Modifier。"""
    folder.mkdir()
    root, artifacts = folder / "workspace", folder / "artifacts"
    root.mkdir()
    artifacts.mkdir()
    name = "forge-simple-cxx-check-" + uuid.uuid4().hex[:12]
    expected = portable_source(source_inventory(original_source))
    layers = dict(command_build_passed=True, primary_build_completed=None, delivery="unobserved", author_tests="unobserved", clean_replay="unobserved", full_completed=None)
    result = dict(layers=layers, source_unchanged=None, artifacts=[], container_name=name)
    started = time.monotonic()
    try:
        subprocess.run(["docker", "run", "-d", "--name", name, "--cpus", str(task.parallel_jobs), "--network", "compile_network_wwf_v1", "--entrypoint", "sleep", image, "1800"], check=True, capture_output=True, timeout=30)
        subprocess.run(["docker", "cp", name + ":/workspace/repo/.", str(root)], check=True, capture_output=True, timeout=60)
        check_original(root, expected)
        rows = source_inventory(root)
        baseline = {key: rows[key] for key in expected}
        primary = primary_artifacts(task=task, reference=reference, root=root, baseline=baseline, deadline=time.monotonic() + 30)
        layers["primary_build_completed"] = primary["status"] == "passed" if primary["status"] != "unknown" else None
        result["primary"] = primary
        result["time_to_primary_check_seconds"] = time.monotonic() - started
        save(folder / "primary-result.json", dict(layers=layers, primary=primary))
        if layers["primary_build_completed"]:
            delivered = []
            for item in primary["artifacts"]:
                p = root / item["path"]
                if (artifacts / p.name).exists():
                    raise PlanContractError("CXX主组件交付名称歧义")
                shutil.copy2(p, artifacts / p.name)
                delivered.append(dict(name=p.name, kind=item["kind"], size=item["size"], sha256=item["sha256"], mode=item["mode"]))
            result["artifacts"] = sorted(delivered, key=lambda r: r["name"])
            layers["delivery"] = "passed"
            if not reference.author_tests:
                layers["author_tests"] = "not_applicable" if reference.tests_not_applicable_reason else "unobserved"
            else:
                layers["author_tests"] = "passed"
                test_start = time.monotonic()
                for i, step in enumerate(reference.author_tests):
                    seconds = int(author_test_seconds - (time.monotonic() - test_start))
                    if seconds < 1:
                        layers["author_tests"] = "timeout"
                        break
                    try:
                        completed = subprocess.run(["docker", "exec", "-e", "CTEST_PARALLEL_LEVEL=1", "-w", step.workdir, name, "bash", "-euo", "pipefail", "-c", step.command], capture_output=True, text=True, timeout=seconds)
                        output = completed.stdout + completed.stderr
                        (folder / f"test-{i}.log").write_text(output)
                        if completed.returncode or not all(marker in output for marker in step.required_output):
                            layers["author_tests"] = "failed"
                            break
                    except subprocess.TimeoutExpired as exc:
                        (folder / f"test-{i}.log").write_text(str(exc))
                        layers["author_tests"] = "timeout"
                        break
            after = folder / "source-after-tests"
            after.mkdir()
            subprocess.run(["docker", "cp", name + ":/workspace/repo/.", str(after)], check=True, capture_output=True, timeout=60)
            check_original(after, expected)
        result["source_unchanged"] = True
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc))
        if isinstance(exc, PlanContractError) and "源码" in str(exc):
            result["source_unchanged"] = False
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
        inspected = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, timeout=30)
        result["cleanup"] = dict(succeeded=inspected.returncode != 0 and "no such" in inspected.stderr.lower())
        result["external_seconds"] = time.monotonic() - started
        save(folder / "result.json", result)
    return result


def run_native_cxx(*, task, reference, source_archive, output_root, completion_call, maximum_cost_usd="1.00", deadline=None, author_test_seconds=120, baseline=BASELINE, zero_provider=False):
    """completion_call由外部授权启动器提供；此处不读取模型密钥或配置文件。"""
    from forge_cxx_current_reference import SDKMeter

    repo = Path(__file__).resolve().parents[1]
    subprocess.run(["bash", str(repo / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    if reference.task_sha256 != _digest(task.model_dump(mode="json")) or hashlib.sha256(source_archive.read_bytes()).hexdigest() != task.source_archive_sha256:
        raise PlanContractError("公开任务、参考或源码归档不一致")
    folder = output_root.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    save(folder / "common-public-task.json", task.model_dump(mode="json"))
    save(folder / "private-reference.json", reference.model_dump(mode="json"))
    snapshot = {str(p.relative_to(baseline)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((baseline / "src").rglob("*.py"))}
    save(folder / "baseline-source-hashes.json", snapshot)
    save(
        folder / "scope.json",
        dict(
            kind="zero_provider_engineering" if zero_provider else "requires_external_authorized_protocol",
            method="cxxcrafter",
            public_task_sha256=reference.task_sha256,
            baseline=str(baseline),
            native_components="Parser/Generator/Modifier/Judge",
            source_protection="portable_content_link_mode_not_inode",
        ),
    )
    sdk = next(baseline.glob(".venv/lib/python*/site-packages/docker/__init__.py"))
    sys.path.extend([str(sdk.parents[1]), str(baseline / "src")])
    import docker
    from openai.resources.chat.completions import Completions

    source = folder / "input" / task.plan_id
    source.mkdir(parents=True)
    with tarfile.open(source_archive) as archive:
        archive.extractall(source, filter="data")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "-f", "--", "."], check=True)
    window = OperationWindow(deadline or (datetime.now(UTC) + timedelta(hours=1)).isoformat())
    meter = SDKMeter(folder / "agent", Decimal(maximum_cost_usd))
    client = docker.APIClient(base_url="unix:///var/run/docker.sock", timeout=240)
    tag = "forge-simple-cxx:" + uuid.uuid4().hex[:12]
    native_root = folder / "native-runtime"
    native_root.mkdir()
    versions, build_containers, evaluations, managed_images = [], set(), [], set()
    result = dict(method="cxxcrafter", status="started", layers=dict(command_build_passed=None, primary_build_completed=None, delivery="unobserved", author_tests="unobserved", clean_replay="unobserved", full_completed=None))
    started = time.monotonic()
    old_copytree = shutil.copytree

    def preserve_links(*args, **kwargs):
        return old_copytree(*args, **kwargs) if len(args) > 2 else old_copytree(*args, **(kwargs | dict(symlinks=True)))

    def complete(_self, *args, **kwargs):
        public = dict(
            role="system",
            content="共同公开构建目标，优先于示例：" + task.model_dump_json() + "\nUse FROM autocompiler:gcc13. COPY the supplied source to /workspace/repo. "
            "Do not clone another revision or modify original source/tests. Use author-recommended or default main targets. "
            "Do not add test, Debug or delivery requirements. External checks run independently.",
        )
        with patch("forge_cxx_current_reference.remaining", lambda: window.remaining() + 300):
            return meter.request(completion_call, kwargs | dict(messages=[public, *kwargs.get("messages", [])]))

    def build(**kwargs):
        window.admit("native_docker_build", 300)
        p = Path(kwargs["path"]) / "Dockerfile"
        original = p.read_text()
        p.write_text(resource_dockerfile(original, task.image_id, task.parallel_jobs))
        versions.append(dict(native=original, effective=p.read_text()))
        save(folder / f"dockerfile-{len(versions)}.json", versions[-1])
        stream = client.build(
            **(kwargs | dict(tag=tag, rm=True, forcerm=True, nocache=True, network_mode="compile_network_wwf_v1", container_limits=dict(cpusetcpus=",".join(map(str, sorted(os.sched_getaffinity(0))[: task.parallel_jobs])))))
        )
        chunks = []
        for chunk in stream:
            chunks.append(chunk)
            if chunk.get("aux", {}).get("ID"):
                managed_images.add(chunk["aux"]["ID"])
            line = chunk.get("stream", "").strip()
            if line.startswith("---> Running in "):
                build_containers.add(line.rsplit(" ", 1)[-1])
            yield chunk
        save(folder / f"build-{len(versions)}.json", chunks)

    class NativeBuildClient:
        def build(self, **kwargs):
            return build(**kwargs)

    try:
        # 原生SDK仅作请求形状构造；全部调用强制经过上方completion_call，绝不读取真实凭据。
        with patch.dict(os.environ, dict(CXXCRAFTER_LLM_MODEL="deepseek-flash", CXXCRAFTER_API_KEY="explicit-injected-transport", CXXCRAFTER_BASE_URL="http://127.0.0.1:9/v1")):
            import cxxcrafter.cli as cli
            import cxxcrafter.execution_module.docker_manager as dm
            import cxxcrafter.generation_module as generation
            import cxxcrafter.init as init
            import cxxcrafter.parsing_module.doc_parser as docs

            with (
                patch.object(init, "get_base_dir", lambda: str(native_root)),
                patch.object(Completions, "create", complete),
                patch.object(dm, "_get_docker_client", NativeBuildClient),
                patch.object(docs, "eval", ast.literal_eval, create=True),
                patch.object(generation.shutil, "copytree", preserve_links),
            ):
                init.ensure_all_directories_exist()
                native = cli.CXXCrafter(str(source))
                _, reported = native.run()
            result["reported_success"] = reported
            if reported and not meter.stopped:
                image = client.inspect_image(tag)["Id"]
                managed_images.add(image)
                evaluations.append(external_simple_check(image=image, task=task, reference=reference, original_source=source, folder=folder / "original", author_test_seconds=author_test_seconds))
                result.update(layers=copy_dict(evaluations[0]["layers"]), source_unchanged=evaluations[0]["source_unchanged"])
                if result["layers"]["primary_build_completed"] and result["layers"]["delivery"] == "passed":
                    window.replay(240)
                    chunks = list(build(path=str(Path(native.dockerfile_path).parent), decode=True))
                    if not any("error" in c or "errorDetail" in c for c in chunks):
                        image = client.inspect_image(tag)["Id"]
                        managed_images.add(image)
                        evaluations.append(external_simple_check(image=image, task=task, reference=reference, original_source=source, folder=folder / "replay", author_test_seconds=author_test_seconds))
                        second = evaluations[-1]
                        tests_ok = result["layers"]["author_tests"] != "passed" or second["layers"]["author_tests"] == "passed"
                        passed = second["layers"]["primary_build_completed"] and second["layers"]["delivery"] == "passed" and second["source_unchanged"] and evaluations[0]["artifacts"] == second["artifacts"] and tests_ok
                        result["layers"]["clean_replay"] = "passed" if passed else "failed"
                    else:
                        result["layers"]["clean_replay"] = "failed"
            result["status"] = "native_completed"
    except Exception as exc:
        result.update(status="error", error_type=type(exc).__name__, error=str(exc))
    finally:
        cleanup = all(e["cleanup"]["succeeded"] for e in evaluations)
        for container in build_containers:
            try:
                client.remove_container(container, force=True)
            except docker.errors.NotFound:
                pass
            except docker.errors.APIError:
                cleanup = False
        for image in [tag, *sorted(managed_images)]:
            try:
                client.remove_image(image, force=False)
            except docker.errors.ImageNotFound:
                pass
            except docker.errors.APIError:
                cleanup = False
        result.update(
            evaluations=evaluations, managed_image_ids=sorted(managed_images), build_container_ids=sorted(build_containers), cleanup=dict(succeeded=cleanup), agent_usage=meter.summary(), arm_total_wall_seconds=time.monotonic() - started
        )
        result["layers"]["full_completed"] = full_completion(result["layers"], cleanup)
        if result["status"] == "error" or result.get("source_unchanged") is False:
            result["layers"]["full_completed"] = False
        save(folder / "result.json", result)
    return result


def copy_dict(value):
    return json.loads(json.dumps(value))


def run_scripted_cxx(*, calls, **kwargs):
    from openai.types.chat import ChatCompletion

    def completion(**request):
        text = json.dumps(request["messages"], ensure_ascii=False)
        selected = next((c for c in calls if c["contains"] in text), None)
        if selected is None:
            raise RuntimeError("离线CXX回复未覆盖当前提示，不调用Provider")
        return ChatCompletion(
            id="zero-provider-script",
            created=0,
            model="deepseek-flash",
            object="chat.completion",
            choices=[dict(index=0, finish_reason="stop", message=dict(role="assistant", content=selected["response"]))],
            usage=dict(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )

    return run_native_cxx(**kwargs, completion_call=completion, zero_provider=True)
