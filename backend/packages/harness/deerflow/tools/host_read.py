"""Host filesystem read tool - direct file access."""

from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool


@tool("host_read", parse_docstring=True)
def host_read_tool(
    filepath: str,
    start_line: Annotated[int | None, "Optional line number to start reading from (1-indexed)."] = None,
    end_line: Annotated[int | None, "Optional line number to stop reading at (inclusive)."] = None,
) -> str:
    """Read the contents of a file from the host filesystem.

    Args:
        filepath: Absolute path to the file to read.
        start_line: Optional line number to start reading from (1-indexed).
        end_line: Optional line number to stop reading at (inclusive).
    """
    try:
        path = Path(filepath)
        if not path.exists():
            return f"Error: File not found: {filepath}"
        if not path.is_file():
            return f"Error: Not a file: {filepath}"

        content = path.read_text(encoding="utf-8")

        if start_line is not None and end_line is not None:
            lines = content.split("\n")
            # Convert to 0-indexed, clamp to valid range
            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)
            if start_idx >= len(lines):
                return f"Error: Start line {start_line} exceeds file length ({len(lines)} lines)"
            return "\n".join(lines[start_idx:end_idx])

        return content
    except PermissionError:
        return f"Error: Permission denied: {filepath}"
    except UnicodeDecodeError:
        return f"Error: Cannot decode file as UTF-8: {filepath}"
    except Exception as e:
        return f"Error: {e}"