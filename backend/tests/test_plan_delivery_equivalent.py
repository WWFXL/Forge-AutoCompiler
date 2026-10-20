"""真实Shell回归：同字节副本可交付，真实歧义与不安全链接仍拒绝。"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from deerflow.compile.plan_delivery_equivalent import equivalent_delivery_command


def test_identical_copies_deliver_the_same_bytes_and_mode(tmp_path):
    source, output = tmp_path / "repo", tmp_path / "artifacts"
    source.mkdir()
    for name in ("build", "build/test"):
        folder = source / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "library.so").write_bytes(Path(sys.executable).read_bytes())
        (folder / "library.so").chmod(0o755)
    command = equivalent_delivery_command(("library.so",)).replace("/artifacts", str(output))
    result = subprocess.run(["bash", "-c", command], cwd=source, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (output / "library.so").read_bytes() == Path(sys.executable).read_bytes()
    assert (output / "library.so").stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize("kind", ["content", "mode", "outside", "dangling", "cycle", "missing"])
def test_real_ambiguity_and_unsafe_inputs_still_rejected(tmp_path, kind):
    source, output = tmp_path / "repo", tmp_path / "artifacts"
    source.mkdir()
    if kind in ("content", "mode"):
        for name in ("build", "test"):
            folder = source / name
            folder.mkdir()
            (folder / "library.so").write_bytes(Path(sys.executable).read_bytes())
            (folder / "library.so").chmod(0o755)
        other = source / "test/library.so"
        if kind == "content":
            other.write_bytes(other.read_bytes() + b"different")
        else:
            other.chmod(0o644)
    elif kind == "outside":
        (source / "library.so").symlink_to(Path(sys.executable).resolve())
    elif kind == "dangling":
        (source / "library.so").symlink_to("missing")
    elif kind == "cycle":
        (source / "library.so").symlink_to("library.so")
    command = equivalent_delivery_command(("library.so",)).replace("/artifacts", str(output))
    result = subprocess.run(["bash", "-c", command], cwd=source, capture_output=True, text=True)
    assert result.returncode != 0
    assert not output.exists()


def test_v2_changes_only_common_delivery_and_keeps_new_identity():
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    spec = importlib.util.spec_from_file_location("cxx_gate_v2", scripts / "forge_build_cxx_common_input_gate_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.IDENTITY == "cpp-build-cxx-common-input-gate-v2"
    assert len(module.schedule()) == 11
    text = (scripts / "forge_build_cxx_common_input_gate_v2.py").read_text()
    assert "return with_equivalent_delivery(plan), reason" in text
    assert "failed_parent_evidence" in text
    assert "create_chat_model" not in text and "credentials(" not in text
