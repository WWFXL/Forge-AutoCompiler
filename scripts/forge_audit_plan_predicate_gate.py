"""独立stdlib核验；不导入生成器、Workflow或执行器，不写原始目录。"""

import datetime
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2])


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def canonical(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load(p):
    return json.loads(p.read_text())


rows = []
for folder, dirs, files in os.walk(ROOT, followlinks=False):
    for name in sorted(dirs + files):
        p = Path(folder) / name
        rel = p.relative_to(ROOT).as_posix()
        if rel in ("inventory.json", "seal.json"):
            continue
        mode = p.lstat().st_mode
        if stat.S_ISLNK(mode):
            target = os.readlink(p)
            raw = os.fsencode(target)
            rows.append(dict(path=rel, type="symlink", target=target, size=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        elif stat.S_ISREG(mode):
            rows.append(dict(path=rel, type="file", size=p.stat().st_size, sha256=sha(p)))
        else:
            assert stat.S_ISDIR(mode), p
rows.sort(key=lambda r: r["path"])
sealed = load(ROOT / "seal.json")
assert rows == load(ROOT / "inventory.json")
assert canonical(rows) == sealed["inventory_canonical_sha256"]
protocol = load(ROOT / "protocol.json")
assert sealed["identity"] == protocol["identity"] == "cpp-build-plan-predicate-qualification-v2"
assert protocol["provider_calls"] == protocol["max_new_provider_cost_usd"] == 0
for name, expected in protocol["components"].items():
    assert sha(ROOT / "source-snapshot" / name) == expected, name
result = load(ROOT / "result.json")
assert not result["not_observed"] and result["stop_reason"] is None
assert len(result["arms"]) == len(protocol["schedule"]) == 14
summary = []
projects = {p["name"]: p for p in protocol["projects"]}
tails = {}
for slot, row in zip(protocol["schedule"], result["arms"]):
    item = projects[slot["project"]]
    assert all(row[k] == v for k, v in slot.items())
    folder = ROOT / (row["name"] + "-plan")
    task = item["task"]
    assert sha(Path(item["source_archive"])) == task["source_archive_sha256"]
    usage = row["agent_usage"]
    for key in ("recorded_tokens", "input_tokens", "output_tokens", "unknown_usage_requests", "estimated_cost_usd_completed_responses"):
        assert usage[key] == 0, (item["name"], key)
    events = [json.loads(line) for line in (folder / "agent/events.jsonl").read_text().splitlines()] if (folder / "agent/events.jsonl").exists() else []
    phases = [e["phase"] for e in events if e["event"] == "unified.agent"]
    case = slot["case"]
    is_tool = slot["method"] == "tool_plan_workflow"
    recovery = case in ("command_recovery", "stdout_path_repair", "no_change_correction", "missing_path_rejected")
    expected_phases = ([] if is_tool else ["initial"]) + (["recovery"] if recovery else [])
    assert phases == expected_phases
    expected_requests = {"legacy_field_correction": 2, "stage_order_correction": 2, "no_change_correction": 3, "missing_path_rejected": 2}.get(case, len(phases))
    assert usage["model_requests"] == expected_requests
    for event in ("model.request_started", "model.request_completed"):
        assert sum(e["event"] == event for e in events) == expected_requests
    rejected = [e for e in events if e["event"] == "observed.proposal_rejected"]
    assert len(rejected) == (2 if case == "missing_path_rejected" else int(case in ("legacy_field_correction", "stage_order_correction", "no_change_correction")))
    for i in range(1, expected_requests + 1):
        response = load(folder / f"agent/response-{i}.json")
        assert all(m["response_metadata"]["model_name"] == "scripted-gate" and m["usage_metadata"]["total_tokens"] == 0 for m in response if m["type"] == "ai")
        assert (folder / f"agent/request-{i}.json").is_file()
    paths = list(folder.glob(".compile-sessions/*/*/session.json"))
    assert len(paths) == 1
    session_path = paths[0]
    session = load(session_path)
    assert session["commit_sha"] == task["commit_sha"] and session["image_id"] == task["image_id"]
    assert session["parallel_jobs"] == 2
    frozen = load(folder / "original-source-hashes.json")
    workspace = Path(session["leadagent_repo_dir"])
    changed = [n for n, s in frozen.items() if not (workspace / n).is_file() or sha(workspace / n) != s]
    if changed:
        classification = load(folder / "physical-cleanup-classification.json")
        assert classification["source_contract_rejected"] and classification["physical_cleanup_succeeded"]
        assert sorted(changed) == sorted(classification["changed_original_paths"]) and not row["strict_completed"]
    plan = load(folder / "agent/plan-1.json")
    receipt_path = folder / "agent/tool-receipt.json"
    if receipt_path.exists():
        receipt = load(receipt_path)
        assert receipt["plan_sha256"] == canonical(plan) and receipt["provider_calls"] == 0
        for x in receipt["source_reads"]:
            assert frozen[x["path"]] == x["sha256"]
    tail = [s for s in plan["steps"] if s["role"] in ("smoke", "artifact_stage")]
    key = item["name"]
    if key in tails:
        assert tails[key] == tail
    tails[key] = tail
    workflow_events = [json.loads(s) for s in (session_path.parent / "logs/workflow.log").read_text().splitlines()]
    revisions = [e for e in workflow_events if e["event"] == "plan.revised"]
    if recovery and case != "missing_path_rejected":
        assert len(revisions) == 1 and revisions[0]["revision"] == 2
        second = load(folder / "agent/plan-2.json")
        assert [s for s in second["steps"] if s["role"] in ("smoke", "artifact_stage")] == tail
        assert sum(s["status"] == "needs_handoff" for s in row["transitions"]) == 1
        if case in ("command_recovery", "no_change_correction"):
            assert revisions[0]["retained_steps"] == ["gate-configure"]
            assert sum(c["role"] == "configure" and c["command"] == "true" for c in session["commands"]) == 1
            assert any(c["role"] == "build" and c["exit_code"] != 0 for c in session["commands"])
        else:
            assert revisions[0]["retained_steps"] == []
            before_build = next(s for s in plan["steps"] if s["role"] == "build")
            after_build = next(s for s in second["steps"] if s["role"] == "build")
            assert before_build["command"] == after_build["command"]
            assert before_build["required_output"] == ["/workspace/repo/test"] and after_build["required_output"] == []
            failed_steps = [e for e in workflow_events if e["event"] == "plan.step" and not e["expected_satisfied"]]
            assert len(failed_steps) == 1
            failed = next(c for c in session["commands"] if c["command_id"] == failed_steps[0]["command_id"])
            assert failed["exit_code"] == 0
            assert "files_exist" in json.dumps(load(folder / "agent/observed-actions-2-0.json"))
    else:
        assert not revisions
    assert row["strict_completed"] == (case != "missing_path_rejected")
    if case == "missing_path_rejected":
        assert row["error_class"] == "PlanContractError" and "no_execution_change" in row["error_message"]
        assert len(session["commands"]) == 1 and session["commands"][0]["exit_code"] == 86
        assert not session["replay_attempts"]
        assert sum(s["status"] == "needs_handoff" for s in row["transitions"]) == 1
    expected = []
    for step in task["verification_steps"]:
        normalized = {"workdir": "/workspace/repo", "requires": [], "required_output": [], "diagnostic_paths": []}
        normalized.update(step)
        expected.append(normalized)
    assert [s for s in plan["steps"] if s["role"] == "smoke"] == expected
    assert plan["artifact_paths"] == task["artifact_paths"]
    assert "FORGE_UNIFIED_STAGED" in plan["steps"][-1]["command"]
    fixed_results = []
    for step in expected:
        matches = [c for c in session["commands"] if c["role"] == "smoke" and c["command"] == step["command"] and c["workdir"] == step["workdir"]]
        if not matches:
            fixed_results.append(None)
        else:
            c = matches[-1]
            text = Path(c["log_path"]).read_text(errors="replace")
            fixed_results.append(c["exit_code"] == 0 and not c["timed_out"] and all(marker in text for marker in step["required_output"]))
    build = any(c["role"] == "build" and c["exit_code"] == 0 and not c["timed_out"] for c in session["commands"])
    stage = any(c["role"] == "artifact_stage" and c["exit_code"] == 0 and not c["timed_out"] for c in session["commands"])
    refs = {session["container_id"], session["container_name"]}
    for replay in session["replay_attempts"]:
        refs.update(replay[k] for k in ("container_id", "container_name") if replay.get(k))
    for ref in sorted(refs):
        check = subprocess.run(["docker", "inspect", "--type", "container", ref], capture_output=True, text=True, timeout=15)
        assert check.returncode == 1 and ("No such container" in check.stderr or "No such object" in check.stderr), ref
    logevents = [json.loads(line) for line in (session_path.parent / "logs/workflow.log").read_text().splitlines()]
    assert any(e["event"] == "container.cleanup.removed" and e.get("exit_code") == 0 and e.get("session_id") == session["session_id"] for e in logevents)
    assert any(e["event"] == "finalize.completed" and e.get("session_id") == session["session_id"] for e in logevents)
    assert row["cleanup"]["succeeded"]
    if row["strict_completed"]:
        assert not changed and session["status"] == "completed" and row["status"] == "verified"
        assert build and stage and all(x is True for x in fixed_results)
        assert session["verification"]["status"] == "passed" and all(c["passed"] for c in session["verification"]["checks"])
        assert len(session["replay_attempts"]) == 1
        replay = session["replay_attempts"][0]
        assert replay["status"] == "passed" and replay["cleanup_succeeded"] and replay["image_id"] == task["image_id"] and replay["commit_sha"] == task["commit_sha"]
        assert replay["exit_code"] == replay["verification_exit_code"] == 0
        assert all(c["passed"] for c in replay["checks"])
        replay_root = session_path.parent / "replay" / replay["attempt_id"]
        assert sha(replay_root / "recipe/source.tar") == task["source_archive_sha256"]
        build_script = (replay_root / "recipe/build.sh").read_text()
        final_plan = load(folder / f"agent/plan-{2 if recovery else 1}.json")
        assert all(step["command"] in build_script for step in final_plan["steps"] if step["role"] != "smoke")
        verify_script = (replay_root / "recipe/verify.sh").read_text()
        assert all(s["command"] in verify_script for s in expected)
        replay_output = (replay_root / "logs/verify.log").read_text(errors="replace")
        assert all(marker in replay_output for step in expected for marker in step["required_output"])
        original_artifacts = Path(session["leadagent_artifacts_dir"])
        original_names = sorted(p.relative_to(original_artifacts).as_posix() for p in original_artifacts.rglob("*") if p.is_file())
        replay_names = sorted(p.relative_to(replay_root / "artifacts").as_posix() for p in (replay_root / "artifacts").rglob("*") if p.is_file())
        assert original_names == replay_names == sorted(task["artifact_paths"])
        assert len(replay["artifacts"]) == len(task["artifact_paths"])
        for artifact in replay["artifacts"]:
            n = artifact["path"]
            assert sha(original_artifacts / n) == sha(replay_root / "artifacts" / n) == artifact["expected_sha256"] == artifact["actual_sha256"]
            assert artifact["passed"] and artifact["type_matches"] and artifact["size_matches"] and artifact["smoke_matches"]
    else:
        if row.get("error_class") == "ToolPlanNeedsAgent":
            assert (folder / "agent/qualification-needs-agent.json").exists()
        else:
            assert row.get("error_class") == "PlanContractError" or session["verification"]["status"] != "passed"
    summary.append(
        {
            "name": item["name"],
            "generated": True,
            "strict_completed": row["strict_completed"],
            "build_success_recorded": build,
            "fixed_test_results": fixed_results,
            "stage_success_recorded": stage,
            "replay_attempts": len(session["replay_attempts"]),
            "error_class": row.get("error_class"),
            "scripted_model_requests": usage["model_requests"],
            "case": slot["case"],
            "method": slot["method"],
            "total_seconds": row["arm_total_wall_seconds"],
            "commands": len(session["commands"]),
            "absent_containers": sorted(refs),
            "source_unchanged": not changed,
        }
    )
output = {
    "valid": True,
    "identity": protocol["identity"],
    "inventory_sha256": sealed["inventory_canonical_sha256"],
    "files": sealed["files"],
    "symlinks": sealed["symlinks"],
    "bytes": sealed["bytes"],
    "provider_calls": 0,
    "scripted_model_requests": sum(r["agent_usage"]["model_requests"] for r in result["arms"]),
    "tokens": 0,
    "estimated_cost_usd": 0,
    "observed": len(summary),
    "strict_completed": sum(x["strict_completed"] for x in summary),
    "rows": summary,
    "implementation_sha256": sha(Path(__file__)),
    "verified_utc": datetime.datetime.now(datetime.UTC).isoformat(),
}
with OUT.open("x") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(json.dumps(output, ensure_ascii=False, indent=2))
