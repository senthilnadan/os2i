Bridge the execution output gap for an abstract transition.

abstract_tool: {abstract_tool}
missing_outputs: {missing_outputs}

execution_outcome (what the grounded tool actually produced):
{execution_outcome}

state (full state after execution — includes inputs and execution outputs):
{state}

patching_tools (preferred — pure, no side effects):
{patching_tool_list}

available_tools (fallback):
{available_tool_list}

Rules:

TOOL SELECTION
- Select ONLY tools listed in patching_tools or available_tools above. Never use the abstract_tool name or any name not in these lists.
- filter_suffix is a TOOL, not an input parameter. To filter a list by suffix, the TOOL must be filter_suffix — not count_list with extra keys.

RESULT_KEY
- Every INPUTS line must include result_key=<key_name>.
- Intermediate steps: use a temporary key (e.g. py_files, entry_lines).
- Final step: use result_key=<missing_output_name> — this is the required abstract output key.

ORDERING
- Emit TOOL blocks in execution order. The first block runs first, the second block runs second.
- If step 2 depends on output of step 1, step 1 must come first in your response.

WHEN TO STOP
- Stop when the last result_key matches the missing output. Do not add extra steps beyond that.

NOT_RESOLVABLE — this rule overrides all other rules including available_tools fallback
- If execution_outcome.outputs contains ONLY boolean flags — keys such as success, deleted, is_present, created, removed, copied, moved — respond NOT_RESOLVABLE immediately.
- Even if file_path is in state and read_file is in available_tools, do NOT use it. Respond NOT_RESOLVABLE.
- success:bool → NOT_RESOLVABLE. is_present:bool → NOT_RESOLVABLE. deleted:bool → NOT_RESOLVABLE.

AVAILABLE_TOOLS FALLBACK (run_shell_command)
- Use run_shell_command ONLY when no patching_tool can transform data already in state. If the data is already in state (entries list, stdout string), use patching_tools first.
- run_shell_command does NOT use result_key. Do NOT add result_key to its INPUTS. Its outputs are stdout, stderr, return_code.
- run_shell_command ALWAYS requires a second step to extract the result from stdout:
  - For a number result: follow with cast_int using value=stdout, result_key=<missing_output_name>
  - For a list result: follow with split_lines using text=stdout, result_key=<missing_output_name>

Example — total file size as int:
TOOL: run_shell_command
INPUTS: command=du -sb <directory_path>

TOOL: cast_int
INPUTS: value=stdout, result_key=<missing_output_name>

Example — files matching a pattern as list:
TOOL: run_shell_command
INPUTS: command=grep -rl import_name <directory_path> --include=*.py

TOOL: split_lines
INPUTS: text=stdout, result_key=<missing_output_name>

task hint (for input value derivation only — not for tool selection): {task}

Respond in plain text only. Use NOT_RESOLVABLE: <reason> if no bridge exists.

TOOL: <exact tool name from patching_tools or available_tools>
INPUTS: result_key=<key>, <other_inputs>=<values>, ...
