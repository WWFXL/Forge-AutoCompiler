"""Issue #367 mechanism v2 的 opt-in 零 Provider Docker lifecycle gate。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_contract_driven_repair_mechanism_v2_candidate_protocol as protocol  # noqa: E402
import forge_contract_driven_repair_mechanism_v2_candidate_runner as runner  # noqa: E402

from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
)

pytestmark = pytest.mark.skipif(
    os.getenv("FORGE_RUN_CONTRACT_REPAIR_V2_CANDIDATE_DOCKER") != "1",
    reason="set FORGE_RUN_CONTRACT_REPAIR_V2_CANDIDATE_DOCKER=1 to run the gate",
)


@pytest.mark.parametrize("checkpoint_index", (0, 1))
def test_v2_parent_capture_and_three_arm_clone_are_state_matched(
    checkpoint_index: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    manifest = protocol.load_manifest()
    checkpoint = manifest["schedule"]["checkpoints"][checkpoint_index]
    output_dir = tmp_path / "qualification-evidence"
    arms: list[Any] = []
    captured: dict[str, Any] | None = None
    runner.base._require_zero_managed_resources()
    with runner._runtime_binding():
        runner.base.validate_runtime(manifest, REPO_ROOT)
        with runner.base._runtime_identity(manifest, REPO_ROOT) as services:
            try:
                captured = runner.base._capture_checkpoint(
                    manifest,
                    checkpoint,
                    output_dir=output_dir,
                    services=services,
                )
                marker_path, ledger_path = runner.base._checkpoint_paths(manifest, output_dir, checkpoint)
                marker = runner.base.qualification.validate_checkpoint(marker_path)
                assert marker["formal_manifest_sha256"] == (runner.base._manifest_sha256(manifest))
                assert marker["checkpoint_id"] == checkpoint["checkpoint_id"]
                assert marker["status"] == "captured"
                assert ledger_path.is_file()
                assert set(marker["feedback_projections"]) == {"c0", "t1", "t2"}
                assert marker["provider_calls"] == 0
                assert marker["formal_attempts"] == 0

                for arm_spec in checkpoint["arms"]:
                    arm = runner.base._provision_arm(
                        manager=services.manager,
                        runtime=services.runtime,
                        parent=captured["parent"],
                        captured=captured["captured"],
                        opaque_clone_id=arm_spec["opaque_clone_id"],
                    )
                    arms.append(arm)
                    assert runner.base._environment_identity(arm) == (captured["captured"]["identity"])
                    finalized, cleanup = cleanup_and_finalize_compile_session_impl(
                        session=arm,
                        interrupted_status="cancelled",
                        error="Zero-provider v2 candidate lifecycle gate completed.",
                    )
                    assert cleanup.succeeded is True
                    assert finalized.finalized_at is not None
                runner.base._checkpoint_cleanup(captured, services)
                captured = None
                assert runner.base._managed_resources() == {
                    "containers": [],
                    "images": [],
                }
            finally:
                for arm in reversed(arms):
                    services.runtime.stop_and_remove_container(arm)
                if captured is not None:
                    services.runtime.stop_and_remove_container(captured["parent"])
                    runner.base._remove_capture_image(captured["captured"]["continuation_image_id"])
