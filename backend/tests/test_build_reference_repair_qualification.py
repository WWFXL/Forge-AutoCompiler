"""参考修复只改预定命令，失败和未观察后缀不得被替换。"""

import copy
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
spec = importlib.util.spec_from_file_location("reference_repair_qualification", Path(__file__).resolve().parents[2] / "scripts/forge_build_reference_repair_qualification.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def original():
    return [
        {
            "name": name,
            "source_archive": "/fixed/source.tar",
            "plan": {
                "commit_sha": "a" * 40,
                "artifact_paths": ["lib.a"],
                "steps": [
                    {"role": "configure", "command": "cmake -S . -B build -DBUILD_TESTS=ON"},
                    {"role": "build", "command": "cmake --build build"},
                    {"role": "smoke", "command": "ctest --test-dir build --no-tests=error", "required_output": ["100% tests passed"]},
                    {"role": "artifact_stage", "command": "cp build/old.a /artifacts/lib.a"},
                ],
            },
        }
        for name in repair.NAMES
    ]


def test_only_two_designated_commands_change_without_mutating_parent():
    parent = original()
    frozen = copy.deepcopy(parent)
    revised = repair.repaired_projects(parent)
    assert parent == frozen
    for old, new in zip(parent, revised):
        restored = copy.deepcopy(new)
        for before, after in zip(old["plan"]["steps"], restored["plan"]["steps"]):
            after["command"] = before["command"]
        assert restored == old
    assert revised[0]["plan"]["steps"][-1]["command"] == "cp build/libpng.a /artifacts/libpng.a"
    assert revised[1]["plan"]["steps"][0]["command"].endswith(" -DBUILD_DOC=OFF")


def protocol():
    return {"projects": original(), "deadline_utc": "2026-10-19T22:45:00Z", "new_project_reserve_seconds": 1800}


def test_measured_failure_does_not_replace_project_or_stop_later_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(repair, "before_deadline", lambda *args: None)
    observed = []

    def execute(item, folder, settings):
        observed.append(item["name"])
        return {"name": item["name"], "qualified": False, "cleanup": {"succeeded": True}}

    rows, unobserved, reason = repair.execute_schedule(protocol(), tmp_path, execute)
    assert observed == repair.NAMES and len(rows) == 2 and not unobserved and reason is None


def test_cleanup_failure_stops_and_preserves_unobserved_suffix(monkeypatch, tmp_path):
    monkeypatch.setattr(repair, "before_deadline", lambda *args: None)
    rows, unobserved, reason = repair.execute_schedule(protocol(), tmp_path, lambda item, *args: {"name": item["name"], "qualified": False, "cleanup": {"succeeded": False}})
    assert len(rows) == 1 and unobserved == [{"name": "libzip", "status": "not_observed", "reason": "cleanup_or_infrastructure_failure"}]
    assert reason == "cleanup_or_infrastructure_failure"


def test_deadline_stops_before_execution_and_does_not_fill_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(repair, "before_deadline", lambda *args: (_ for _ in ()).throw(ValueError("deadline")))
    rows, unobserved, reason = repair.execute_schedule(protocol(), tmp_path, lambda *args: (_ for _ in ()).throw(AssertionError("不应执行")))
    assert not rows and [item["name"] for item in unobserved] == repair.NAMES
    assert reason == "deadline_reservation" and all(item["status"] == "not_observed" for item in unobserved)
