# OS2I Example: Task 01 from batch_006_simple_tasks.jsonl

## Seed Input
- `id`: `batch_006_task_01`
- Task text: "Check whether hello.py exists in the project folder."
- Abstract DSTT segment taken directly from the feed (single transition, no decomposition). The abstract tool is `check_python_file_existence` with outputs `python_file_exists`.

## Context (OS2I resolved)
```json
{
  "project_folder_path": "/Users/senthilnadanjothi/works/fship/os2i",
  "target_file": "hello.py",
  "language": "python",
  "user_role": "developer"
}
```
This concrete context keeps the transition grounded in the repo root.

## Available Tool Specs (grounded tool catalog)
```json
[
  {
    "name": "list_directory",
    "signature": {
      "inputs": ["directory_path"],
      "outputs": ["entries"]
    },
    "description": "Returns the names of files and folders directly under `directory_path`."
  },
  {
    "name": "read_file",
    "signature": {
      "inputs": ["file_path"],
      "outputs": ["text"]
    },
    "description": "Reads the full contents of a text file."
  },
  {
    "name": "create_file",
    "signature": {
      "inputs": ["file_path", "content"],
      "outputs": ["success"]
    },
    "description": "Creates or truncates `file_path` with the provided `content`."
  },
  {
    "name": "append_to_file",
    "signature": {
      "inputs": ["file_path", "content"],
      "outputs": ["success"]
    },
    "description": "Appends the provided text to the end of `file_path`."
  },
  {
    "name": "delete_file",
    "signature": {
      "inputs": ["file_path"],
      "outputs": ["deleted"]
    },
    "description": "Deletes `file_path` if it exists and reports boolean success."
  },
  {
    "name": "move_file",
    "signature": {
      "inputs": ["source_path", "destination_path"],
      "outputs": ["moved"]
    },
    "description": "Moves or renames a file from source to destination."
  },
  {
    "name": "copy_file",
    "signature": {
      "inputs": ["source_path", "destination_path"],
      "outputs": ["copied"]
    },
    "description": "Copies a file from source to destination."
  },
  {
    "name": "exists",
    "signature": {
      "inputs": ["file_path"],
      "outputs": ["is_present"]
    },
    "description": "Reports whether `file_path` currently exists."
  },
  {
    "name": "run_shell_command",
    "signature": {
      "inputs": ["command", "working_directory"],
      "outputs": ["stdout", "stderr", "return_code"]
    },
    "description": "Executes a simple shell command; returns standard streams and exit code."
  }
]
```
This catalog represents the dozen or so file/shell capabilities expected from OS2I; the compiler must ground abstract transitions using these exact tools.

## Abstract DSTT (from seed)
```json
{
  "segments": [
    {
      "transitions": [
        {
          "id": "t1",
          "tool": "check_python_file_existence",
          "inputs": ["project_folder_path"],
          "outputs": ["python_file_exists"],
          "output_type": {"python_file_exists": "bool"},
          "complexityTime": "O(n)",
          "complexitySpace": "O(1)",
          "skill_required": ["programmer", "software_engineer", "system_administrator"],
          "resource_required": ["filesystem"]
        }
      ],
      "milestone": ["python_file_exists"]
    }
  ]
}
```

## Executable DSTT (OS2I output)
OS2I maps the abstract transition onto the grounded `exists` tool, injecting the resolved inputs and contextual metadata.
```json
{
  "status": "ok",
  "segments": [
    {
      "transitions": [
        {
          "id": "t1",
          "tool": "exists",
          "inputs": {
            "file_path": "/Users/senthilnadanjothi/works/fship/os2i/hello.py"
          },
          "outputs": {
            "is_present": false
          }
        }
      ],
      "milestone": ["is_present"]
    }
  ],
  "context": {
    "resolved_by": "OS2I",
    "notes": "Derived from the seed task and repo root context."
  }
}
```
`is_present` reflects the actual filesystem state; OS2I maintains determinism by returning the boolean produced by the grounded tool.

## Notes
- The example draws from the provided seed file to keep OS2I’s input rooted in real abstract transitions.
- The catalog of simple file/shell tools shows what implementations must support; OS2I must never invent new tool names.
