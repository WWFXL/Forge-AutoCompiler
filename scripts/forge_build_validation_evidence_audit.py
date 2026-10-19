#!/usr/bin/env python3
"""冻结构建证据的回顾性分层审计；不执行Docker或Provider。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


class FrozenInput:
    """核对inventory绑定与所有实际消费文件，不代替旧阶段全量独立审计。"""

    def __init__(self, spec):
        self.root = Path(spec["root"])
        inventory = json.loads((self.root / "inventory.json").read_text())
        canonical = sha(json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        if canonical != spec["inventory_sha256"] or json.loads((self.root / "seal.json").read_text())["inventory_canonical_sha256"] != canonical:
            raise ValueError("冻结输入inventory身份不符")
        self.index = {row["path"]: row for row in inventory}
        self.consumed = {}
        for filename, key in (("protocol.json", "protocol_sha256"), ("result.json", "result_sha256")):
            if sha(self.read(filename)) != spec[key]:
                raise ValueError("冻结协议或原始结果变化")

    def read(self, relative):
        relative = Path(relative).as_posix()
        entry = self.index.get(relative)
        if entry is None or entry["type"] != "file":
            raise ValueError("输入文件不在冻结普通文件清单中")
        path = self.root / relative
        if path.is_symlink():
            raise ValueError("输入普通文件变为链接")
        data = path.read_bytes()
        if len(data) != entry["size"] or sha(data) != entry["sha256"]:
            raise ValueError("输入文件内容偏离冻结inventory")
        self.consumed[relative] = entry["sha256"]
        return data

    def json(self, relative):
        return json.loads(self.read(relative))


def layer_observations(session, task, logs, *, source_unchanged, artifact_paths, cleanup):
    """中间层来自实际记录；终态不用于反推未观察层。"""
    commands = session["commands"]
    builds = [c for c in commands if c["role"] == "build"]
    build = "not_observed" if not builds else "passed" if builds[-1]["exit_code"] == 0 and not builds[-1]["timed_out"] else "failed"
    test_rows = []
    for step in task["verification_steps"]:
        matches = [(i, c) for i, c in enumerate(commands) if (c["command"], c["workdir"], c["role"]) == (step["command"], step.get("workdir", "/workspace/repo"), "smoke")]
        state, record = "not_observed", None
        reason = "no_exact_test_record"
        if matches:
            index, record = matches[-1]
            text = logs.get(record["command_id"], "")
            stale = any(c["role"] in ("dependency", "configure", "build") for c in commands[index + 1 :])
            state = "passed" if record["exit_code"] == 0 and not record["timed_out"] and all(marker in text for marker in step["required_output"]) and not stale else "failed"
            reason = "fresh_complete_test" if state == "passed" else "stale_after_environment_or_build" if stale else "exit_timeout_or_fixed_output_missing"
        test_rows.append({"command": step["command"], "state": state, "reason": reason, "command_id": record["command_id"] if record else None})
    test_states = [row["state"] for row in test_rows]
    tests = "failed" if "failed" in test_states else "not_observed" if "not_observed" in test_states else "passed"
    staged = any(c["role"] == "artifact_stage" for c in commands) or bool(session.get("verification"))
    artifacts = ("passed" if set(artifact_paths) == set(task["artifact_paths"]) else "failed") if staged else "not_observed"
    attempts = session.get("replay_attempts", [])
    replay = "not_observed"
    if attempts:
        last = attempts[-1]
        replay = "passed" if last["status"] == "passed" and last["cleanup_succeeded"] and last.get("verification_exit_code") == 0 and all(check["passed"] for check in last["checks"]) else "failed"
    return {
        "latest_build_exit": build,
        "fixed_full_tests": tests,
        "exact_artifact_set": artifacts,
        "original_source_files": "passed" if source_unchanged else "failed",
        "clean_replay": replay,
        "recorded_cleanup": "passed" if cleanup else "failed",
        "fixed_tests_detail": test_rows,
        "replay_attempts": [{"attempt_id": a["attempt_id"], "status": a["status"], "failure_classification": a.get("failure_classification"), "failed_checks": [c["name"] for c in a["checks"] if not c["passed"]]} for a in attempts],
    }


LAYERS = ("latest_build_exit", "fixed_full_tests", "exact_artifact_set", "original_source_files", "clean_replay", "recorded_cleanup")


def analyze_cohort(spec):
    frozen = FrozenInput(spec)
    protocol, result = frozen.json("protocol.json"), frozen.json("result.json")
    rows = result[spec["rows_key"]]
    identifiers = [{"name": row["name"], **({"arm": row["arm"]} if "arm" in row else {})} for row in rows]
    if result["identity"] != spec["identity"] or identifiers != spec["rows"]:
        raise ValueError("回顾队列身份或行顺序变化")
    project_specs = {row["name"]: row for row in protocol.get("projects", protocol.get("cases", []))}
    output = []
    for row in rows:
        folder = row["name"] + ("-" + row["arm"] if "arm" in row else "")
        project = project_specs[row.get("project", row["name"])]
        task = project.get("task")
        if task is None:
            plan = project["plan"]
            task = {"artifact_paths": plan["artifact_paths"], "verification_steps": [s for s in plan["steps"] if s["role"] == "smoke"]}
        metadata = [name for name in frozen.index if name.startswith(folder + "/.compile-sessions/") and name.endswith("/session.json")]
        if len(metadata) != 1:
            raise ValueError("没有唯一权威Session")
        session_path = Path(metadata[0])
        session_root = session_path.parent
        session = frozen.json(session_path)
        logs = {}
        for command in session["commands"]:
            if command["role"] == "smoke":
                logs[command["command_id"]] = frozen.read(session_root / "logs" / Path(command["log_path"]).name).decode(errors="replace")
        original = frozen.json(Path(folder) / "original-source-hashes.json")
        changed = []
        for name, expected in original.items():
            key = (session_root / "workspace/repo" / name).as_posix()
            if key not in frozen.index or frozen.index[key]["type"] != "file" or sha(frozen.read(key)) != expected:
                changed.append(name)
        prefix = (session_root / "artifacts").as_posix() + "/"
        artifacts = [name[len(prefix) :] for name in frozen.index if name.startswith(prefix)]
        layers = layer_observations(session, task, logs, source_unchanged=not changed, artifact_paths=artifacts, cleanup=row["cleanup"]["succeeded"])
        original_outcome = row["strict_completed"] if "strict_completed" in row else row.get("qualified", row["status"] == "verified" and row["session_status"] == "completed")
        output.append(
            {
                "name": row["name"],
                "arm": row.get("arm"),
                "control": row.get("control"),
                "session_status": session["status"],
                "original_endpoint_passed": original_outcome,
                "layers": layers,
                "changed_original_files": changed,
                "evidence_session": metadata[0],
                "artifact_paths": artifacts,
                "explicit_failed_layers": [name for name in LAYERS if layers[name] == "failed"],
                "successful_build_but_original_endpoint_not_passed": layers["latest_build_exit"] == "passed" and not original_outcome,
            }
        )
    return {
        "identity": spec["identity"],
        "kind": spec["kind"],
        "root": spec["root"],
        "inventory_sha256": spec["inventory_sha256"],
        "rows": output,
        "layer_counts": {name: dict(Counter(row["layers"][name] for row in output)) for name in LAYERS},
        "consumed_files": frozen.consumed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if protocol["identity"] != "cpp-build-validation-evidence-audit-v1" or protocol["provider_calls"] != 0 or protocol["docker_runs"] != 0 or not protocol["results_previously_observed"]:
        raise ValueError("回顾分析边界不符")
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    results = {
        "identity": protocol["identity"],
        "kind": protocol["kind"],
        "protocol_sha256": sha(args.protocol.read_bytes()),
        "analysis_code_sha256": sha(Path(__file__).read_bytes()),
        "input_verification_scope": "核对inventory绑定及全部消费文件；不重新执行旧全量审计或构建",
        "cohorts": [],
    }
    for spec in protocol["cohorts"]:
        results["cohorts"].append(analyze_cohort(spec))
    with (root / "result.json").open("x") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"identity": results["identity"], "rows": sum(len(c["rows"]) for c in results["cohorts"]), "provider_calls": 0, "docker_runs": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
