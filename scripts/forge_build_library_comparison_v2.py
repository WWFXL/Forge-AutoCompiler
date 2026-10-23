#!/usr/bin/env python3
"""补齐原默认示例的共同任务义务与可执行裁判；旧接口遗漏证据不回填。"""

from __future__ import annotations

import copy
import shlex
import signal
from pathlib import Path
from unittest.mock import patch

import forge_build_library_comparison as previous

base, bounded = previous.base, previous.bounded
IDENTITY = "cpp-build-library-strategy-comparison-v2"
EXAMPLES = ("add_section/add_section", "anonymizer/anonymizer", "arion/arion", "arioso/arioso", "elfdump/elfdump", "elfio_ldd/elfio-ldd", "proc_mem/proc_mem", "tutorial/tutorial", "write_obj/write_obj", "writer/writer")


def scope_command():
    script = (
        "from pathlib import Path; import json,hashlib\n"
        "cache=Path('build/CMakeCache.txt').read_text().splitlines()\n"
        "assert 'ELFIO_BUILD_EXAMPLES:BOOL=ON' in cache\n"
        "rows=[]\n"
        f"for name in {EXAMPLES!r}:\n"
        " p=Path('build/examples')/name\n"
        " assert p.is_file() and p.read_bytes()[:4]==b'\\x7fELF',str(p)\n"
        " rows.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))\n"
        "print('FORGE_ELFIO_ORIGINAL_EXAMPLES 10',json.dumps(rows,sort_keys=True))\n"
    )
    return "python3 -c " + shlex.quote(script)


def complete_item(original, dependencies):
    item = copy.deepcopy(original)
    if item["name"] == "ELFIO":
        step = item["task"]["verification_steps"][0]
        step["command"] += "\n" + scope_command()
        step["required_output"].append("FORGE_ELFIO_ORIGINAL_EXAMPLES 10")
        item["source_paths"] += ["examples/CMakeLists.txt"]
    item["common_test_preparation"] = previous.common_obligation(item, dependencies)
    item["common_test_preparation"]["required_compilation_scope"] = (
        "ELFIO必须保持原默认示例构建开启，构建全部十个默认示例以及ELFIOTest；不得关闭ELFIO_BUILD_EXAMPLES；原73测试/74CTest全部执行。示例无需额外交付，精确交付仍ELFIOTest。"
        if item["name"] == "ELFIO" else
        "rang必须构建并运行原all_rang_tests/colorTest/envTermMissing三个程序，原六case默认执行；三个程序均精确交付。"
    )
    return item


def validate(candidate):
    if candidate["identity"] != IDENTITY or candidate["stage_max_cost_usd"] != "8.00":
        raise base.PlanContractError("完整义务独立身份或比较余量预算变化")
    parent_path = base.ROOT / "benchmarks/manifests/cpp-build-library-strategy-comparison-v1.json"
    if base.digest(parent_path) != candidate["parent_manifest_sha256"]:
        raise base.PlanContractError("旧比较身份变化")
    parent = base.load(parent_path)
    expected = []
    for item in parent["projects"]:
        record = next(q for q in candidate["qualification_evidence"] if q["name"] == item["name"])
        ref = base.load(Path(record["root"]) / "protocol.json")
        original = next(p for p in ref["projects"] if p["name"] == item["name"])
        expected.append(complete_item(item, original["dependencies"]))
    if candidate["projects"] != expected:
        raise base.PlanContractError("超出显式完整编译义务及裁判补齐范围")
    for item in candidate["projects"]:
        base.PlanTask.model_validate(item["task"])
    previous.validate({**candidate, "identity": previous.IDENTITY, "stage_max_cost_usd": "10.00", "projects": parent["projects"]})
    receipt = Path(candidate["full_reference_scope_audit_path"])
    if base.digest(receipt) != candidate["full_reference_scope_audit_sha256"] or not base.load(receipt)["valid"]:
        raise base.PlanContractError("原参考完整示例编译证据缺失")


def main():
    signal.signal(signal.SIGINT, bounded.request_stop)
    with (patch.object(base, "validate", validate),
          patch.object(base, "execution_window", bounded.execution_window),
          patch.object(base, "PreparationMeter", bounded.previous.QualifiedPreparationMeter),
          patch.object(base, "execute", bounded.execute),
          patch.object(base, "run_slot", previous.replication.run_slot)):
        return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
