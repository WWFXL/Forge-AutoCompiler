"""Host filesystem write tool - direct file access without sandbox."""

from pathlib import Path
from typing import Annotated

from langchain.agents import tool


@tool("host_write", parse_docstring=True)
def host_write_tool(
    filepath: str,
    content: Annotated[str, "The content to write to the file."],
    append: Annotated[bool, "If True, append to existing file instead of overwriting."] = False,
) -> str:
    """Write content to a file on the host filesystem.

    Args:
        filepath: Absolute path to the file to write.
        content: The content to write.
        append: If True, append to existing file instead of overwriting.
    """
    try:
        path = Path(filepath)
        # Create parent directories if they don't exist
        path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)

        action = "appended to" if append else "written to"
        return f"Successfully {action} {filepath}"
    except PermissionError:
        return f"Error: Permission denied: {filepath}"
    except Exception as e:
        return f"Error: {e}"