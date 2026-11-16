#!/usr/bin/env python3
"""实际容器依赖诊断证据链；零Provider，不安装依赖或重复参考构建。"""

import argparse
import json
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

from forge_libffi_dependency_guidance import save
from forge_libffi_diagnostic_memory import IMAGE_ID, material

from deerflow.compile.dependency_diagnosis import DependencyDiagnosis
from deerflow.compile.plan_agent import PlanAgentLedger
from deerflow.compile.recovery_diagnostic_memory import RecoveryDiagnosticMemory
from deerflow.compile.recovery_environment import query_command

ROOT = Path(__file__).resolve().parents[1]


class ContainerQueries:
    """仅工程验证适配器；真实Workflow预算接线由针对性测试覆盖。"""

    def __init__(self, container, output, failure):
        self.container, self.output = container, output
        self.calls = 0
        self.handoff_id = "engineering-handoff"
        self.workflow = SimpleNamespace(handoff=dict(handoff_id=self.handoff_id, step_id="configure", recent_commands=[failure]))
        self.diagnostic_memory = RecoveryDiagnosticMemory()
        self.meter = SimpleNamespace(ledger=PlanAgentLedger(output / "queries"))

    def execute(self, operation, query, **options):
        command = query_command(operation, query, **options)
        if self.calls >= 12:
            return dict(status="budget_exhausted")
        self.calls += 1
        result = subprocess.run(["docker", "exec", self.container, "bash", "-c", command], capture_output=True, text=True, timeout=30)
        command_id = f"query-{self.calls}"
        log = self.output / f"{command_id}.log"
        log.write_text(result.stdout + result.stderr)
        data = json.loads(result.stdout) if result.returncode == 0 else dict(status="query_failed", output=(result.stdout + result.stderr)[-2000:])
        data.update(command_id=command_id, log_path=log.name, exit_code=result.returncode)
        self.meter.ledger.append("engineering.query", operation=operation, query=query, **options, result=data)
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    task, _, archive, _ = material()
    args.output.mkdir(parents=True, exist_ok=False)
    save(
        args.output / "scope.json", dict(identity="cpp-build-dependency-diagnosis-engineering-v1", authorization="用户批准实现及针对性验证", provider_calls=0, cost_usd=0, image_id=IMAGE_ID, source_archive_sha256=task.source_archive_sha256)
    )
    name = "forge-diagnosis-engineering-" + uuid.uuid4().hex[:12]
    container = None
    summary = dict(provider_calls=0, cost_usd=0, independent_project_effect=False)
    try:
        container = subprocess.check_output(["docker", "run", "-d", "--name", name, "--label", "forge.role=diagnosis-engineering", "--cpus", "2", "--entrypoint", "sleep", IMAGE_ID, "infinity"], text=True, timeout=30).strip()
        subprocess.run(["docker", "cp", str(archive), container + ":/tmp/source.tar"], check=True, timeout=30)
        subprocess.run(["docker", "exec", container, "bash", "-c", "mkdir -p /workspace/repo && tar -xf /tmp/source.tar -C /workspace/repo"], check=True, timeout=30)
        failure = subprocess.run(["docker", "exec", "-w", "/workspace/repo", container, "bash", "-c", "./autogen.sh"], capture_output=True, text=True, timeout=60)
        output = failure.stdout + failure.stderr
        (args.output / "autogen.log").write_text(output)
        assert failure.returncode != 0 and "possibly undefined macro: LT_SYS_SYMBOL_USCORE" in output
        environment = ContainerQueries(container, args.output, dict(command_id="autogen", log_path="autogen.log", role="configure", exit_code=failure.returncode, output_tail=output[-4000:]))
        diagnosis = DependencyDiagnosis(environment)
        diagnosis.prepare()
        first = environment.diagnostic_memory.snapshot(environment.workflow.handoff)
        save(args.output / "prepared-memory.json", first)
        assert any(c["package"] == "libltdl-dev" for c in first["candidates"])
        # 工程夹具指定候选，只验证查询证据，不伪称Agent自主选中了正确包。
        verified = diagnosis.diagnose("macro", "LT_SYS_SYMBOL_USCORE", candidate="libltdl-dev")
        save(args.output / "candidate-verification.json", verified)
        files = diagnosis.query("environment", "ltdl.m4", kind="package_file_search")
        assert "libltdl-dev" in files["result"].get("output", "")
        unrelated = diagnosis.diagnose("header", "zlib.h")
        assert "zlib1g-dev" in str(unrelated)
        final = environment.diagnostic_memory.snapshot(environment.workflow.handoff)
        save(args.output / "final-memory.json", final)
        save(args.output / "diagnosis.json", diagnosis.snapshot())
        candidate = next(c for c in final["candidates"] if c["package"] == "libltdl-dev")
        assert candidate["checks"]["package"]["installed"] is False
        summary.update(
            actual_queries=environment.calls,
            original_macro_failure_observed=True,
            candidate_discovered_by_component_search=True,
            fixture_candidate_verified_not_installed=True,
            macro_file_provider_found=True,
            unrelated_header_provider_found=True,
            build_not_run=True,
        )
    finally:
        if container:
            subprocess.run(["docker", "rm", "-f", container], check=True, capture_output=True, timeout=30)
        references = [v for v in (container, name) if v]
        absent = {v: subprocess.run(["docker", "inspect", v], capture_output=True, timeout=15).returncode != 0 for v in references}
        summary["cleanup"] = dict(references_absent=absent, succeeded=all(absent.values()))
        save(args.output / "summary.json", summary)
    assert summary["cleanup"]["succeeded"]
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
