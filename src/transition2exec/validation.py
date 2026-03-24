from __future__ import annotations

from typing import Dict, Iterable, Set

from transition2exec.api.models import ExecutableDSTT
from transition2exec.tool_catalog import GroundedTool


def validate_executable_dstt(
    dstt: ExecutableDSTT,
    available_tools: Iterable[GroundedTool],
    context: Dict[str, object],
) -> None:
    lookup = {tool.name: tool for tool in available_tools}
    previous_outputs: Set[str] = set()
    previous_inputs: Set[str] = set()

    for segment in dstt.segments:
        for transition in segment.transitions:
            tool = lookup.get(transition.tool)
            if not tool:
                raise ValueError(f"Tool '{transition.tool}' is not grounded in the catalog.")

            missing = set(tool.signature.inputs) - set(transition.inputs.keys())
            if missing:
                raise ValueError(
                    f"Transition '{transition.id}' missing required inputs: {', '.join(missing)}."
                )

            if previous_outputs:
                # Allow inputs from: prior outputs, context, or prior transition inputs (constants)
                allowed = previous_outputs.union(context.keys()).union(previous_inputs)
                unexpected_inputs = [
                    name
                    for name in transition.inputs
                    if name not in allowed
                ]
                if unexpected_inputs:
                    raise ValueError(
                        f"Transition '{transition.id}' references inputs {unexpected_inputs} "
                        "that are not produced by prior outputs or provided context."
                    )

            previous_inputs.update(transition.inputs.keys())
            previous_outputs.update(transition.outputs.keys())

    if not dstt.segments and dstt.status == "ok":
        raise ValueError("Executable DSTT is empty but status is OK.")
