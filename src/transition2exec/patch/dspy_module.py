from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import dspy

from transition2exec.api.models import PatchRequest, PatchResponse, PatchTransition
from transition2exec.patch.patch_tools import PATCH_TOOL_BY_NAME, PATCH_TOOLS

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def _load(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


PATCH_RESOLUTION_TEMPLATE = _load("patch_resolution.md")


class PatchResolutionModule:
    def __init__(self, lm: dspy.LM) -> None:
        self.lm = lm

    def generate_patch_response(self, request: PatchRequest) -> PatchResponse:
        missing = request.missing_outputs or [
            k for k in request.abstract_transition.outputs if k not in request.state
        ]
        if not missing:
            return PatchResponse(status="resolved", patch_transitions=[])

        try:
            plan = self._resolve_patch_plan(request, missing)
        except Exception as exc:
            return PatchResponse(status="not_resolvable", reason=str(exc))

        return self._extract_patch_transitions(plan, request, missing)

    # ------------------------------------------------------------------
    # Stage 1 — LLM selects patching tool(s) and input values
    # ------------------------------------------------------------------

    def _resolve_patch_plan(
        self, request: PatchRequest, missing: List[str]
    ) -> str:
        patching_tool_list = "\n".join(
            f"- {t.name} [inputs: {', '.join(t.signature.inputs)}]: {t.description}"
            for t in (request.patching_tools or PATCH_TOOLS)
        )
        available_tool_list = "\n".join(
            f"- {t.name} [inputs: {', '.join(t.signature.inputs)}]: {t.description}"
            for t in request.available_tools
        )
        # Summarise state — show keys and types/preview to keep context short
        state_summary = json.dumps(
            {k: _preview(v) for k, v in (request.state or {}).items()},
            default=str,
        )
        execution_outcome_summary = json.dumps(
            {
                "tool": request.execution_outcome.tool,
                "outputs": {k: _preview(v) for k, v in request.execution_outcome.outputs.items()},
            },
            default=str,
        )
        substitutions = {
            "abstract_tool": request.abstract_transition.tool,
            "missing_outputs": ", ".join(missing),
            "execution_outcome": execution_outcome_summary,
            "state": state_summary,
            "patching_tool_list": patching_tool_list,
            "available_tool_list": available_tool_list,
            "task": request.task,
        }
        prompt = _safe_substitute(PATCH_RESOLUTION_TEMPLATE, substitutions)
        completion = self.lm(messages=[{"role": "user", "content": prompt}])
        return completion[0] if isinstance(completion, list) and completion else str(completion)

    # ------------------------------------------------------------------
    # Stage 2 (Python) — parse plan into PatchTransition list
    # ------------------------------------------------------------------

    def _extract_patch_transitions(
        self, plan: str, request: PatchRequest, missing: List[str]
    ) -> PatchResponse:
        plan_stripped = plan.strip()

        # LLM signalled it cannot resolve
        if plan_stripped.upper().startswith("NOT_RESOLVABLE"):
            reason = plan_stripped.split(":", 1)[1].strip() if ":" in plan_stripped else plan_stripped
            return PatchResponse(status="not_resolvable", reason=reason)

        # Build a combined lookup: patching tools take precedence over available tools
        patching_lookup = {t.name: t for t in (request.patching_tools or PATCH_TOOLS)}
        available_lookup = {t.name: t for t in request.available_tools}
        state = request.state or {}

        # Parse all TOOL/INPUTS blocks in order
        entries: list[tuple[str, dict[str, str]]] = []
        current_tool: str | None = None
        current_inputs: dict[str, str] = {}
        for line in plan_stripped.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("TOOL:"):
                if current_tool is not None:
                    entries.append((current_tool, current_inputs))
                current_tool = stripped.split(":", 1)[1].strip()
                current_inputs = {}
            elif stripped.upper().startswith("INPUTS:") and current_tool is not None:
                current_inputs.update(_parse_inputs(stripped.split(":", 1)[1]))
        if current_tool is not None:
            entries.append((current_tool, current_inputs))

        if not entries:
            return PatchResponse(
                status="not_resolvable",
                reason="patch resolution plan produced no tool selection",
            )

        satisfied: set[str] = set()  # missing outputs already covered by earlier transitions
        transitions: list[PatchTransition] = []
        for idx, (tool_name, stage1_kv) in enumerate(entries):
            # Stop early: all missing outputs are already covered
            if set(missing) <= satisfied:
                break

            tool = patching_lookup.get(tool_name) or available_lookup.get(tool_name)
            if not tool:
                return PatchResponse(
                    status="not_resolvable",
                    reason=f"tool '{tool_name}' not found in patching or available catalogs",
                )

            # Resolve input values: if stage1 value is a state key, use state value;
            # otherwise use the literal string from stage1. Null inputs are left as None
            # (executor resolves from state at dispatch time per PATCH-Q6 contract).
            resolved: Dict[str, Any] = {}
            for k in tool.signature.inputs:
                raw = stage1_kv.get(k)
                if raw is None:
                    resolved[k] = None  # executor reads from state at dispatch
                elif raw in state:
                    resolved[k] = state[raw]
                else:
                    resolved[k] = raw
            # Include any extra keys stage1 provided (e.g. optional params)
            for k, v in stage1_kv.items():
                if k not in resolved:
                    resolved[k] = state[v] if v in state else v

            # Determine output key: result_key for patching tools; signature outputs for available tools.
            # run_shell_command (available tool) does NOT use result_key — its outputs are fixed.
            result_key_val = resolved.get("result_key") if tool_name in patching_lookup else None
            # Remove result_key from resolved inputs for available tools (not part of their signature)
            if tool_name in available_lookup and "result_key" in resolved:
                del resolved["result_key"]
            if result_key_val and isinstance(result_key_val, str):
                outputs: Dict[str, Any] = {result_key_val: None}
                satisfied.add(result_key_val)
            else:
                outputs = {k: None for k in tool.signature.outputs}

            transitions.append(
                PatchTransition(
                    id=f"patch_t{idx + 1}",
                    tool=tool_name,
                    inputs=resolved,
                    outputs=outputs,
                )
            )

        return PatchResponse(status="resolved", patch_transitions=transitions)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import re as _re


def _parse_inputs(inputs_str: str) -> Dict[str, str]:
    """Parse comma-separated key=value pairs from a TOOL INPUTS line.

    Handles quoted values (including commas inside quotes):
        items=entries, sep=",", result_key=file_list_str
    """
    result: Dict[str, str] = {}
    # Match key = "quoted" | key = 'quoted' | key = unquoted (stops at next comma or end)
    pattern = _re.compile(r'''([\w.]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^,]*))''')
    for m in pattern.finditer(inputs_str):
        key = m.group(1).strip()
        if m.group(2) is not None:
            val = m.group(2)
        elif m.group(3) is not None:
            val = m.group(3)
        else:
            val = (m.group(4) or "").strip()
        result[key] = val
    return result


def _safe_substitute(template: str, substitutions: dict[str, str]) -> str:
    """Replace {key} placeholders without Python's .format() so literal braces in
    shell commands (e.g. awk '{print $1}') are passed through unchanged."""
    result = template
    for key, value in substitutions.items():
        result = result.replace("{" + key + "}", value)
    return result


def _preview(value: Any) -> Any:
    """Compact preview of a state value so the LLM context stays short."""
    if isinstance(value, list):
        preview = value[:5]
        return f"list[{len(value)}]: {preview}{'...' if len(value) > 5 else ''}"
    if isinstance(value, str) and len(value) > 120:
        return value[:120] + "..."
    return value
