Select the best grounded tool and declare key bindings for its inputs.

abstract_tool: {abstract_tool}
abstract_inputs: {abstract_inputs}
abstract_outputs: {abstract_outputs}

state keys (names only — values resolved by program): {state_keys}

available_tools:
{tool_list}

Step 1 — select the tool:
  Match abstract_tool to the closest grounded tool by name and abstract_outputs.
  abstract_outputs is the primary signal — pick the tool whose outputs best cover abstract_outputs.
  Use only ONE tool unless the abstract_tool clearly implies a sequence.

Step 2 — bind inputs:
  For each input of the selected tool, declare which state key holds its value.
  BIND values must be key names from the state keys list above — never use abstract_outputs names as bind values.
  If a state key matches the tool input key exactly, you may omit it.
  If no state key matches an input, omit that binding entirely.

task (for semantic guidance only — do not copy values): {task}

If no tool in available_tools can fulfil the abstract_tool, respond:
STATUS: ambiguous
REASON: <why>

Otherwise respond in plain text:
TOOL: <exact tool name>
BIND: <input_key> <- <state_key>, ...
