#!/usr/bin/env python3
"""零Provider后验验证：真实ltdl宏与Agent兼容宏的当前平台构建及功能。"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "cpp-build-libffi-functional-comparison-v1"
HISTORY = Path("/home/yiwei/.codex/outputs/forge-libffi-posthoc-review-flash-2026-11-16-v1")


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path):
    result = []
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2 and re.fullmatch("[A-Za-z]", fields[1]):
            result.append((fields[0], fields[1]))
    return sorted(set(result))


def defines(path):
    return sorted(line.strip() for line in path.read_text().splitlines() if line.startswith("#define "))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    item = next(row for row in json.loads((ROOT / "benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json").read_text())["projects"] if row["name"] == "libffi")
    archive = Path(item["source_archive"])
    assert sha(archive) == item["task"]["source_archive_sha256"]
    session = json.loads(next((HISTORY / "libffi").rglob("session.json")).read_text())
    original = Path(session["leadagent_repo_dir"])
    macro = original / "m4/lt_sys_symbol_uscore_compat.m4"
    save(
        root / "scope.json",
        dict(
            identity=IDENTITY,
            kind="posthoc_functional_validation",
            provider_calls=0,
            maximum_cost_usd=0,
            authorization="用户批准进行下一项零模型费用功能对照",
            stop="每路径一次；非预期失败保留，不自动重试；命令最多600秒",
            task=item["task"],
            historical_evidence_readonly=str(HISTORY),
            shared_configuration="./autogen.sh && ./configure --disable-docs; make -j2",
            treatments=["真实libltdl-dev宏", "上一自主运行最终新增宏"],
            scientific_effect_observations=0,
        ),
    )
    snapshot = root / "source-snapshot"
    snapshot.mkdir()
    for path in [Path(__file__), ROOT / "benchmarks/fixtures/libffi-functional-comparison-v1/probe.c"]:
        shutil.copy2(path, snapshot / path.name)
    shutil.copy2(macro, root / "observed-compat.m4")
    save(root / "source-sha256.json", {p.name: sha(p) for p in snapshot.iterdir()})
    records = []
    cleanup = []
    started = time.monotonic()

    def execute(label, command, timeout=600):
        t = time.monotonic()
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        (root / f"{label}.log").write_text(result.stdout + result.stderr)
        records.append(dict(label=label, command=command, exit_code=result.returncode, seconds=time.monotonic() - t))
        save(root / "commands.json", records)
        if result.returncode:
            raise RuntimeError(f"{label}退出{result.returncode}，保留并停止")
        return result.stdout

    try:
        for arm in ["real_dependency", "agent_macro"]:
            work = root / arm
            work.mkdir()
            shutil.copy2(archive, work / "source.tar")
            shutil.copy2(snapshot / "probe.c", work / "probe.c")
            shutil.copy2(macro, work / "compat.m4")
            # 复制原观察产物与公开头文件，原件只读，不在原目录执行。
            observed = work / "observed"
            observed.mkdir()
            for name in ["ffi.h", "ffitarget.h"]:
                shutil.copy2(original / "x86_64-pc-linux-gnu/include" / name, observed / name)
            artifacts = Path(session["leadagent_artifacts_dir"])
            for name in ["libffi.a", "libffi.so.8.1.4"]:
                shutil.copy2(artifacts / name, observed / name)
            (observed / "libffi.so.8").symlink_to("libffi.so.8.1.4")
            (observed / "libffi.so").symlink_to("libffi.so.8.1.4")
            name = f"forge-libffi-functional-{arm.replace('_', '-')}-{int(time.time())}"
            container = execute(
                f"{arm}-create",
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--network",
                    "compile_network_wwf_v1",
                    "--cpus",
                    "2",
                    "--memory",
                    "4g",
                    "-v",
                    f"{work}:/case",
                    "-w",
                    "/case",
                    item["task"]["image_id"],
                    "sleep",
                    "infinity",
                ],
                60,
            ).strip()
            try:
                prep = "mkdir repo out; tar -xf source.tar -C repo; "
                prep += "apt-get -o Acquire::Retries=0 update; "
                if arm == "real_dependency":
                    prep += "DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=0 install -y --no-install-recommends libltdl-dev; "
                    prep += "dpkg-query -S /usr/share/aclocal/ltdl.m4 > out/macro-owner.txt; cp /usr/share/aclocal/ltdl.m4 out/provider.m4; "
                else:
                    prep += "cp compat.m4 repo/m4/lt_sys_symbol_uscore_compat.m4; "
                prep += "dpkg-query -W > out/packages.txt; cc --version > out/compiler.txt; cat /etc/apt/sources.list.d/ubuntu.sources > out/apt-sources.txt"
                execute(f"{arm}-prepare", ["docker", "exec", container, "bash", "-euo", "pipefail", "-c", prep])
                build = (
                    "cd repo; "
                    "./autogen.sh; "
                    "./configure --disable-docs; "
                    "make -j2; "
                    "cp x86_64-pc-linux-gnu/fficonfig.h ../out/fficonfig.h; "
                    "cp x86_64-pc-linux-gnu/include/ffi.h ../out/ffi.h; "
                    "cp x86_64-pc-linux-gnu/include/ffitarget.h ../out/ffitarget.h; "
                    "nm -D --defined-only --format=posix x86_64-pc-linux-gnu/.libs/libffi.so.8.1.4 > ../out/shared-symbols.txt; "
                    "nm -g --defined-only --format=posix x86_64-pc-linux-gnu/.libs/libffi.a > ../out/static-symbols.txt"
                )
                execute(f"{arm}-build", ["docker", "exec", container, "bash", "-euo", "pipefail", "-c", build])
                probe = (
                    "cd /case; "
                    "cc -Wall -Wextra -Werror -Irepo/x86_64-pc-linux-gnu/include probe.c repo/x86_64-pc-linux-gnu/.libs/libffi.a -ldl -lpthread -lm -o out/probe-static; "
                    "./out/probe-static > out/static-results.txt; "
                    "cc -Wall -Wextra -Werror -Irepo/x86_64-pc-linux-gnu/include probe.c -L/case/repo/x86_64-pc-linux-gnu/.libs -Wl,-rpath,/case/repo/x86_64-pc-linux-gnu/.libs -lffi -lm -o out/probe-shared; "
                    "ldd out/probe-shared > out/shared-linked.txt; "
                    "./out/probe-shared > out/shared-results.txt"
                )
                execute(f"{arm}-probe", ["docker", "exec", container, "bash", "-euo", "pipefail", "-c", probe])
                if arm == "agent_macro":
                    probe_original = (
                        "cc -Wall -Wextra -Werror -Iobserved probe.c observed/libffi.a -ldl -lpthread -lm -o out/observed-static; "
                        "./out/observed-static > out/observed-static-results.txt; "
                        "cc -Wall -Wextra -Werror -Iobserved probe.c -L/case/observed -Wl,-rpath,/case/observed -lffi -lm -o out/observed-shared; "
                        "ldd out/observed-shared > out/observed-shared-linked.txt; "
                        "./out/observed-shared > out/observed-shared-results.txt"
                    )
                    execute("observed-artifact-probe", ["docker", "exec", container, "bash", "-euo", "pipefail", "-c", probe_original])
            finally:
                execute(f"{arm}-cleanup", ["docker", "rm", "-f", container], 60)
                check = subprocess.run(["docker", "container", "inspect", container], capture_output=True, text=True)
                absent = check.returncode != 0 and "No such" in check.stderr
                cleanup.append(dict(container_id=container, container_name=name, absent=absent))
                save(root / "cleanup.json", cleanup)
                if not absent:
                    raise RuntimeError("清理未确认，停止")
        a, b = [root / arm / "out" for arm in ["real_dependency", "agent_macro"]]
        outputs = [a / "static-results.txt", a / "shared-results.txt", b / "static-results.txt", b / "shared-results.txt", b / "observed-static-results.txt", b / "observed-shared-results.txt"]
        assert all("FUNCTIONAL_SCENARIOS=5 PASSED=5" in p.read_text() for p in outputs)
        assert "/case/repo/" in (a / "shared-linked.txt").read_text()
        assert "/case/repo/" in (b / "shared-linked.txt").read_text()
        assert "/case/observed/" in (b / "observed-shared-linked.txt").read_text()
        ad, bd = defines(a / "fficonfig.h"), defines(b / "fficonfig.h")
        save(
            root / "summary.json",
            dict(
                identity=IDENTITY,
                provider_calls=0,
                cost_usd=0,
                status="completed",
                seconds=time.monotonic() - started,
                configuration_defines_equal=ad == bd,
                only_real_defines=sorted(set(ad) - set(bd)),
                only_agent_defines=sorted(set(bd) - set(ad)),
                public_headers_equal=all((a / f).read_bytes() == (b / f).read_bytes() for f in ["ffi.h", "ffitarget.h"]),
                shared_export_symbols_equal=symbols(a / "shared-symbols.txt") == symbols(b / "shared-symbols.txt"),
                static_global_symbols_equal=symbols(a / "static-symbols.txt") == symbols(b / "static-symbols.txt"),
                shared_export_count=len(symbols(a / "shared-symbols.txt")),
                functional_scenarios_per_binary=5,
                tested_binaries=6,
                functional_outputs_equal=len({p.read_text() for p in outputs}) == 1,
                observed_artifacts_tested=True,
                cleanup=cleanup,
                boundary="当前固定Linux x86_64案例验证，非全功能/跨平台等价证明；不回写旧观察或增加项目分母",
            ),
        )
    except Exception as exc:
        save(root / "failure.json", dict(error=str(exc), provider_calls=0, cleanup=cleanup))
        raise


if __name__ == "__main__":
    main()
