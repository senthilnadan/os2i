from __future__ import annotations

from abc import ABC, abstractmethod

import dspy

from transition2exec.api.models import (
    ExecutableDSTT,
    ExecutableSegment,
    ExecutableTransition,
    Transition2ExecRequest,
)
from transition2exec.config import settings
from transition2exec.transition.dspy_module import Transition2ExecChainOfThought
from transition2exec.transition.mapping import default_output_value, resolve_input


class Transition2ExecBackend(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_executable_dstt(self, request: Transition2ExecRequest) -> ExecutableDSTT:
        raise NotImplementedError


class StubTransition2ExecBackend(Transition2ExecBackend):
    @property
    def model_name(self) -> str:
        return settings.model_name

    def generate_executable_dstt(self, request: Transition2ExecRequest) -> ExecutableDSTT:
        segmented = self._compile_transition(request)
        status = "ok" if segmented else "not_mappable"
        return ExecutableDSTT(
            status=status,
            segments=[segmented] if segmented else [],
            context={
                "resolved_by": "Transition2Exec",
                "notes": "Mapped abstract transition to grounded tool.",
                **(request.context or {}),
            },
        )

    def _compile_transition(self, request: Transition2ExecRequest) -> ExecutableSegment | None:
        name = request.abstract_transition.tool.lower()
        tool = next(
            (t for t in request.available_tools if t.name.lower() == name or name in t.name.lower()),
            None,
        )
        if not tool:
            return None
        inputs = {n: resolve_input(n, request.context) for n in tool.signature.inputs}
        outputs = {n: default_output_value(n) for n in tool.signature.outputs}
        inputs = {k: v for k, v in inputs.items() if v is not None}
        return ExecutableSegment(
            transitions=[ExecutableTransition(
                id=request.abstract_transition.id,
                tool=tool.name,
                inputs=inputs,
                outputs=outputs,
            )],
            milestone=tool.signature.outputs,
        )


class DSPyTransition2ExecBackend(Transition2ExecBackend):
    def __init__(self, lm: dspy.LM) -> None:
        super().__init__()
        self.program = Transition2ExecChainOfThought(lm)

    @property
    def model_name(self) -> str:
        return settings.qwen_model_name

    def generate_executable_dstt(self, request: Transition2ExecRequest) -> ExecutableDSTT:
        return self.program.generate_executable_dstt(request)


def _build_lm(model: str, api_base: str, api_key: str) -> dspy.LM:
    return dspy.LM(
        f"openai/{model}",
        api_base=api_base,
        api_key=api_key,
        temperature=settings.model_temperature,
        max_tokens=512,
    )


def build_backend() -> Transition2ExecBackend:
    if settings.backend == "qwen":
        lm = _build_lm(settings.qwen_model_name, settings.qwen_api_base, "ollama")
        return DSPyTransition2ExecBackend(lm)
    if settings.backend == "ollama":
        lm = _build_lm(settings.ollama_reasoning_model, settings.ollama_base_url, "ollama")
        return DSPyTransition2ExecBackend(lm)
    if settings.backend == "openai_compatible":
        api_key = settings.openai_api_key or "openai-compatible"
        lm = _build_lm(settings.openai_reasoning_model, settings.openai_base_url, api_key)
        return DSPyTransition2ExecBackend(lm)
    return StubTransition2ExecBackend()
