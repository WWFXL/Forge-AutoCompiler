"""只验证新单次入口及付费前门禁，不冒充模型构建效果。"""

import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
entry = importlib.import_module("forge_libffi_index_autonomous")


def authorization(now):
    return dict(identity=entry.IDENTITY, maximum_cost_usd="1.00", user_authorized=True, deadline_utc=(now + timedelta(minutes=55)).isoformat())


@pytest.mark.parametrize(
    "change",
    [
        dict(identity="cpp-build-libffi-dependency-guidance-flash-v1"),
        dict(maximum_cost_usd="2.00"),
        dict(user_authorized=False),
        dict(user_authorized="true"),
        dict(deadline_utc="2020-01-01T00:00:00+00:00"),
        dict(deadline_utc="2099-01-01T00:00:00+00:00"),
        dict(deadline_utc="2026-11-16T12:00:00"),
    ],
)
def test_invalid_authorization_never_reaches_runtime_or_provider(tmp_path, monkeypatch, change):
    auth = authorization(datetime.now(UTC)) | change
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(auth))
    output = tmp_path / "formal-evidence"
    monkeypatch.setattr(sys, "argv", ["entry", "--authorization", str(path), "--output", str(output)])
    monkeypatch.setattr(entry, "material", lambda: (None, None, None, None))

    def forbidden(*args, **kwargs):
        pytest.fail("无有效授权不得访问Docker或创建Provider")

    monkeypatch.setattr(entry.subprocess, "run", forbidden)
    monkeypatch.setattr(entry, "PlanThinkingDeepSeek", forbidden)
    with pytest.raises(ValueError, match="授权"):
        entry.main()
    assert not output.exists()


def test_valid_single_run_authorization():
    now = datetime.now(UTC)
    entry.validate_authorization(authorization(now), now=now)


def test_default_cli_only_checks_material(monkeypatch, capsys):
    class Task:
        def model_dump(self, **kwargs):
            return {"name": "libffi"}

    monkeypatch.setattr(sys, "argv", ["entry"])
    monkeypatch.setattr(entry, "material", lambda: (Task(), None, None, None))

    def forbidden(*args, **kwargs):
        pytest.fail("默认入口不得创建Provider或检查Docker")

    monkeypatch.setattr(entry.subprocess, "run", forbidden)
    monkeypatch.setattr(entry, "PlanThinkingDeepSeek", forbidden)
    entry.main()
    result = json.loads(capsys.readouterr().out)
    assert result["identity"] == "cpp-build-libffi-index-autonomous-flash-v1"
    assert result["provider_calls"] == 0 and result["credentials_read"] is False


def test_material_only_changes_run_label_goal_and_query_image(tmp_path, monkeypatch):
    from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask

    # CI不依赖科研服务器归档；真实归档已由默认CLI单独核验。
    item = next(p for p in json.loads((entry.ROOT / "benchmarks/fixtures/planning-tool-p4-comparison-v1/tasks.json").read_text())["projects"] if p["name"] == "libffi")
    original = PublicBuildTask.model_validate(item["task"])
    old_reference = BuildReference.model_validate(item["reference"])
    archive = tmp_path / "source.tar"
    recovery = object()
    monkeypatch.setattr(entry, "previous_material", lambda: (original, old_reference, archive, recovery))
    task, reference, actual_archive, actual_recovery = entry.material()
    assert task.image_id == entry.IMAGE_ID != original.image_id
    assert task.goal == entry.SIMPLE_GOAL
    assert task.plan_id == entry.IDENTITY
    assert reference.task_sha256 == entry._digest(task.model_dump(mode="json"))
    assert actual_archive == archive
    assert task.source_archive_sha256 == original.source_archive_sha256
    assert actual_recovery is recovery
    assert "libltdl-dev" not in task.goal
