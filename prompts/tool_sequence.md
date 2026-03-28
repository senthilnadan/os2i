Map the abstract tool to the single best grounded tool.

abstract_tool: {abstract_tool}
required_outputs: {abstract_outputs}
context: {context}

available_tools:
{tool_list}

Step 1 — select the tool:
  Match abstract_tool to the closest grounded tool by name and required_outputs.
  required_outputs is the primary signal — pick the tool whose outputs best cover required_outputs.
  Use only ONE tool unless the abstract_tool clearly implies a sequence.

Step 2 — resolve inputs:
  List ALL inputs shown in [inputs: ...] for the selected tool.
  Use values from context first.
  If a value is not in context, use the task hint below to derive it.
  If no value can be derived, use an empty string "".
  INPUTS must only contain keys from the tool's input signature. Never include required_outputs key names or any output key names as input values.

task hint (use only for deriving input values, not for tool selection): {task}

Respond in plain text:

TOOL: <exact tool name from available_tools>
INPUTS: <key>=<value>, <key>=<value>, ...
