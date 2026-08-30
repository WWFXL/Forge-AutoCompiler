"""Issue #224 OpenH264 candidate 的 opt-in Ubuntu 原生 Docker lifecycle 门禁。"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DOCKER_ENABLED = os.getenv("FORGE_RUN_OPAQUE_PROVENANCE_OPENH264_DOCKER") == "1"

pytestmark = pytest.mark.skipif(
    not DOCKER_ENABLED,
    reason="set FORGE_RUN_OPAQUE_PROVENANCE_OPENH264_DOCKER=1 in WSL Ubuntu",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


gate = _load_module(
    "forge_opaque_provenance_openh264_candidate_gate_docker",
    SCRIPTS_DIR / "forge_opaque_provenance_openh264_candidate_gate.py",
)
legacy = _load_module(
    "forge_opaque_provenance_openh264_legacy_docker_orchestration",
    REPO_ROOT / "backend/tests/test_forge_opaque_provenance_make_lifecycle_gate_docker.py",
)


def _docker(
    *args: str,
    check: bool = True,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_openh264_real_parent_treatment_replay_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate.validate_static_gate(REPO_ROOT)
    tag = f"forge-issue224-openh264-{uuid.uuid4().hex[:12]}"
    label = f"forge.issue224.image={tag}"
    context = tmp_path / "image"
    context.mkdir()
    (context / "Dockerfile").write_text(
        "FROM autocompiler:gcc13\n"
        "RUN curl --location --fail --show-error --connect-timeout 15 "
        "--max-time 60 --output /tmp/nasm.deb "
        f"{gate.NASM_DEB_URL} "
        f"&& echo '{gate.NASM_DEB_SHA256}  /tmp/nasm.deb' | sha256sum --check - "
        "&& dpkg --install /tmp/nasm.deb && rm /tmp/nasm.deb\n",
        encoding="utf-8",
        newline="\n",
    )
    image_id: str | None = None
    try:
        built = _docker(
            "build",
            "--label",
            label,
            "--tag",
            tag,
            str(context),
            timeout=180,
        )
        assert built.returncode == 0
        image_id = _docker("image", "inspect", tag, "--format", "{{.Id}}").stdout.strip()
        assert image_id.startswith("sha256:")
        nasm = _docker("run", "--rm", image_id, "nasm", "-v")
        assert nasm.returncode == 0

        monkeypatch.setattr(legacy, "adapter", gate.build_docker_adapter(image_id))
        legacy.test_real_make_parent_treatment_replay_and_cleanup(tmp_path, monkeypatch)
    finally:
        if image_id:
            _docker("image", "rm", "--force", image_id, check=False)
        _docker("image", "rm", "--force", tag, check=False)
    remaining = _docker(
        "image",
        "ls",
        "--quiet",
        "--filter",
        f"label={label}",
    ).stdout.splitlines()
    assert remaining == []
