"""暴露检索不误配相似仓库，也不把脚本资格升级为真实模型观察。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_candidate_exposure_audit import exact_match, observed_model_arms, repository_key  # noqa: E402


def test_exact_repository_boundaries_and_case():
    assert exact_match("clibs/buffer", '"https://github.com/CLIBS/BUFFER.git"')
    assert exact_match("clibs/buffer", "clibs/buffer/Makefile")
    assert not exact_match("clibs/buffer", "clibs/buffer-extra")
    assert not exact_match("clibs/buffer", "otherclibs/buffer")
    assert not exact_match("clibs/buffer", "clibs/buffer.gitx")
    assert repository_key("https://github.com/Clibs/Buffer.git/") == "clibs/buffer"


@pytest.mark.parametrize("value", ["clibs", "github.com/clibs/buffer", "clibs/buffer/tree/main"])
def test_non_repository_identifier_rejected(value):
    with pytest.raises(ValueError):
        repository_key(value)


def test_actual_provider_observations_preserve_failed_arm_and_ignore_script():
    protocol = {"identity": "cohort", "projects": [{"name": "buffer", "task": {"repository_url": "https://github.com/clibs/buffer"}}]}
    result = {
        "identity": "cohort",
        "arms": [
            {"name": "buffer-r1", "arm": "plan", "agent_usage": {"model_requests": 0}, "strict_completed": True},
            {"name": "buffer-r2", "arm": "tool", "agent_usage": {"model_requests": 3}, "strict_completed": False},
        ],
    }
    observed = observed_model_arms(protocol, result)
    assert len(observed) == 1
    assert observed[0]["repository"] == "clibs/buffer"
    assert observed[0]["strict_completed"] is False
    result["identity"] = "other"
    with pytest.raises(ValueError, match="身份"):
        observed_model_arms(protocol, result)


def test_unknown_project_cannot_inherit_neighbor_observation():
    with pytest.raises(ValueError, match="未绑定"):
        observed_model_arms({"identity": "c", "projects": []}, {"identity": "c", "arms": [{"name": "missing", "agent_usage": {"model_requests": 3}}]})
