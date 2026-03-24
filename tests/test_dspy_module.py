from transition2exec.api.models import AbstractTransition, Transition2ExecRequest
from transition2exec.tool_catalog import DEFAULT_TOOLS
from transition2exec.transition.dspy_module import Transition2ExecChainOfThought, _parse_json_like


def _sample_transition() -> AbstractTransition:
    return AbstractTransition(
        id="t1",
        tool="read_python_file",
        inputs=["file_path"],
        outputs=["file_contents"],
        output_type={"file_contents": "string"},
        complexityTime="O(n)",
        complexitySpace="O(1)",
        skill_required=["programmer"],
        resource_required=["filesystem"],
    )


def test_parse_json_like_handles_code_block_and_literal():
    json_block = "```json\n{\"foo\": [1, 2, 3]}\n```"
    literal_block = "[{'tool': 'read_file', 'inputs': {}, 'outputs': {}}]"

    assert _parse_json_like(json_block) == {"foo": [1, 2, 3]}
    assert _parse_json_like(literal_block) == [
        {"tool": "read_file", "inputs": {}, "outputs": {}},
    ]


def test_resolve_tool_plan_prompt_contains_key_fields():
    chain = Transition2ExecChainOfThought(lm=object())
    request = Transition2ExecRequest(
        task="Read hello.py",
        context={"project_folder_path": "/tmp", "target_file": "hello.py"},
        abstract_transition=_sample_transition(),
        available_tools=DEFAULT_TOOLS,
    )

    # Reach into the prompt directly by formatting the template
    from transition2exec.transition.dspy_module import TOOL_SEQUENCE_TEMPLATE
    import json
    tool_list = "\n".join(f"- {t.name}: {t.description}" for t in DEFAULT_TOOLS)
    prompt = TOOL_SEQUENCE_TEMPLATE.format(
        task=request.task,
        abstract_tool=request.abstract_transition.tool,
        abstract_outputs=", ".join(request.abstract_transition.outputs),
        context=json.dumps(request.context or {}, default=str),
        tool_list=tool_list,
    )

    assert "read_python_file" in prompt
    assert "read_file" in prompt
    assert "/tmp" in prompt
    assert "file_contents" in prompt
