"""按实际构建入口运行作者测试；只修入口适配，不把零测试算通过。"""

from __future__ import annotations

import shlex
from pathlib import Path

from deerflow.compile.plan_workflow import PlanStep

CTEST_SCRIPT = """import pathlib,subprocess
root=pathlib.Path('/workspace/repo').resolve()
roots=[]
for p in sorted(root.rglob('CMakeCache.txt')):
 if p.is_symlink() or not p.resolve().is_relative_to(root): continue
 cache={line.split('=',1)[0].split(':',1)[0]:line.split('=',1)[1] for line in p.read_text(errors='replace').splitlines() if '=' in line and ':' in line.split('=',1)[0]}
 if pathlib.Path(cache.get('CMAKE_HOME_DIRECTORY','/nonexistent')).resolve()==root: roots.append(p.parent)
if len(roots)!=1: raise SystemExit('Expected one actual top-level CMake build directory; observed '+str(roots))
subprocess.run(['ctest','--test-dir',str(roots[0]),'-j1','--output-on-failure','--no-tests=error'],check=True)
"""


def cmake_roots(root: Path) -> list[Path]:
    result = []
    for p in sorted(root.rglob("CMakeCache.txt")):
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            continue
        cache = dict(line.split("=", 1) for line in p.read_text(errors="replace").splitlines() if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL="))
        if cache.get("CMAKE_HOME_DIRECTORY:INTERNAL") in {"/workspace/repo", str(root.resolve())}:
            result.append(p.parent)
    return result


def resolve_author_tests(root, reference):
    """保留原任务的测试适用性；实际顶层CMake配置优先选择作者CTest。"""
    if not reference.author_tests or not cmake_roots(root):
        return reference.author_tests, dict(route="reference", reason="无实际顶层CMake配置，沿用作者固定入口")
    step = PlanStep(
        step_id="author-check",
        role="smoke",
        command="export CTEST_PARALLEL_LEVEL=1\npython3 -c " + shlex.quote(CTEST_SCRIPT),
        source="实际顶层CMakeCache与作者CTest注册；" + "; ".join(s.source for s in reference.author_tests),
        expected="运行当前构建配置注册的全部作者CTest，零测试或任何失败均不通过",
        required_output=("100% tests passed",),
    )
    return (step,), dict(route="actual_cmake_ctest", build_directories=[p.relative_to(root).as_posix() for p in cmake_roots(root)], zero_tests="error", coverage="作者在当前配置中注册的全部测试；不声称与其他构建系统测试集逐项相同")
