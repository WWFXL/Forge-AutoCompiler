"""来源资格必须同时满足真实验收、清理和原始源码完整性。"""

import importlib.util
import json
import tarfile
from pathlib import Path

import pytest

from deerflow.compile.plan_workflow import PlanContractError

spec = importlib.util.spec_from_file_location("source_qualification", Path(__file__).resolve().parents[2] / "scripts/forge_build_plan_source_qualification.py")
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


def test_original_archive_and_later_source_change_reject_claimed_success(tmp_path):
    folder = tmp_path / "run"
    session = folder / ".compile-sessions/thread/session"
    source = session / "workspace/repo"
    source.mkdir(parents=True)
    (source / "program.c").write_text("int x;\n")
    archive_path = tmp_path / "source.tar"
    with tarfile.open(archive_path, "w") as archive:
        archive.add(source / "program.c", arcname="program.c")
    frozen = qualification.original_files(archive_path)
    (session / "session.json").write_text(json.dumps({"session_id": "session", "commands": [], "replay_attempts": []}))
    (folder / "result.json").write_text(json.dumps({"status": "verified", "session_status": "completed", "cleanup": {"succeeded": True}, "provider_calls": 0, "runtime_agent_calls": 0}))
    assert qualification.inspect_result(folder, frozen)["qualified"]
    (source / "program.c").write_text("int altered;\n")
    result = qualification.inspect_result(folder, frozen)
    assert not result["qualified"] and not result["fixed_source_files_unchanged"]


@pytest.mark.parametrize("changes", [{"provider_calls": 1}, {"identity": "other"}])
def test_nonzero_provider_or_wrong_identity_stops_before_any_source_execution(changes):
    with pytest.raises(PlanContractError, match="边界"):
        qualification.validate({"identity": "cpp-build-plan-source-qualification-v2", "provider_calls": 0, **changes})
