from __future__ import annotations

import json
from ast import literal_eval
from pathlib import Path
from typing import Any

import dspy

from transition2exec.api.models import ExecutableDSTT, Transition2ExecRequest
from transition2exec.transition.mapping import resolve_input

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def _load(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


TOOL_SEQUENCE_TEMPLATE = _load("tool_sequence.md")
DSTT_FORMAT_TEMPLATE = _load("dstt_format.md")


class Transition2ExecChainOfThought(dspy.Module):
    def __init__(self, lm: dspy.LM):
        super().__init__()
        self.lm = lm

    def run_stages(self, request: Transition2ExecRequest) -> tuple[str, str]:
        """Return (stage1_plan, stage2_raw) without parsing or validating."""
        stage1 = self._resolve_tool_plan(request)
        resolved = self._extract_resolved_tools(stage1, request)
        stage2 = self._format_to_dstt(stage1, resolved, request)
        return stage1, stage2

    def generate_executable_dstt(self, request: Transition2ExecRequest) -> ExecutableDSTT:
        try:
            tool_plan = self._resolve_tool_plan(request)
        except Exception as exc:
            return ExecutableDSTT(
                status="not_mappable",
                segments=[],
                context={"stage": "1", "reason": str(exc)},
            )

        try:
            resolved = self._extract_resolved_tools(tool_plan, request)
            raw = self._format_to_dstt(tool_plan, resolved, request)
            dstt = ExecutableDSTT.model_validate(self._normalize_output(raw))
            return dstt.model_copy(update={"context": {**(dstt.context or {}), "tool_plan": tool_plan}})
        except Exception as exc:
            return ExecutableDSTT(
                status="not_mappable",
                segments=[],
                context={"stage": "2", "reason": str(exc), "tool_plan": tool_plan},
            )

    def _resolve_tool_plan(self, request: Transition2ExecRequest) -> str:
        tool_list = "\n".join(
            f"- {t.name} [inputs: {', '.join(t.signature.inputs)}]: {t.description}"
            for t in request.available_tools
        )
        prompt = TOOL_SEQUENCE_TEMPLATE.format(
            task=request.task,
            abstract_tool=request.abstract_transition.tool,
            abstract_outputs=", ".join(request.abstract_transition.outputs),
            context=json.dumps(request.context or {}, default=str),
            tool_list=tool_list,
        )
        completion = self.lm(messages=[{"role": "user", "content": prompt}])
        return completion[0] if isinstance(completion, list) and completion else str(completion)

    def _extract_resolved_tools(self, tool_plan: str, request: Transition2ExecRequest) -> str:
        """Parse TOOL/INPUTS lines from stage 1, return fully-populated JSON templates per tool."""
        lookup = {t.name: t for t in request.available_tools}

        # Parse stage1 plan into ordered list of (tool_name, {key: value}) entries.
        # Preserves duplicates (e.g., append_to_file appearing twice).
        entries: list[tuple[str, dict[str, str]]] = []
        current_tool: str | None = None
        current_inputs: dict[str, str] = {}
        for line in tool_plan.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("TOOL:"):
                if current_tool is not None:
                    entries.append((current_tool, current_inputs))
                current_tool = stripped.split(":", 1)[1].strip()
                current_inputs = {}
            elif stripped.upper().startswith("INPUTS:") and current_tool is not None:
                for part in stripped.split(":", 1)[1].split(","):
                    part = part.strip()
                    if "=" in part:
                        k, _, v = part.partition("=")
                        current_inputs[k.strip()] = v.strip().strip('"')
        if current_tool is not None:
            entries.append((current_tool, current_inputs))

        # Build templates for all matched entries
        templates: list[tuple[str, dict, dict]] = []  # (tool_name, inputs, outputs)
        for tool_name, stage1_kv in entries:
            tool = lookup.get(tool_name)
            if not tool:
                continue
            # Merge: context → stage1 synthesized → ""
            resolved: dict[str, str | None] = {}
            for k in tool.signature.inputs:
                v = resolve_input(k, request.context)
                if v is None:
                    v = stage1_kv.get(k, "")
                resolved[k] = v
            # Include optional inputs stage1 provided that aren't in the signature
            for k, v in stage1_kv.items():
                if k not in resolved:
                    resolved[k] = v
            output_template = {k: None for k in tool.signature.outputs}
            templates.append((tool_name, resolved, output_template))

        if not templates:
            return "(none matched)"

        # If stage1 produced multiple tools, select the one whose outputs best
        # match the abstract transition's required outputs. This is pure Python
        # selection — no LLM reasoning needed here.
        selected = _select_best_match(templates, request.abstract_transition.outputs)

        lines = []
        seen: dict[str, int] = {}
        for tool_name, resolved, output_template in selected:
            count = seen.get(tool_name, 0) + 1
            seen[tool_name] = count
            key = tool_name if count == 1 else f"{tool_name}#{count}"
            transition_template = {"id": "t?", "tool": tool_name, "inputs": resolved, "outputs": output_template}
            lines.append(f"{key}: {json.dumps(transition_template)}")
        return "\n".join(lines)

    def _format_to_dstt(self, tool_plan: str, resolved_tools: str, request: Transition2ExecRequest) -> str:
        prompt = DSTT_FORMAT_TEMPLATE.format(
            resolved_tools=resolved_tools,
        )
        completion = self.lm(messages=[{"role": "user", "content": prompt}])
        return completion[0] if isinstance(completion, list) and completion else str(completion)

    def _normalize_output(self, value: object) -> dict:
        text = str(value).strip()
        if text.startswith("```"):
            text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        first = text.find("{")
        if first == -1:
            raise ValueError("no JSON object found")
        text = text[first:]
        # try balanced extraction first
        depth = 0
        for i, ch in enumerate(text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[: i + 1])
        # output was truncated — repair by closing open brackets/braces
        return json.loads(_close_json(text))


def _select_best_match(
    templates: list[tuple[str, dict, dict]],
    abstract_outputs: list[str],
) -> list[tuple[str, dict, dict]]:
    """Select templates whose grounded tool outputs best match the abstract outputs.

    Stage 1 may over-generate (e.g. make_directory + create_file for a transition
    that only needs create_file). This function picks the single best match using
    word-overlap between abstract output names and grounded tool output/name tokens.
    If there is only one template, return it as-is.
    """
    if len(templates) <= 1:
        return templates

    abstract_words = set(
        w for name in abstract_outputs for w in name.lower().replace("_", " ").split()
    )

    def score(entry: tuple[str, dict, dict]) -> int:
        tool_name, _, _ = entry
        # Score against tool name only — abstract outputs encode the step's semantic
        # intent, and tool names reflect that more reliably than output key names.
        name_words = set(tool_name.lower().replace("_", " ").split())
        return len(abstract_words & name_words)

    scores = [score(t) for t in templates]
    best = max(scores)
    # If best score is 0 (no overlap at all), fall back to first entry
    if best == 0:
        return [templates[0]]
    # Return all templates tied at the best score (preserves multi-tool sequences
    # when they are all equally relevant)
    return [t for t, s in zip(templates, scores) if s == best]


def _close_json(text: str) -> str:
    """Append missing closing brackets and braces to a truncated JSON string."""
    brace, bracket, in_string, escape = 0, 0, False, False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
    return text + "]" * bracket + "}" * brace


def _parse_json_like(value: object) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        try:
            return literal_eval(text)
        except (ValueError, SyntaxError):
            pass
    return None
