# Grounded Tool Catalog for OS2I

This catalog lists the simple, generic tools OS2I is allowed to map abstract transitions to. Each entry lists the canonical name, input/output signature, and a short description so the compiler can validate tooling choices without inventing new capabilities.

| Tool | Inputs | Outputs | Description |
| --- | --- | --- | --- |
| `list_directory` | `directory_path: string` | `entries: list<string>` | Lists the names (files/folders) directly under `directory_path`. No recursion. |
| `list_directory_recursive` | `directory_path: string` | `entries: list<string>` | Walks `directory_path` top-down and returns every entry (files + folders). Useful for search tasks. |
| `read_file` | `file_path: string` | `text: string` | Reads the entire file content as text; fails if the path is not readable. |
| `create_file` | `file_path: string`, `content: string` | `success: bool` | Creates or overwrites `file_path` with `content`. Returns true on success. |
| `append_to_file` | `file_path: string`, `content: string` | `success: bool` | Appends `content` to the end of `file_path`, creating the file if necessary. |
| `delete_file` | `file_path: string` | `deleted: bool` | Removes the file if it exists and reports whether the deletion happened. |
| `copy_file` | `source_path: string`, `destination_path: string` | `copied: bool` | Copies `source_path` to `destination_path`, overwriting when allowed. |
| `move_file` | `source_path: string`, `destination_path: string` | `moved: bool` | Moves or renames a file, creating intermediate directories when possible. |
| `exists` | `file_path: string` | `is_present: bool` | Boolean check for the existence of `file_path`. |
| `make_directory` | `directory_path: string` | `created: bool` | Creates `directory_path` (and intermediate directories) if it does not exist. |
| `remove_directory` | `directory_path: string`, `recursive: bool` | `removed: bool` | Removes the directory; if `recursive` is true, contents are removed. |
| `run_shell_command` | `command: string`, `working_directory: string` | `stdout: string`, `stderr: string`, `return_code: int` | Executes the command in `working_directory` with basic output capture. No privileged operations.

## Example Use
OS2I should map the abstract `check_python_file_existence` transition to the `exists` tool and feed it the resolved `file_path`. When compiling a `list every file` task, OS2I can pick `list_directory_recursive` and use the `directory_path` input derived from the task context.

## Schema Option (Pydantic)
```python
from pydantic import BaseModel
from typing import List

class ToolSignature(BaseModel):
    inputs: List[str]
    outputs: List[str]

class GroundedTool(BaseModel):
    name: str
    signature: ToolSignature
    description: str
```
Use this schema (or a simpler spec) to validate that every grounded tool entry includes the necessary metadata.
