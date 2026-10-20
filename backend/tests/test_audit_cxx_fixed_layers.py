"""分层结果分析先验证完整封存及固定分母，不能静默漏行或信任漂移文件。"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cxx_layers", ROOT / "scripts/forge_audit_cxx_fixed_layers.py")
layers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layers)


def sealed(root, files):
    rows = []
    for name, value in files.items():
        path = root / name
        path.write_text(json.dumps(value))
        rows.append(dict(path=name, type="file", size=path.stat().st_size, sha256=layers.sha(path)))
    rows.sort(key=lambda r: r["path"])
    (root / "inventory.json").write_text(json.dumps(rows))
    (root / "seal.json").write_text(json.dumps(dict(identity="cohort", inventory_canonical_sha256=layers.canonical(rows))))


def test_changed_consumed_evidence_is_rejected(tmp_path):
    sealed(tmp_path, {"result.json": {"arms": []}})
    assert layers.verify_seal(tmp_path)["identity"] == "cohort"
    (tmp_path / "result.json").write_text('{"arms":["injected"]}')
    with pytest.raises(AssertionError):
        layers.verify_seal(tmp_path)


def test_unlisted_extra_file_is_rejected(tmp_path):
    sealed(tmp_path, {"result.json": {"arms": []}})
    (tmp_path / "extra.json").write_text("{}")
    with pytest.raises(AssertionError):
        layers.verify_seal(tmp_path)


def test_fixed_denominator_cannot_drop_unobserved_slot(tmp_path):
    sealed(tmp_path, {"result.json": {"identity": "cohort", "arms": [], "not_observed": []}, "protocol.json": {"identity": "cohort", "schedule": [], "projects": []}})
    with pytest.raises(AssertionError):
        layers.audit_cohort(dict(root=str(tmp_path), identity="cohort", slots=1, inventory_sha256=None))


def test_changed_identity_cannot_reuse_same_sealed_cohort(tmp_path):
    sealed(tmp_path, {"result.json": {"identity": "cohort", "arms": [], "not_observed": []}, "protocol.json": {"identity": "cohort", "schedule": [], "projects": []}})
    with pytest.raises(AssertionError):
        layers.audit_cohort(dict(root=str(tmp_path), identity="other", slots=0, inventory_sha256=None))
