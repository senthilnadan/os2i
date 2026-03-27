from __future__ import annotations

import json
from pathlib import Path

import dspy

from transition2exec.api.models import (
    ExecutableDSTT,
    ExecutableSegment,
    ExecutableTransition,
    Transition2ExecRequest,
)

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def _load(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


TOOL_SEQUENCE_TEMPLATE = _load("tool_sequence.md")


class Transition2ExecChainOfThought(dspy.Module):
    def __init__(self, lm: dspy.LM):
        super().__init__()
        self.lm = lm

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
            return self._build_dstt(tool_plan, request)
        except Exception as exc:
            return ExecutableDSTT(
                status="not_mappable",
                segments=[],
                context={"stage": "1.5", "reason": str(exc), "tool_plan": tool_plan},
            )

    def _resolve_tool_plan(self, request: Transition2ExecRequest) -> str:
        tool_list = "\n".join(
            f"- {t.name} [inputs: {', '.join(t.signature.inputs)}]: {t.description}"
            for t in request.available_tools
        )
        state_keys = ", ".join((request.context or {}).keys()) or "(empty)"
        prompt = TOOL_SEQUENCE_TEMPLATE.format(
            task=request.task,
            abstract_tool=request.abstract_transition.tool,
            abstract_inputs=", ".join(request.abstract_transition.inputs),
            abstract_outputs=", ".join(request.abstract_transition.outputs),
            state_keys=state_keys,
            tool_list=tool_list,
        )
        completion = self.lm(messages=[{"role": "user", "content": prompt}])
        return completion[0] if isinstance(completion, list) and completion else str(completion)

    def _build_dstt(self, tool_plan: str, request: Transition2ExecRequest) -> ExecutableDSTT:
        """Stage 1.5 — parse TOOL/BIND, resolve values from state, construct DSTT programmatically."""
        lookup = {t.name: t for t in request.available_tools}
        state = request.context or {}

        # Check for STATUS: ambiguous from stage 1
        for line in tool_plan.splitlines():
            if line.strip().upper().startswith("STATUS:"):
                status_val = line.split(":", 1)[1].strip().lower()
                if status_val == "ambiguous":
                    reason = ""
                    for l in tool_plan.splitlines():
                        if l.strip().upper().startswith("REASON:"):
                            reason = l.split(":", 1)[1].strip()
                    return ExecutableDSTT(
                        status="not_mappable",
                        segments=[],
                        context={"stage": "1", "reason": reason, "tool_plan": tool_plan},
                    )

        # Parse TOOL and BIND lines
        tool_name: str | None = None
        bindings: dict[str, str] = {}
        for line in tool_plan.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("TOOL:"):
                tool_name = stripped.split(":", 1)[1].strip()
            elif stripped.upper().startswith("BIND:"):
                for part in stripped.split(":", 1)[1].split(","):
                    part = part.strip()
                    # support both <- and = as separators
                    if "<-" in part:
                        k, _, v = part.partition("<-")
                    elif "=" in part:
                        k, _, v = part.partition("=")
                    else:
                        continue
                    v = v.strip().strip('"')
                    if v and v != "-":   # "-" is a sentinel meaning no binding found
                        bindings[k.strip()] = v

        if not tool_name:
            return ExecutableDSTT(
                status="not_mappable",
                segments=[],
                context={"stage": "1.5", "reason": "no TOOL line in stage 1 output", "tool_plan": tool_plan},
            )

        tool = lookup.get(tool_name)
        if not tool:
            return ExecutableDSTT(
                status="not_mappable",
                segments=[],
                context={"stage": "1.5", "reason": f"tool '{tool_name}' not in available_tools", "tool_plan": tool_plan},
            )

        # Input resolution — input signature only, output signature never in scope
        inputs: dict[str, str] = {}
        ambiguous_keys: list[str] = []
        for input_key in tool.signature.inputs:
            bind_key = bindings.get(input_key, input_key)
            if bind_key in state:
                inputs[input_key] = state[bind_key]        # exact copy from state via binding
            elif input_key in state:
                inputs[input_key] = state[input_key]       # direct state match fallback
            elif bind_key and bind_key != input_key:
                inputs[input_key] = bind_key               # LLM provided a literal value in BIND
            else:
                result = self._extract_value(input_key, request.task)
                if result is None:
                    ambiguous_keys.append(input_key)
                else:
                    inputs[input_key] = result

        if ambiguous_keys:
            return ExecutableDSTT(
                status="not_mappable",
                segments=[],
                context={
                    "stage": "1.5",
                    "reason": f"could not resolve inputs: {ambiguous_keys}",
                    "tool_plan": tool_plan,
                },
            )

        # Output binding — output signature only, input signature never in scope
        outputs = {k: None for k in tool.signature.outputs}

        transition = ExecutableTransition(
            id=request.abstract_transition.id,
            tool=tool.name,
            inputs=inputs,
            outputs=outputs,
        )
        segment = ExecutableSegment(
            transitions=[transition],
            milestone=list(tool.signature.outputs),
        )
        return ExecutableDSTT(
            status="ok",
            segments=[segment],
            context={"tool_plan": tool_plan},
        )

    def run_stages(self, request: Transition2ExecRequest) -> tuple[str | None, str | None]:
        """Compatibility shim for batch runner: returns (stage1_plan, stage2_raw).
        In v1.1 there is no stage 2; stage2_raw is always None."""
        try:
            stage1_plan = self._resolve_tool_plan(request)
        except Exception:
            stage1_plan = None
        return stage1_plan, None

    def _extract_value(self, input_key: str, task: str) -> str | None:
        """Narrow LLM call to derive a single input value from task text.

        Returns None (mark ambiguous) if the model returns empty, null, or echoes the key name.
        """
        prompt = (
            f"Task: {task}\n\n"
            f"What value should be used for the input '{input_key}'?\n"
            f"Respond with only the value, no explanation."
        )
        completion = self.lm(messages=[{"role": "user", "content": prompt}])
        raw = completion[0] if isinstance(completion, list) and completion else str(completion)
        result = raw.strip().strip('"')
        if not result or result.lower() in ("null", "none") or result == input_key:
            return None
        return result


def _select_best_match(
    templates: list[tuple[str, dict, dict]],
    abstract_outputs: list[str],
) -> list[tuple[str, dict, dict]]:
    """Select templates whose grounded tool outputs best match the abstract outputs."""
    if len(templates) <= 1:
        return templates

    abstract_words = set(
        w for name in abstract_outputs for w in name.lower().replace("_", " ").split()
    )

    def score(entry: tuple[str, dict, dict]) -> int:
        tool_name, _, _ = entry
        name_words = set(tool_name.lower().replace("_", " ").split())
        return len(abstract_words & name_words)

    scores = [score(t) for t in templates]
    best = max(scores)
    if best == 0:
        return [templates[0]]
    return [t for t, s in zip(templates, scores) if s == best]
