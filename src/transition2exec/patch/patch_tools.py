from __future__ import annotations

from typing import Any, Callable, Dict, List

from transition2exec.tool_catalog import GroundedTool, ToolSignature


# ---------------------------------------------------------------------------
# Pure patching functions
# Each function accepts a resolved inputs dict and returns {result_key: value}.
# ---------------------------------------------------------------------------

def count_list(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs["items"]
    result_key = inputs["result_key"]
    return {result_key: len(items)}


def get_first(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs["items"]
    result_key = inputs["result_key"]
    return {result_key: items[0] if items else None}


def cast_int(inputs: Dict[str, Any]) -> Dict[str, Any]:
    value = inputs["value"]
    result_key = inputs["result_key"]
    return {result_key: int(value)}


def cast_float(inputs: Dict[str, Any]) -> Dict[str, Any]:
    value = inputs["value"]
    result_key = inputs["result_key"]
    return {result_key: float(value)}


def cast_str(inputs: Dict[str, Any]) -> Dict[str, Any]:
    value = inputs["value"]
    result_key = inputs["result_key"]
    return {result_key: str(value)}


def split_lines(inputs: Dict[str, Any]) -> Dict[str, Any]:
    text = inputs["text"]
    result_key = inputs["result_key"]
    return {result_key: [line for line in text.splitlines() if line.strip()]}


def join_list(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs["items"]
    sep = inputs.get("sep", ",")
    result_key = inputs["result_key"]
    return {result_key: sep.join(str(i) for i in items)}


def filter_suffix(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs["items"]
    suffix = inputs["suffix"]
    result_key = inputs["result_key"]
    return {result_key: [item for item in items if str(item).endswith(suffix)]}


# ---------------------------------------------------------------------------
# Registry — used by the executor to run patch transitions
# ---------------------------------------------------------------------------

PATCH_TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "count_list": count_list,
    "get_first": get_first,
    "cast_int": cast_int,
    "cast_float": cast_float,
    "cast_str": cast_str,
    "split_lines": split_lines,
    "join_list": join_list,
    "filter_suffix": filter_suffix,
}


# ---------------------------------------------------------------------------
# Catalog — GroundedTool descriptors passed to the LLM as patching_tools
# ---------------------------------------------------------------------------

PATCH_TOOLS: List[GroundedTool] = [
    GroundedTool(
        name="count_list",
        signature=ToolSignature(inputs=["items", "result_key"], outputs=["result_key"]),
        description="Counts elements in a list. `items`: list. `result_key`: output key name. Returns {result_key: int}.",
    ),
    GroundedTool(
        name="get_first",
        signature=ToolSignature(inputs=["items", "result_key"], outputs=["result_key"]),
        description="Returns the first element of a list. `items`: list. `result_key`: output key name. Returns {result_key: any}.",
    ),
    GroundedTool(
        name="cast_int",
        signature=ToolSignature(inputs=["value", "result_key"], outputs=["result_key"]),
        description="Casts a string or float to int. `value`: str|float. `result_key`: output key name. Returns {result_key: int}.",
    ),
    GroundedTool(
        name="cast_float",
        signature=ToolSignature(inputs=["value", "result_key"], outputs=["result_key"]),
        description="Casts a string to float. `value`: str. `result_key`: output key name. Returns {result_key: float}.",
    ),
    GroundedTool(
        name="cast_str",
        signature=ToolSignature(inputs=["value", "result_key"], outputs=["result_key"]),
        description="Converts any value to string. `value`: any. `result_key`: output key name. Returns {result_key: str}.",
    ),
    GroundedTool(
        name="split_lines",
        signature=ToolSignature(inputs=["text", "result_key"], outputs=["result_key"]),
        description="Splits a multi-line string into a list of non-empty lines. `text`: str. `result_key`: output key name. Returns {result_key: list[str]}.",
    ),
    GroundedTool(
        name="join_list",
        signature=ToolSignature(inputs=["items", "sep", "result_key"], outputs=["result_key"]),
        description="Joins list elements into a string with separator. `items`: list. `sep`: str. `result_key`: output key name. Returns {result_key: str}.",
    ),
    GroundedTool(
        name="filter_suffix",
        signature=ToolSignature(inputs=["items", "suffix", "result_key"], outputs=["result_key"]),
        description="Filters list to items ending with `suffix`. `items`: list[str]. `suffix`: str (e.g. '.py'). `result_key`: output key name. Returns {result_key: list}.",
    ),
]

PATCH_TOOL_BY_NAME: Dict[str, GroundedTool] = {t.name: t for t in PATCH_TOOLS}
