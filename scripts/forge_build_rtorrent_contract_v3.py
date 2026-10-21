"""rtorrent任务专属完整作者注册测试合同v3；原测试程序不改写，不按结果删减。"""

from __future__ import annotations

import inspect
import json
import re
import shlex


def author_tests(root):
    """展开作者Makefile.am的TESTS及各SOURCES，固定所有原CppUnit注册声明。"""
    text = (root / "test/Makefile.am").read_text().replace("\\\n", " ")
    variables = dict(re.findall(r"(?m)^([A-Za-z0-9_]+)\s*=\s*([^\n]*)", text))

    def expand(value):
        for _ in range(20):
            replaced = re.sub(r"\$\((\w+)\)", lambda m: variables[m.group(1)], value)
            if replaced == value:
                return replaced.split()
            value = replaced
        raise ValueError("作者变量展开未闭合")

    result = {}
    for program in expand(variables["TESTS"]):
        names = []
        registrations = {}
        for source in expand(variables[program + "_SOURCES"]):
            if source.endswith(".cc"):
                body = (root / "test" / source).read_text()
                for suite, registry in re.findall(r'CPPUNIT_TEST_SUITE_NAMED_REGISTRATION\s*\(\s*(\w+)\s*,\s*"([^"\n]+)"\s*\)', body):
                    if suite in registrations and registrations[suite] != registry:
                        raise ValueError("同一suite多个注册来源，需独立审阅")
                    registrations[suite] = registry
        headers = [p for p in expand(variables[program + "_SOURCES"]) if p.endswith(".h")]
        for header in headers:
            content = (root / "test" / header).read_text()
            content = re.sub(r"/\*.*?\*/|//[^\n]*", "", content, flags=re.S)
            suites = re.findall(r"\bCPPUNIT_TEST_SUITE\s*\(\s*(\w+)\s*\)", content)
            cases = re.findall(r"\bCPPUNIT_TEST\s*\(\s*(\w+)\s*\)", content)
            if cases:
                if len(suites) != 1:
                    raise ValueError("测试声明需独立审阅")
                prefix = registrations.get(suites[0], "")
                names.extend((prefix + "::" if prefix else "") + suites[0] + "::" + c for c in cases)
        if not names or len(names) != len(set(names)):
            raise ValueError("原测试程序为空或重复")
        result[program] = sorted(names)
    return result


def validate_cppunit_output(output, expected):
    """既核对原退出码，又校验全部叶测试身份及CppUnit总数，不能空测试通过。"""
    import re

    names = []
    pending = None
    for line in output.splitlines():
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_/]*(?:::\w+)+)(.*)", line)
        if match and match[2] != ":":
            if pending is not None or match[1] not in expected:
                raise ValueError("原测试开始身份未知或前叶尚未结束")
            pending = match[1]
            if match[2].strip() == ": OK":
                names.append(pending)
                pending = None
            elif match[2].strip():
                raise ValueError("原测试开始行格式不明确")
        elif line.strip() == ": OK":
            if pending is None:
                raise ValueError("原测试成功标记没有开始身份")
            names.append(pending)
            pending = None
        elif re.search(r" : (?:assertion|error)(?:$|\s)", line):
            raise ValueError("原测试含失败标记")
    if pending is not None:
        raise ValueError("原测试开始后缺少结束标记")
    summaries = re.findall(r"(?m)^OK \((\d+)(?: tests?)?\)\s*$", output)
    if len(summaries) != 1 or int(summaries[0]) != len(expected) or sorted(names) != sorted(expected):
        raise ValueError("原测试总数/叶身份缺失、重复或未全通过")
    return len(names)


def verification_main(groups):
    import os
    import pathlib
    import subprocess

    results = []
    environment = os.environ.copy()
    environment.pop("TEST_NAME", None)
    environment["LC_ALL"] = "C"
    environment["LD_LIBRARY_PATH"] = "/workspace/prefix/lib"
    for build, programs in groups.items():
        cwd = pathlib.Path("/workspace/repo") / build / "test"
        for name, expected in programs.items():
            run = subprocess.run([str(cwd / name)], cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, text=True)
            (cwd / (name + ".forge-full.log")).write_text(run.stdout)
            if run.returncode != 0:
                raise ValueError("原作者测试失败:" + name + ":" + str(run.returncode))
            count = validate_cppunit_output(run.stdout, expected)
            results.append({"program": name, "passed": count, "expected": len(expected)})
    environment["LD_LIBRARY_PATH"] = "/artifacts"
    run = subprocess.run(["/artifacts/rtorrent", "-h"], env=environment, capture_output=True, text=True, timeout=20)
    pathlib.Path("/workspace/repo/build-rtorrent/rtorrent-help.log").write_text(run.stdout + run.stderr)
    if run.returncode != 0 or "Rakshasa's BitTorrent client version 0.16.25." not in run.stdout or "Usage: rtorrent" not in run.stdout:
        raise ValueError("精确交付的CLI/同版本库验证失败")
    print("FORGE_RTORRENT_FULL_TESTS=" + json.dumps({"programs": results, "cli_version": "0.16.25", "test_name_filter": False}, sort_keys=True), flush=True)


def verification_command(groups):
    source = inspect.getsource(validate_cppunit_output) + "\n" + inspect.getsource(verification_main) + "\nverification_main(" + repr(groups) + ")\n"
    return "python3 -c " + shlex.quote(source)
