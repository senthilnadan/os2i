from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from transition2exec.tool_catalog import DEFAULT_TOOLS, GroundedTool


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=1)
    context: Dict[str, Any] | None = None
    constraints: Dict[str, Any] | None = None

    @field_validator("task")
    @classmethod
    def task_must_have_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task must not be empty")
        return value.strip()

    @field_validator("context")
    @classmethod
    def normalize_context(cls, value: Dict[str, Any] | None) -> Dict[str, Any] | None:
        return value or None


class AbstractTransition(BaseModel):
    id: str
    tool: str
    inputs: List[str]
    outputs: List[str]
    output_type: Dict[str, str] = {}
    complexityTime: str = ""
    complexitySpace: str = ""
    skill_required: List[str] = []
    resource_required: List[str] = []


class AbstractSegment(BaseModel):
    transitions: List[AbstractTransition]
    milestone: List[str]


class AbstractDSTT(BaseModel):
    segments: List[AbstractSegment]


class Transition2ExecRequest(TaskRequest):
    abstract_transition: AbstractTransition
    available_tools: List[GroundedTool] = Field(
        default_factory=lambda: [tool.model_copy(deep=True) for tool in DEFAULT_TOOLS]
    )


class ExecutableTransition(BaseModel):
    id: str
    tool: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]


class ExecutableSegment(BaseModel):
    transitions: List[ExecutableTransition]
    milestone: List[str]


class ExecutableDSTT(BaseModel):
    status: Literal["ok", "needs_decomposition", "not_mappable"]
    segments: List[ExecutableSegment]
    context: Dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Patch service models
# ---------------------------------------------------------------------------

class ExecutionOutcome(BaseModel):
    tool: str
    outputs: Dict[str, Any]


class PatchRequest(BaseModel):
    task: str
    abstract_transition: AbstractTransition
    execution_outcome: ExecutionOutcome
    state: Dict[str, Any] = {}
    available_tools: List[GroundedTool] = Field(
        default_factory=lambda: [tool.model_copy(deep=True) for tool in DEFAULT_TOOLS]
    )
    patching_tools: Optional[List[GroundedTool]] = None
    missing_outputs: Optional[List[str]] = None


class PatchTransition(BaseModel):
    id: str
    tool: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]


class PatchResponse(BaseModel):
    status: Literal["resolved", "not_resolvable"]
    patch_transitions: Optional[List[PatchTransition]] = None
    reason: Optional[str] = None


class Meta(BaseModel):
    status: Literal["ok", "ambiguous", "low_confidence", "error"]
    model: str
    version: str
    detail: str | None = None


class Transition2ExecResponse(BaseModel):
    executable_dstt: ExecutableDSTT
    meta: Meta
