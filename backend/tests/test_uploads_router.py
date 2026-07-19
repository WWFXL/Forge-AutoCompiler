import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import UploadFile

from app.gateway.routers import uploads


def test_upload_files_writes_thread_storage(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)

    with (
        patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "ensure_uploads_dir", return_value=thread_uploads_dir),
    ):
        file = UploadFile(filename="notes.txt", file=BytesIO(b"hello uploads"))
        result = asyncio.run(uploads.upload_files("thread-local", files=[file]))

    assert result.success is True
    assert len(result.files) == 1
    assert result.files[0]["filename"] == "notes.txt"
    assert result.files[0]["virtual_path"] == "/mnt/user-data/uploads/notes.txt"
    assert (thread_uploads_dir / "notes.txt").read_bytes() == b"hello uploads"


def test_upload_files_converts_and_marks_markdown_file(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)

    async def fake_convert(file_path: Path) -> Path:
        md_path = file_path.with_suffix(".md")
        md_path.write_text("converted", encoding="utf-8")
        return md_path

    with (
        patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "ensure_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "convert_file_to_markdown", AsyncMock(side_effect=fake_convert)),
    ):
        file = UploadFile(filename="report.pdf", file=BytesIO(b"pdf-bytes"))
        result = asyncio.run(uploads.upload_files("thread-aio", files=[file]))

    assert result.success is True
    assert len(result.files) == 1
    file_info = result.files[0]
    assert file_info["filename"] == "report.pdf"
    assert file_info["markdown_file"] == "report.md"
    assert file_info["markdown_virtual_path"] == "/mnt/user-data/uploads/report.md"

    assert (thread_uploads_dir / "report.pdf").read_bytes() == b"pdf-bytes"
    assert (thread_uploads_dir / "report.md").read_text(encoding="utf-8") == "converted"


def test_upload_files_rejects_dotdot_and_dot_filenames(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)

    with (
        patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "ensure_uploads_dir", return_value=thread_uploads_dir),
    ):
        # These filenames must be rejected outright
        for bad_name in ["..", "."]:
            file = UploadFile(filename=bad_name, file=BytesIO(b"data"))
            result = asyncio.run(uploads.upload_files("thread-local", files=[file]))
            assert result.success is True
            assert result.files == [], f"Expected no files for unsafe filename {bad_name!r}"

        # Path-traversal prefixes are stripped to the basename and accepted safely
        file = UploadFile(filename="../etc/passwd", file=BytesIO(b"data"))
        result = asyncio.run(uploads.upload_files("thread-local", files=[file]))
        assert result.success is True
        assert len(result.files) == 1
        assert result.files[0]["filename"] == "passwd"

    # Only the safely normalised file should exist
    assert [f.name for f in thread_uploads_dir.iterdir()] == ["passwd"]


def test_delete_uploaded_file_removes_generated_markdown_companion(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)
    (thread_uploads_dir / "report.pdf").write_bytes(b"pdf-bytes")
    (thread_uploads_dir / "report.md").write_text("converted", encoding="utf-8")

    with patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir):
        result = asyncio.run(uploads.delete_uploaded_file("thread-aio", "report.pdf"))

    assert result == {"success": True, "message": "Deleted report.pdf"}
    assert not (thread_uploads_dir / "report.pdf").exists()
    assert not (thread_uploads_dir / "report.md").exists()
