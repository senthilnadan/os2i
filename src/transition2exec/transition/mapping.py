from __future__ import annotations

from pathlib import Path  # noqa: F401 — used in resolve_input
from pathlib import Path


DEFAULT_MISSING_VALUE = {
    "entries": [],
    "text": "",
    "success": False,
    "deleted": False,
    "copied": False,
    "moved": False,
    "is_present": False,
    "created": False,
    "removed": False,
    "stdout": "",
    "stderr": "",
    "return_code": 0,
}



def default_output_value(name: str):
    return DEFAULT_MISSING_VALUE.get(name, None)


def resolve_input(name: str, context: dict | None, base_path: Path | None = None) -> str | None:
    if not context:
        return None
    if value := context.get(name):
        return value
    if name == "file_path" and "target_file" in context:
        base = context.get("project_folder_path") or (str(base_path) if base_path else None)
        if base:
            return str(Path(base) / context["target_file"])
        return context["target_file"]
    if name == "directory_path" and "project_folder_path" in context:
        return context["project_folder_path"]
    if name == "working_directory":
        return context.get("project_folder_path")
    return None
