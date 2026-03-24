import argparse
import json
from pathlib import Path

from transition2exec.api.models import AbstractTransition, GroundedTool, Transition2ExecRequest
from transition2exec.service import service as transition2exec_service
from transition2exec.tool_catalog import DEFAULT_TOOLS
from transition2exec.transition.providers import DSPyTransition2ExecBackend


def _load_tools(tools_raw: list | None) -> list[GroundedTool]:
    if not tools_raw:
        return [t.model_copy(deep=True) for t in DEFAULT_TOOLS]
    return [GroundedTool.model_validate(t) for t in tools_raw]


def _load_request(entry: dict, shared_tools: list[GroundedTool]) -> Transition2ExecRequest:
    transition = AbstractTransition.model_validate(
        entry.get("abstract_transition")
        or entry["expected_abstract_dstt"]["segments"][0]["transitions"][0]
    )
    # entry-level available_tools override shared; fall back to shared, then DEFAULT_TOOLS
    available_tools = _load_tools(entry.get("available_tools")) if entry.get("available_tools") else shared_tools
    return Transition2ExecRequest(
        task=entry["task"],
        context=entry.get("context"),
        abstract_transition=transition,
        available_tools=available_tools,
    )


def _check_expected(result_dstt: dict, expected: dict | None) -> str | None:
    """Return None if expected matches, or an error string describing the mismatch."""
    if not expected:
        return None
    transitions = (result_dstt.get("segments") or [{}])[0].get("transitions") or []
    if not transitions:
        return "no transitions produced"
    t = transitions[0]
    actual_tool = t.get("tool")
    if actual_tool != expected.get("tool"):
        return f"WRONG_TOOL: got '{actual_tool}', expected '{expected['tool']}'"
    if "inputs" in expected:
        actual_inputs = t.get("inputs", {})
        for key, exp_val in expected["inputs"].items():
            if actual_inputs.get(key) != exp_val:
                return f"WRONG_INPUT[{key}]: got '{actual_inputs.get(key)}', expected '{exp_val}'"
    return None


def _load_entries(seed_path: Path) -> tuple[list[dict], list[GroundedTool]]:
    """Support both JSONL and JSON-with-seeds-array formats."""
    raw = seed_path.read_text().strip()
    if raw.startswith("{"):
        data = json.loads(raw)
        shared_tools = _load_tools(data.get("available_tools"))
        return data.get("seeds", []), shared_tools
    # JSONL
    entries = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return entries, [t.model_copy(deep=True) for t in DEFAULT_TOOLS]


def run_batch(
    seed_path: Path, limit: int | None = None, output: Path | None = None
) -> None:
    print(f"Running batch from {seed_path}")
    entries, shared_tools = _load_entries(seed_path)
    handle = output.open("w") if output else None

    passed = 0
    total = 0
    for idx, entry in enumerate(entries):
        if limit is not None and idx >= limit:
            break
        total += 1
        request = _load_request(entry, shared_tools)

        stage1_plan, stage2_raw = None, None
        backend = transition2exec_service.backend
        if isinstance(backend, DSPyTransition2ExecBackend):
            stage1_plan, stage2_raw = backend.program.run_stages(request)

        response = transition2exec_service.build_plan(request)
        exec_dstt = {
            "status": response.executable_dstt.status,
            "segments": [s.model_dump() for s in response.executable_dstt.segments],
        }

        expected = entry.get("expected")
        mismatch = _check_expected(exec_dstt, expected) if response.executable_dstt.status == "ok" else None
        ok = response.executable_dstt.status == "ok" and mismatch is None
        if ok:
            passed += 1

        result = {
            "id": entry.get("id"),
            "task": entry["task"],
            "abstract_transition": request.abstract_transition.model_dump(),
            "expected": expected,
            "stage1_tool_sequence": stage1_plan,
            "stage2_dstt_raw": stage2_raw,
            "execdstt": exec_dstt,
            "meta_status": response.meta.status,
            "meta_detail": response.meta.detail,
            "verdict": "PASS" if ok else ("MISMATCH: " + mismatch if mismatch else "FAIL"),
        }
        text = json.dumps(result, indent=2)
        if handle:
            handle.write(text + "\n")
        else:
            verdict = result["verdict"]
            print(f"[{entry.get('id', idx)}] {verdict}  — {entry['task']}")
            if not ok:
                print(f"  stage1: {stage1_plan}")
                print(f"  status: {response.executable_dstt.status}  detail: {response.meta.detail}")

    print(f"\n{'='*40}")
    print(f"Result: {passed}/{total} passed")
    if handle:
        handle.close()
        print(f"Written to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay seed tasks through Transition2Exec")
    parser.add_argument("--seed", type=Path, default=Path("seed/live_tasks.jsonl"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    run_batch(args.seed, args.limit, args.output)


if __name__ == "__main__":
    main()
