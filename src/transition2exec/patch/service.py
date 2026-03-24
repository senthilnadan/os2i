from __future__ import annotations

from abc import ABC, abstractmethod

import dspy

from transition2exec.api.models import PatchRequest, PatchResponse
from transition2exec.config import settings
from transition2exec.patch.dspy_module import PatchResolutionModule


class PatchBackend(ABC):
    @abstractmethod
    def resolve(self, request: PatchRequest) -> PatchResponse:
        raise NotImplementedError


class StubPatchBackend(PatchBackend):
    """Deterministic fallback — always signals not_resolvable.

    Keeps the service operational when no LLM is configured. The executor
    treats not_resolvable as abort_and_heal, which is the safe default.
    """

    def resolve(self, request: PatchRequest) -> PatchResponse:
        return PatchResponse(
            status="not_resolvable",
            reason="stub backend: no LLM configured for patch resolution",
        )


class DSPyPatchBackend(PatchBackend):
    def __init__(self, lm: dspy.LM) -> None:
        self._module = PatchResolutionModule(lm)

    def resolve(self, request: PatchRequest) -> PatchResponse:
        return self._module.generate_patch_response(request)


class PatchService:
    def __init__(self, backend: PatchBackend) -> None:
        self._backend = backend

    def resolve(self, request: PatchRequest) -> PatchResponse:
        # If missing_outputs not supplied, compute from abstract_transition vs state
        if not request.missing_outputs:
            missing = [k for k in request.abstract_transition.outputs if k not in (request.state or {})]
            request = request.model_copy(update={"missing_outputs": missing})

        if not request.missing_outputs:
            # Nothing missing — gap already closed, nothing to do
            return PatchResponse(status="resolved", patch_transitions=[])

        return self._backend.resolve(request)


def _build_lm(model: str, api_base: str, api_key: str) -> dspy.LM:
    return dspy.LM(
        f"openai/{model}",
        api_base=api_base,
        api_key=api_key,
        temperature=settings.model_temperature,
        max_tokens=512,
    )


def build_patch_service() -> PatchService:
    if settings.backend == "qwen":
        lm = _build_lm(settings.qwen_model_name, settings.qwen_api_base, "ollama")
        return PatchService(DSPyPatchBackend(lm))
    if settings.backend == "ollama":
        lm = _build_lm(settings.ollama_reasoning_model, settings.ollama_base_url, "ollama")
        return PatchService(DSPyPatchBackend(lm))
    if settings.backend == "openai_compatible":
        api_key = settings.openai_api_key or "openai-compatible"
        lm = _build_lm(settings.openai_reasoning_model, settings.openai_base_url, api_key)
        return PatchService(DSPyPatchBackend(lm))
    return PatchService(StubPatchBackend())


patch_service = build_patch_service()
