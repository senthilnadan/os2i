"""Batch runner for /patchTaskExecutionOutcomeToAbstractOutcome seeds.

Usage:
    python training/run_patch_batch.py [--seed seed/patch_seed.json] [--output results.jsonl]
"""
import argparse
import json
from pathlib import Path

from transition2exec.api.models import (
    AbstractTransition,
    ExecutionOutcome,
    PatchRequest,
)
from transition2exec.patch.patch_tools import PATCH_TOOLS
from transition2exec.patch.service import patch_service
from transition2exec.patch.dspy_module import PatchResolutionModule
from transition2exec.patch.service import DSPyPatchBackend
from transition2exec.tool_catalog import DEFAULT_TOOLS, GroundedTool, ToolSignature


# ---------------------------------------------------------------------------
# Seed loading
# ---------------------------------------------------------------------------

def _seed_tool_to_grounded(raw: dict) -> GroundedTool:
    """Convert seed patching_tool format (inputs as list of {name, type}) to GroundedTool."""
    inputs = [i["name"] if isinstance(i, dict) else i for i in raw.get("inputs", [])]
    outputs = [o["name"] if isinstance(o, dict) else o for o in raw.get("outputs", [])]
    # Strip angle brackets from output names like "<result_key>"
    outputs = [o.strip("<>") for o in outputs]
    return GroundedTool(
        name=raw["name"],
        description=raw.get("description", ""),
        signature=ToolSignature(inputs=inputs, outputs=outputs),
    )


def _load_seed(seed_path: Path) -> tuple[list[dict], list[GroundedTool]]:
    data = json.loads(seed_path.read_text())
    raw_patching = data.get("patching_tools", [])
    patching_tools = [_seed_tool_to_grounded(t) for t in raw_patching] if raw_patching else PATCH_TOOLS
    return data.get("seeds", []), patching_tools


def _build_request(entry: dict, patching_tools: list[GroundedTool]) -> PatchRequest:
    return PatchRequest(
        task=entry["task"],
        abstract_transition=AbstractTransition.model_validate(entry["abstract_transition"]),
        execution_outcome=ExecutionOutcome.model_validate(entry["execution_outcome"]),
        state=entry.get("state", {}),
        available_tools=[t.model_copy(deep=True) for t in DEFAULT_TOOLS],
        patching_tools=patching_tools,
    )


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def _check_verdict(response_dict: dict, expected: dict) -> str:
    """Return 'PASS', 'MISMATCH: ...', or 'FAIL: ...'."""
    exp_status = expected.get("status")
    actual_status = response_dict.get("status")

    if actual_status != exp_status:
        return f"FAIL: status={actual_status}, expected={exp_status}"

    if exp_status == "not_resolvable":
        return "PASS"

    # resolved — check patch_transitions
    actual_pts = response_dict.get("patch_transitions") or []
    expected_pts = expected.get("patch_transitions") or []

    if len(actual_pts) != len(expected_pts):
        actual_tools = [pt.get("tool") for pt in actual_pts]
        exp_tools = [pt.get("tool") for pt in expected_pts]
        return f"MISMATCH: got {len(actual_pts)} transitions {actual_tools}, expected {len(expected_pts)} {exp_tools}"

    mismatches = []
    for i, (apt, ept) in enumerate(zip(actual_pts, expected_pts)):
        step = f"patch_t{i + 1}"
        if apt.get("tool") != ept.get("tool"):
            mismatches.append(f"{step} WRONG_TOOL: got '{apt.get('tool')}', expected '{ept.get('tool')}'")
            continue
        # Check result_key alignment — the critical correctness signal
        exp_inputs = ept.get("inputs", {})
        act_inputs = apt.get("inputs", {})
        if "result_key" in exp_inputs and act_inputs.get("result_key") != exp_inputs["result_key"]:
            mismatches.append(
                f"{step} WRONG_RESULT_KEY: got '{act_inputs.get('result_key')}', expected '{exp_inputs['result_key']}'"
            )

    return "PASS" if not mismatches else "MISMATCH: " + "; ".join(mismatches)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_batch(seed_path: Path, limit: int | None = None, output: Path | None = None) -> None:
    print(f"Running patch batch from {seed_path}")
    seeds, patching_tools = _load_seed(seed_path)
    handle = output.open("w") if output else None

    passed = 0
    total = 0
    for idx, entry in enumerate(seeds):
        if limit is not None and idx >= limit:
            break
        total += 1
        seed_id = entry.get("id", str(idx))

        request = _build_request(entry, patching_tools)
        response = patch_service.resolve(request)
        response_dict = response.model_dump()

        # Capture stage1 plan if LLM backend is active
        stage1_plan = None
        backend = patch_service._backend
        if isinstance(backend, DSPyPatchBackend):
            missing = [k for k in request.abstract_transition.outputs if k not in (request.state or {})]
            if missing:
                try:
                    stage1_plan = backend._module._resolve_patch_plan(request, missing)
                except Exception as exc:
                    stage1_plan = f"ERROR: {exc}"

        expected = entry.get("expected", {})
        verdict = _check_verdict(response_dict, expected)
        if verdict == "PASS":
            passed += 1

        result = {
            "id": seed_id,
            "pattern": entry.get("pattern"),
            "task": entry["task"],
            "expected_status": expected.get("status"),
            "actual_status": response.status,
            "stage1_plan": stage1_plan,
            "patch_transitions": response_dict.get("patch_transitions"),
            "reason": response_dict.get("reason"),
            "verdict": verdict,
        }
        text = json.dumps(result, indent=2)
        if handle:
            handle.write(text + "\n")
        else:
            print(f"[{seed_id}] {verdict}  — {entry['task'][:60]}")
            if verdict != "PASS":
                if stage1_plan:
                    print(f"  stage1: {stage1_plan.strip()[:200]}")
                print(f"  actual:   {response_dict.get('patch_transitions') or response_dict.get('reason')}")
                print(f"  expected: {expected.get('patch_transitions') or expected.get('reason')}")

    print(f"\n{'='*40}")
    print(f"Result: {passed}/{total} passed")
    if handle:
        handle.close()
        print(f"Written to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay patch seeds through /patchTaskExecutionOutcomeToAbstractOutcome")
    parser.add_argument("--seed", type=Path, default=Path("seed/patch_seed.json"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    run_batch(args.seed, args.limit, args.output)


if __name__ == "__main__":
    main()
