from __future__ import annotations

from transition2exec.api.models import (
    ExecutableDSTT,
    ExecutableSegment,
    ExecutableTransition,
    Meta,
    Transition2ExecRequest,
    Transition2ExecResponse,
)
from transition2exec.config import settings
from transition2exec.transition.providers import build_backend
from transition2exec.validation import validate_executable_dstt


class Transition2ExecService:
    def __init__(self) -> None:
        self.backend = build_backend()

    def build_plan(self, request: Transition2ExecRequest) -> Transition2ExecResponse:
        task = request.task.strip()
        if self._requires_context_and_constraints(task, request.context, request.constraints or {}):
            return Transition2ExecResponse(
                executable_dstt=self._clarification_dstt(task, request.context),
                meta=Meta(
                    status="ambiguous",
                    model=self.backend.model_name,
                    version=settings.prompt_version,
                    detail=(
                        "Ask for missing context and constraints with getOrAskContextAndConstraints, "
                        "then call transition2exec again."
                    ),
                ),
            )

        try:
            executable_dstt = self.backend.generate_executable_dstt(request)
            validate_executable_dstt(executable_dstt, request.available_tools, request.context or {})
        except ValueError as exc:
            return Transition2ExecResponse(
                executable_dstt=ExecutableDSTT(status="not_mappable", segments=[]),
                meta=Meta(
                    status="error",
                    model=self.backend.model_name,
                    version=settings.prompt_version,
                    detail=str(exc),
                ),
            )
        except Exception as exc:
            return Transition2ExecResponse(
                executable_dstt=ExecutableDSTT(status="not_mappable", segments=[]),
                meta=Meta(
                    status="error",
                    model=self.backend.model_name,
                    version=settings.prompt_version,
                    detail=f"Backend failure: {exc}",
                ),
            )

        status = "ok"
        detail = None
        if executable_dstt.status == "needs_decomposition":
            status = "ambiguous"
            detail = (
                "Feasibility review requested decomposition or clarification for this transition."
            )
        elif executable_dstt.status == "not_mappable":
            status = "error"
            detail = (
                (executable_dstt.context or {}).get("reason")
                or "Unable to map the abstract transition using the grounded tool catalog."
            )
        elif self._looks_low_confidence(task, request.context, request.constraints or {}):
            status = "low_confidence"
            detail = (
                "The request can be compiled, but key operational details were not provided."
            )

        return Transition2ExecResponse(
            executable_dstt=executable_dstt,
            meta=Meta(
                status=status,
                model=self.backend.model_name,
                version=settings.prompt_version,
                detail=detail,
            ),
        )

    def _clarification_dstt(
        self, task: str, context: dict[str, str] | None
    ) -> ExecutableDSTT:
        stages = []
        stages.append(
            ExecutableSegment(
                transitions=[
                    ExecutableTransition(
                        id="t1",
                        tool="getOrAskContextAndConstraints",
                        inputs={"task": task, **(context or {})},
                        outputs={"context": None, "constraints": None},
                    )
                ],
                milestone=["context", "constraints"],
            )
        )
        stages.append(
            ExecutableSegment(
                transitions=[
                    ExecutableTransition(
                        id="t2",
                        tool="transition2exec",
                        inputs={"task": task},
                        outputs={"executable_dstt": None},
                    )
                ],
                milestone=["executable_dstt"],
            )
        )
        return ExecutableDSTT(
            status="needs_decomposition",
            segments=stages,
            context={"resolved_by": "Transition2Exec", "notes": "Clarify and retry."},
        )

    def _requires_context_and_constraints(
        self, task: str, context: dict | None, constraints: dict[str, object]
    ) -> bool:
        return len(task.split()) < 5 and not context and not constraints

    def _looks_low_confidence(
        self, task: str, context: dict | None, constraints: dict[str, object]
    ) -> bool:
        return len(task.split()) < 8 and not context and not constraints


service = Transition2ExecService()
