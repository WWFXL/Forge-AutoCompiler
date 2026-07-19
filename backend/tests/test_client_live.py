"""Live integration tests for DeerFlowClient with real API.

These tests require a working config.yaml with valid API credentials.
They are skipped in CI and must be run explicitly:

    PYTHONPATH=. uv run pytest tests/test_client_live.py -v -s
"""

import os
from pathlib import Path

import pytest

from deerflow.client import DeerFlowClient, StreamEvent
from deerflow.uploads.manager import PathTraversalError

# Skip entire module in CI or when no config.yaml exists
_skip_reason = None
if os.environ.get("CI"):
    _skip_reason = "Live tests skipped in CI"
elif not Path(__file__).resolve().parents[2].joinpath("config.yaml").exists():
    _skip_reason = "No config.yaml found — live tests require valid API credentials"

if _skip_reason:
    pytest.skip(_skip_reason, allow_module_level=True)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Create a real DeerFlowClient (no mocks)."""
    return DeerFlowClient(thinking_enabled=False)


@pytest.fixture
def thread_tmp(tmp_path):
    """Provide a unique thread_id + tmp directory for file operations."""
    import uuid

    tid = f"live-test-{uuid.uuid4().hex[:8]}"
    return tid, tmp_path


# ===========================================================================
# Scenario 1: Basic chat — model responds coherently
# ===========================================================================


class TestLiveBasicChat:
    def test_chat_returns_nonempty_string(self, client):
        """chat() returns a non-empty response from the real model."""
        response = client.chat("Reply with exactly: HELLO")
        assert isinstance(response, str)
        assert len(response) > 0
        print(f"  chat response: {response}")

    def test_chat_follows_instruction(self, client):
        """Model can follow a simple instruction."""
        response = client.chat("What is 7 * 8? Reply with just the number.")
        assert "56" in response
        print(f"  math response: {response}")


# ===========================================================================
# Scenario 2: Streaming — events arrive in correct order
# ===========================================================================


class TestLiveStreaming:
    def test_stream_yields_messages_tuple_and_end(self, client):
        """stream() produces at least one messages-tuple event and ends with end."""
        events = list(client.stream("Say hi in one word."))

        types = [e.type for e in events]
        assert "messages-tuple" in types, f"Expected 'messages-tuple' event, got: {types}"
        assert "values" in types, f"Expected 'values' event, got: {types}"
        assert types[-1] == "end"

        for e in events:
            assert isinstance(e, StreamEvent)
            print(f"  [{e.type}] {e.data}")

    def test_stream_ai_content_nonempty(self, client):
        """Streamed messages-tuple AI events contain non-empty content."""
        ai_messages = [e for e in client.stream("What color is the sky? One word.") if e.type == "messages-tuple" and e.data.get("type") == "ai" and e.data.get("content")]
        assert len(ai_messages) >= 1
        for m in ai_messages:
            assert len(m.data.get("content", "")) > 0


# ===========================================================================
# Scenario 3: File upload lifecycle with real filesystem
# ===========================================================================


class TestLiveFileUpload:
    def test_upload_list_delete(self, client, thread_tmp):
        """Upload → list → delete → verify deletion."""
        thread_id, tmp_path = thread_tmp

        # Create test files
        f1 = tmp_path / "test_upload_a.txt"
        f1.write_text("content A")
        f2 = tmp_path / "test_upload_b.txt"
        f2.write_text("content B")

        # Upload
        result = client.upload_files(thread_id, [f1, f2])
        assert result["success"] is True
        assert len(result["files"]) == 2
        filenames = {r["filename"] for r in result["files"]}
        assert filenames == {"test_upload_a.txt", "test_upload_b.txt"}
        for r in result["files"]:
            assert int(r["size"]) > 0
            assert r["virtual_path"].startswith("/mnt/user-data/uploads/")
            assert "artifact_url" in r
        print(f"  uploaded: {filenames}")

        # List
        listed = client.list_uploads(thread_id)
        assert listed["count"] == 2
        print(f"  listed: {[f['filename'] for f in listed['files']]}")

        # Delete one
        del_result = client.delete_upload(thread_id, "test_upload_a.txt")
        assert del_result["success"] is True
        remaining = client.list_uploads(thread_id)
        assert remaining["count"] == 1
        assert remaining["files"][0]["filename"] == "test_upload_b.txt"
        print(f"  after delete: {[f['filename'] for f in remaining['files']]}")

        # Delete the other
        client.delete_upload(thread_id, "test_upload_b.txt")
        empty = client.list_uploads(thread_id)
        assert empty["count"] == 0
        assert empty["files"] == []

    def test_upload_nonexistent_file_raises(self, client):
        with pytest.raises(FileNotFoundError):
            client.upload_files("t-fail", ["/nonexistent/path/file.txt"])


# ===========================================================================
# Scenario 4: Configuration query — real config loading
# ===========================================================================


class TestLiveConfigQueries:
    def test_list_models_returns_configured_model(self, client):
        """list_models() returns at least one configured model with Gateway-aligned fields."""
        result = client.list_models()
        assert "models" in result
        assert len(result["models"]) >= 1
        names = [m["name"] for m in result["models"]]
        # Verify Gateway-aligned fields
        for m in result["models"]:
            assert "display_name" in m
            assert "supports_thinking" in m
        print(f"  models: {names}")

    def test_get_model_found(self, client):
        """get_model() returns details for the first configured model."""
        result = client.list_models()
        first_model_name = result["models"][0]["name"]
        model = client.get_model(first_model_name)
        assert model is not None
        assert model["name"] == first_model_name
        assert "display_name" in model
        assert "supports_thinking" in model
        print(f"  model detail: {model}")

    def test_get_model_not_found(self, client):
        assert client.get_model("nonexistent-model-xyz") is None

    def test_list_skills(self, client):
        """list_skills() runs without error."""
        result = client.list_skills()
        assert "skills" in result
        assert isinstance(result["skills"], list)
        print(f"  skills count: {len(result['skills'])}")
        for s in result["skills"][:3]:
            print(f"    - {s['name']}: {s['enabled']}")


# ===========================================================================
# Scenario 5: Artifact error handling
# ===========================================================================


class TestLiveArtifact:
    def test_get_artifact_not_found(self, client):
        with pytest.raises(FileNotFoundError):
            client.get_artifact("nonexistent-thread", "mnt/user-data/outputs/nope.txt")


# ===========================================================================
# Scenario 6: Per-call overrides
# ===========================================================================


class TestLiveOverrides:
    def test_thinking_disabled_still_works(self, client):
        """Explicit thinking_enabled=False override produces a response."""
        response = client.chat(
            "Say OK.",
            thinking_enabled=False,
        )
        assert len(response) > 0
        print(f"  response: {response}")


# ===========================================================================
# Scenario 7: Error resilience
# ===========================================================================


class TestLiveErrorResilience:
    def test_delete_nonexistent_upload(self, client):
        with pytest.raises(FileNotFoundError):
            client.delete_upload("nonexistent-thread", "ghost.txt")

    def test_bad_artifact_path(self, client):
        with pytest.raises(ValueError):
            client.get_artifact("t", "invalid/path")

    def test_path_traversal_blocked(self, client):
        with pytest.raises(PathTraversalError):
            client.delete_upload("t", "../../etc/passwd")
