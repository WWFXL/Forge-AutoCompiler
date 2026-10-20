"""独立stdlib调度门禁核验，不导入执行器或Workflow，不写原证据。"""

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def audit(root):
    actual = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            p = Path(directory) / name
            rel = p.relative_to(root).as_posix()
            if rel in ("inventory.json", "seal.json"):
                continue
            mode = p.lstat().st_mode
            if stat.S_ISLNK(mode):
                target = os.readlink(p)
                actual.append(
                    dict(
                        path=rel,
                        type="symlink",
                        target=target,
                        size=len(os.fsencode(target)),
                        sha256=hashlib.sha256(os.fsencode(target)).hexdigest(),
                    )
                )
            elif stat.S_ISREG(mode):
                actual.append(
                    dict(path=rel, type="file", size=p.stat().st_size, sha256=sha(p))
                )
            else:
                assert stat.S_ISDIR(mode)
    actual.sort(key=lambda r: r["path"])
    sealed = load(root / "seal.json")
    assert (
        actual == load(root / "inventory.json")
        and canonical(actual) == sealed["inventory_canonical_sha256"]
    )
    protocol, result = load(root / "protocol.json"), load(root / "result.json")
    assert (
        protocol["identity"]
        == result["identity"]
        == sealed["identity"]
        == "cpp-build-observed-plan-dispatch-gate-v1"
    )
    assert (
        protocol["provider_calls"]
        == protocol["max_new_provider_cost_usd"]
        == sealed["unknown_usage_requests"]
        == 0
    )
    assert not result["not_observed"] and result["stop_reason"] is None
    assert (
        len(protocol["projects"]) == 1 and protocol["projects"][0]["name"] == "buffer"
    )
    assert len(result["arms"]) == len(protocol["schedule"]) == 3
    assert [s["method"] for s in protocol["schedule"]] == [
        "tool_plan_workflow",
        "model_plan_workflow",
        "strong_tool_agent",
    ]
    for name, expected in protocol["components"].items():
        assert sha(root / "source-snapshot" / name) == expected
    task = protocol["projects"][0]["task"]
    assert (
        sha(Path(protocol["projects"][0]["source_archive"]))
        == task["source_archive_sha256"]
    )
    rows, tails = [], []
    for slot, row in zip(protocol["schedule"], result["arms"], strict=True):
        assert (
            all(row[k] == v for k, v in slot.items())
            and row["strict_completed"]
            and row["cleanup"]["succeeded"]
        )
        tool = slot["method"] == "strong_tool_agent"
        folder = root / (row["name"] + ("-tool" if tool else "-plan"))
        usage = row["agent_usage"]
        assert all(
            usage[k] == 0
            for k in (
                "input_tokens",
                "output_tokens",
                "recorded_tokens",
                "unknown_usage_requests",
                "estimated_cost_usd_completed_responses",
            )
        )
        count = int(slot["method"] != "tool_plan_workflow")
        assert usage["model_requests"] == count
        events = [
            json.loads(s)
            for s in (folder / "agent/events.jsonl").read_text().splitlines()
        ]
        for event in ("model.request_started", "model.request_completed"):
            assert sum(e["event"] == event for e in events) == count
        if count:
            messages = load(folder / "agent/response-1.json")
            assert all(
                m["response_metadata"]["model_name"] == "scripted-gate"
                and m["usage_metadata"]["total_tokens"] == 0
                for m in messages
                if m["type"] == "ai"
            )
            calls = [c for m in messages if m["type"] == "ai" for c in m["tool_calls"]]
            assert ("submit_verified_build" if tool else "ObservedBuildActions") in [
                c["name"] for c in calls
            ]
            if tool:
                assert (
                    next(
                        c["args"] for c in calls if c["name"] == "submit_verified_build"
                    )
                    == {}
                )
        paths = list(folder.glob(".compile-sessions/*/*/session.json"))
        assert len(paths) == 1
        session_path = paths[0]
        session = load(session_path)
        assert (
            session["status"] == "completed"
            and session["commit_sha"] == task["commit_sha"]
            and session["image_id"] == task["image_id"]
            and session["parallel_jobs"] == 2
        )
        original = load(folder / "original-source-hashes.json")
        workspace = Path(session["leadagent_repo_dir"])
        assert all(
            (workspace / n).is_file() and sha(workspace / n) == h
            for n, h in original.items()
        )
        assert any(
            c["role"] == "build" and c["exit_code"] == 0 for c in session["commands"]
        )
        for step in task["verification_steps"]:
            matches = [
                c
                for c in session["commands"]
                if c["role"] == "smoke"
                and c["command"] == step["command"]
                and c["workdir"] == step.get("workdir", "/workspace/repo")
            ]
            assert (
                matches
                and matches[-1]["exit_code"] == 0
                and not matches[-1]["timed_out"]
            )
            assert all(
                marker in Path(matches[-1]["log_path"]).read_text()
                for marker in step.get("required_output", [])
            )
        if not tool:
            plan = load(folder / "agent/plan-1.json")
            tails.append(
                [s for s in plan["steps"] if s["role"] in ("smoke", "artifact_stage")]
            )
            assert plan["artifact_paths"] == task["artifact_paths"]
        assert session["verification"]["status"] == "passed" and all(
            c["passed"] for c in session["verification"]["checks"]
        )
        assert len(session["replay_attempts"]) == 1
        replay = session["replay_attempts"][0]
        assert (
            replay["status"] == "passed"
            and replay["cleanup_succeeded"]
            and replay["image_id"] == task["image_id"]
            and replay["commit_sha"] == task["commit_sha"]
        )
        assert replay["exit_code"] == replay["verification_exit_code"] == 0 and all(
            c["passed"] for c in replay["checks"]
        )
        replay_root = session_path.parent / "replay" / replay["attempt_id"]
        assert sha(replay_root / "recipe/source.tar") == task["source_archive_sha256"]
        verify_script = (replay_root / "recipe/verify.sh").read_text()
        verify_output = (replay_root / "logs/verify.log").read_text()
        assert all(
            s["command"] in verify_script
            and all(v in verify_output for v in s.get("required_output", []))
            for s in task["verification_steps"]
        )
        artifacts = Path(session["leadagent_artifacts_dir"])

        def names(path):
            return sorted(
                p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()
            )

        assert (
            names(artifacts)
            == names(replay_root / "artifacts")
            == sorted(task["artifact_paths"])
        )
        for artifact in replay["artifacts"]:
            assert (
                sha(artifacts / artifact["path"])
                == sha(replay_root / "artifacts" / artifact["path"])
                == artifact["expected_sha256"]
                == artifact["actual_sha256"]
            )
            assert (
                artifact["passed"]
                and artifact["type_matches"]
                and artifact["size_matches"]
                and artifact["smoke_matches"]
            )
        references = {session["container_id"], session["container_name"]}
        references.update(
            replay[k] for k in ("container_id", "container_name") if replay.get(k)
        )
        for ref in references:
            check = subprocess.run(
                ["docker", "inspect", "--type", "container", ref],
                capture_output=True,
                text=True,
                timeout=15,
            )
            assert check.returncode == 1 and (
                "No such container" in check.stderr or "No such object" in check.stderr
            )
        workflow = [
            json.loads(s)
            for s in (session_path.parent / "logs/workflow.log")
            .read_text()
            .splitlines()
        ]
        assert any(
            e["event"] == "container.cleanup.removed" and e.get("exit_code") == 0
            for e in workflow
        )
        assert any(e["event"] == "finalize.completed" for e in workflow)
        rows.append(
            dict(
                method=slot["method"],
                strict_completed=True,
                requests=count,
                commands=len(session["commands"]),
                absent_containers=sorted(references),
                seconds=row["arm_total_wall_seconds"],
            )
        )
    assert tails[0] == tails[1]
    return dict(
        valid=True,
        identity=protocol["identity"],
        inventory_sha256=sealed["inventory_canonical_sha256"],
        strict_completed=3,
        observed=3,
        provider_calls=0,
        tokens=0,
        cost_usd=0,
        scripted_model_requests=2,
        files=sealed["files"],
        symlinks=sealed["symlinks"],
        bytes=sealed["bytes"],
        rows=rows,
        implementation_sha256=sha(Path(__file__)),
    )


if __name__ == "__main__":
    result = audit(Path(sys.argv[1]).resolve())
    with Path(sys.argv[2]).open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
