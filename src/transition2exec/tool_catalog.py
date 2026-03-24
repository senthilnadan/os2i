from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel


class ToolSignature(BaseModel):
    inputs: List[str]
    outputs: List[str]


class GroundedTool(BaseModel):
    name: str
    signature: ToolSignature
    description: str


DEFAULT_TOOLS: List[GroundedTool] = [
    GroundedTool(
        name="list_directory",
        signature=ToolSignature(inputs=["directory_path"], outputs=["entries"]),
        description="Lists the names of files and folders directly under `directory_path`.",
    ),
    GroundedTool(
        name="list_directory_recursive",
        signature=ToolSignature(inputs=["directory_path"], outputs=["entries"]),
        description="Recursively walks `directory_path` and returns every entry (files and folders).",
    ),
    GroundedTool(
        name="read_file",
        signature=ToolSignature(inputs=["file_path"], outputs=["text"]),
        description="Reads the entire contents of a text file.",
    ),
    GroundedTool(
        name="create_file",
        signature=ToolSignature(inputs=["file_path", "content"], outputs=["success"]),
        description="Creates or overwrites `file_path` with the provided `content`.",
    ),
    GroundedTool(
        name="append_to_file",
        signature=ToolSignature(inputs=["file_path", "content"], outputs=["success"]),
        description="Appends text to `file_path`, creating it if necessary.",
    ),
    GroundedTool(
        name="delete_file",
        signature=ToolSignature(inputs=["file_path"], outputs=["deleted"]),
        description="Deletes `file_path` if it exists and returns the result.",
    ),
    GroundedTool(
        name="copy_file",
        signature=ToolSignature(
            inputs=["source_path", "destination_path"], outputs=["copied"]
        ),
        description="Copies a file from `source_path` to `destination_path`.",
    ),
    GroundedTool(
        name="move_file",
        signature=ToolSignature(
            inputs=["source_path", "destination_path"], outputs=["moved"]
        ),
        description="Moves or renames a file to the specified destination.",
    ),
    GroundedTool(
        name="exists",
        signature=ToolSignature(inputs=["file_path"], outputs=["is_present"]),
        description="Reports whether `file_path` currently exists.",
    ),
    GroundedTool(
        name="make_directory",
        signature=ToolSignature(inputs=["directory_path"], outputs=["created"]),
        description="Creates `directory_path` (and intermediates) if it does not already exist.",
    ),
    GroundedTool(
        name="remove_directory",
        signature=ToolSignature(
            inputs=["directory_path", "recursive"], outputs=["removed"]
        ),
        description="Removes `directory_path`, optionally recursively when `recursive` is true.",
    ),
    GroundedTool(
        name="run_shell_command",
        signature=ToolSignature(
            inputs=["command"],
            outputs=["stdout", "stderr", "return_code"],
        ),
        description="Executes a shell command (grep, find, wc, python, etc.) and captures stdout, stderr, and exit code. Use this for search, count, filter, or run operations. Optional inputs: working_directory, shell (defaults to bash).",
    ),
]


TOOL_BY_NAME: Dict[str, GroundedTool] = {tool.name: tool for tool in DEFAULT_TOOLS}
