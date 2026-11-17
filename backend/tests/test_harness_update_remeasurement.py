"""修复后重测保留Harness差异、任务和原实验隔离。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import forge_harness_update_comparison as previous  # noqa: E402
import forge_harness_update_remeasurement as remeasure  # noqa: E402


def test_remeasurement_only_changes_common_base_and_three_references():
    current = remeasure.runner()
    original = previous.shared.load(previous.FIXTURE)
    updated = current.shared.load(current.FIXTURE)
    changed = set()
    for old, new in zip(original["projects"], updated["projects"], strict=True):
        assert {k: v for k, v in old.items() if k != "reference"} == {k: v for k, v in new.items() if k != "reference"}
        if old["reference"] != new["reference"]:
            changed.add(old["name"])
    assert changed == {"smenu", "quickjs", "zstd"}
    assert current.schedule() == previous.schedule()
    assert current.harnesses() == previous.harnesses()
    assert all(current.policy(m) == previous.policy(m) for m in previous.METHODS)
    assert current.IDENTITY != previous.IDENTITY
    assert current.MANIFEST != previous.MANIFEST
    assert previous.IDENTITY == "cpp-build-harness-update-comparison-flash-v1"
    value = current.candidate()
    current.validate(value, check_sources=False)
    assert value["known_solution_injection"] is False
    assert value["recipe_reuse"] is False
    assert value["experience_bank"] is None
    assert len(value["schedule"]) == 36


def test_material_check_never_calls_provider(tmp_path, monkeypatch, capsys):
    current = remeasure.runner()
    monkeypatch.setattr(current, "MANIFEST", tmp_path / "manifest.json")
    current.shared.save(current.MANIFEST, current.candidate())
    validate = current.validate
    monkeypatch.setattr(current, "validate", lambda value: validate(value, check_sources=False))
    monkeypatch.setattr(current, "run_paid", lambda *args: (_ for _ in ()).throw(AssertionError("不得调用Provider")))
    monkeypatch.setattr(sys, "argv", ["remeasure", "--check-prepared"])
    current.main()
    assert '"provider_calls": 0' in capsys.readouterr().out
