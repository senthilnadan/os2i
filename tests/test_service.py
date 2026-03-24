import os
import pytest

os.environ.setdefault("TRANSITION2EXEC_BACKEND", "stub")
from transition2exec.api.models import (
    AbstractTransition,
    Transition2ExecRequest,
    ExecutableDSTT,
    ExecutableSegment,
    ExecutableTransition,
)
from transition2exec.service import service
from transition2exec.tool_catalog import DEFAULT_TOOLS
from transition2exec.validation import validate_executable_dstt


def _sample_transition() -> AbstractTransition:
    return AbstractTransition(
        id="t1",
        tool="check_python_file_existence",
        inputs=["project_folder_path", "target_file"],
        outputs=["python_file_exists"],
        output_type={"python_file_exists": "bool"},
        complexityTime="O(n)",
        complexitySpace="O(1)",
        skill_required=["programmer"],
        resource_required=["filesystem"],
    )


def test_build_plan_requires_context():
    request = Transition2ExecRequest(
        task="Check hello file",
        abstract_transition=_sample_transition(),
    )

    response = service.build_plan(request)

    assert response.meta.status == "ambiguous"
    assert response.executable_dstt.status == "needs_decomposition"


def test_build_plan_generates_executable_dstt():
    request = Transition2ExecRequest(
        task="Check hello file",
        context={
            "project_folder_path": "/tmp",
            "target_file": "hello.py",
        },
        abstract_transition=_sample_transition(),
    )

    response = service.build_plan(request)

    assert response.meta.status in {"ok", "low_confidence"}
    assert response.executable_dstt.segments
    transition = response.executable_dstt.segments[0].transitions[0]
    assert transition.tool == "exists"
    assert "file_path" in transition.inputs
    assert transition.outputs.get("is_present") is not None


def test_validator_rejects_unknown_tool():
    dstt = ExecutableDSTT(
        status="ok",
        segments=[
            ExecutableSegment(
                transitions=[
                    ExecutableTransition(id="t0", tool="missing_tool", inputs={}, outputs={})
                ],
                milestone=["missing_tool"],
            )
        ],
    )

    with pytest.raises(ValueError):
        validate_executable_dstt(dstt, DEFAULT_TOOLS, {})
