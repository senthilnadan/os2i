# /patchTaskExecutionOutcomeToAbstractOutcome — Interface Spec

**Version:** 1.0 — for architect review
**Date:** 2026-03-22
**Owner:** DSTT Runtime — patch service coexists with transition2exec (port 8001)
**Called by:** taskexecutor kernel — only on gap detection
**Status:** Pending architect approval

---

## Summary

When transition2exec grounds an abstract transition to a tool that produces compatible but differently-shaped output, the abstract outputs may not land in state. This is not a failure of execution — the tool ran correctly — but a grounding gap. Rather than aborting, the executor calls `/patchTaskExecutionOutcomeToAbstractOutcome`. The patch service resolves the gap and returns ready-to-run transitions. The executor runs them and continues.

**The executor stays mechanical throughout.** It does not decide how to patch. It detects, delegates, executes, and continues — or aborts if the patch service cannot resolve.

---

## Boundary

| Concern                                | Owner          |
|----------------------------------------|----------------|
| Detect the gap                         | taskexecutor   |
| Call the patch service                 | taskexecutor   |
| Decide how to resolve                  | patch service  |
| Select patching tool or available tool | patch service  |
| Align output keys to abstract outputs  | patch service  |
| Run the returned transitions           | taskexecutor   |
| Abort and signal `abort_and_heal`      | taskexecutor   |
| Heal the abstract plan                 | DSTT Runtime   |

---

## When this is called

After all grounded transitions for one abstract transition complete, the executor checks:

```
abstract_transition.outputs: ["python_file_count"]
state after grounded tools:  {"entries": ["a.py", "b.py", "c.py"]}
→ "python_file_count" not in state → gap → call patch service
```

If no gap — abstract outputs are in state — no call is made. Normal execution continues.

---

## Request

```
POST /patchTaskExecutionOutcomeToAbstractOutcome
{
  "task": "string",

  "abstract_transition": {
    "id": "t1",
    "tool": "count_python_files",
    "inputs": ["directory_path"],
    "outputs": ["python_file_count"]
  },

  "execution_outcome": {
    "tool": "list_directory_recursive",
    "outputs": { "entries": ["a.py", "b.py", "c.py"] }
  },

  "state": { ...full state at gap point... },

  "available_tools": [ ...runtime execution catalog... ],
  "patching_tools":  [ ...patch-time transformation tool catalog... ]
}
```

**`available_tools`** — the runtime execution catalog (filesystem, shell tools). Same catalog used by transition2exec. Provided as grounding context for the patch service.

**`patching_tools`** — a separate catalog of pure, side-effect-free type-bridging tools. The executor holds this registry (`PATCH_TOOL_REGISTRY`) and passes it so the patch service knows what transformation tools are available to select from. These tools are never reachable during normal execution.

---

## Response

### Resolved

```json
{
  "status": "resolved",
  "patch_transitions": [
    {
      "id": "patch_t1",
      "tool": "count_list",
      "inputs": { "items": ["a.py", "b.py", "c.py"], "result_key": "python_file_count" },
      "outputs": { "python_file_count": null }
    }
  ]
}
```

The patch service returns one or more fully grounded `ExecutableTransition` objects. Output keys already match the abstract transition's declared outputs — no executor-side mapping or casting required. The executor runs each through the normal dispatch path and merges outputs into state.

**`result_key` convention:** patching tools accept an optional `result_key` input that names their output key. This is how the patch service aligns tool output to the abstract output name — the tool writes directly to the required key.

### Not resolved

```json
{
  "status": "not_resolvable",
  "reason": "no patching or available tool can bridge list[str] → int"
}
```

The executor fails with `abort_and_heal`. DSTT Runtime repair service heals the abstract plan.

---

## Status semantics

| Status            | Executor action                                     | DSTT Runtime action                |
|-------------------|-----------------------------------------------------|------------------------------------|
| `resolved`        | Run patch_transitions via normal dispatch, continue | None — execution proceeds          |
| `not_resolvable`  | Fail with `abort_and_heal`                          | Repair service heals abstract plan |

---

## Execution flow

```
kernel — abstract_transition t1
  → grounded transitions run
  → post-transition check: abstract outputs not in state → gap detected

  → call /patchTaskExecutionOutcomeToAbstractOutcome

    resolved →
      for each patch_transition:
        PATCH → DISPATCH → MERGE  (normal kernel path)
      abstract outputs now in state
      → continue to t2

    not_resolvable →
      ExecutionResult { status: "failed", error: "abort_and_heal" }
      → DSTT Runtime heals abstract plan
```

---

## Executor changes (minimal)

**1. Post-abstract-transition gap check** — one new block in `kernel.py` after the grounded transitions loop:

```python
# PATCH-Q1 (resolved): trigger on ANY missing abstract output, not only total miss.
missing = [k for k in abstract_transition.outputs if k not in state]
if missing:
    if patch_client:
        patch_result = patch_client.call(
            task, abstract_transition, last_grounded_outputs, state, catalog,
            missing_outputs=missing   # patch service targets only the missing keys
        )
        if patch_result.status == "resolved":
            # PATCH-Q3 (resolved): run all patch_transitions first, then check.
            # null inputs in pt.inputs resolve from state — do not overwrite state with null.
            for pt in patch_result.patch_transitions:
                resolved_inputs = {
                    k: (v if v is not None else state.get(k))
                    for k, v in pt.inputs.items()
                }
                tool_fn = TOOL_REGISTRY.get(pt.tool) or PATCH_TOOL_REGISTRY.get(pt.tool)
                outputs = tool_fn(resolved_inputs)
                state.update(outputs)
                execution_log.append(LogEntry(..., status="ok"))
            # Post-patch consistency check: all missing outputs must now be in state.
            still_missing = [k for k in missing if k not in state]
            if still_missing:
                return _fail(..., error="abort_and_heal",
                             detail=f"patch did not resolve: {still_missing}")
        else:
            # PATCH-Q5 (resolved): abort_and_heal is terminal this sprint — treat as failed.
            return _fail(..., error="abort_and_heal")
    else:
        return _fail(..., error="abort_and_heal", detail="no patch service configured")
```

**2. `PATCH_TOOL_REGISTRY`** — a second tool registry alongside `TOOL_REGISTRY`. Contains patching tools only. Never used during normal dispatch.

**3. `PatchClient`** — a new HTTP client alongside `Transition2ExecClient`. Uses the same `TRANSITION2EXEC_URL` — the patch endpoint is served by the same service. No separate URL configuration required.

---

## Patching Tools

Pure functions. No filesystem access. No side effects. Owned by the patch service; registered in `PATCH_TOOL_REGISTRY` in the executor.

| Tool            | Inputs                           | Outputs via `result_key` | Purpose                          |
|-----------------|----------------------------------|--------------------------|----------------------------------|
| `count_list`    | items: list, result_key: str     | result_key: int          | `["a","b","c"]` → `3`           |
| `get_first`     | items: list, result_key: str     | result_key: any          | `["a","b"]` → `"a"`             |
| `cast_int`      | value: str, result_key: str      | result_key: int          | `"42"` → `42`                   |
| `cast_float`    | value: str, result_key: str      | result_key: float        | `"3.14"` → `3.14`               |
| `cast_str`      | value: any, result_key: str      | result_key: str          | `42` → `"42"`                   |
| `split_lines`   | text: str, result_key: str       | result_key: list[str]    | `"a\nb"` → `["a","b"]`         |
| `join_list`     | items: list, sep: str, result_key: str | result_key: str    | `["a","b"]`, `","` → `"a,b"`   |
| `filter_suffix` | items: list, suffix: str, result_key: str | result_key: list| filter `.py` files from entries  |

The patch service selects the tool and sets `result_key` to the required abstract output name. The executor runs it without knowing why or what the key means.

---

## Decisions

| Decision             | Resolution                                                                                      |
|----------------------|-------------------------------------------------------------------------------------------------|
| Patch strategy       | Patch service owns entirely — patching tools preferred, available tools as fallback             |
| Output key alignment | Patch service sets `result_key` on patching tools; output keys match abstract outputs exactly   |
| Multi-step patch     | `patch_transitions` is a list — patch service may return multiple; executor runs in order       |
| Patch depth          | No recursion. If a patch transition produces another gap, executor aborts — no second call      |
| Patch service URL    | Same as `TRANSITION2EXEC_URL` — coexists with transition2exec on port 8001.                    |

---

## Resolved decisions

| Question                              | Decision                                                                                    |
|---------------------------------------|---------------------------------------------------------------------------------------------|
| Patch service location                | Coexists with transition2exec — same service, port 8001. No separate deployment.            |
| `available_tools` side effects        | Acceptable. The execution catalog already includes shell and file tools with side effects. No opt-in required. |
| Patch service URL                     | Uses `TRANSITION2EXEC_URL`. No separate `PATCH_URL` in `.env`.                             |
| Patching tool ownership               | Executor holds `PATCH_TOOL_REGISTRY` and runs them. Patch service selects them via the `patching_tools` catalog passed in the request. Same pattern as `TOOL_REGISTRY` / `available_tools`. |

---

## Open Issues — Pending Architect Resolution

### PATCH-Q1: Gap condition — partial vs total output miss
**Raised by:** transition2exec team
**Section:** Executor changes — post-abstract-transition gap check

The current code triggers the patch only when `not satisfied` (zero abstract outputs landed in state). If an abstract transition declares two outputs and only one lands, `satisfied` is non-empty and no patch is called — leaving the second output permanently missing.

**Question:** Should the patch trigger on ANY missing abstract output (`len(satisfied) < len(abstract_transition.outputs)`), not only when all are missing? If yes, the executor changes section needs to update the condition and the patch request should indicate which specific outputs are missing so the patch service can target them precisely.

### Architects reponse

TaskExecutor would call missing output - to find a reasonable solution along with the sequence of transtions 

---

### PATCH-Q2: Side effects before gap is detected (ISS-015 interaction)
**Raised by:** transition2exec team
**Section:** When this is called / Execution flow

Gap detection fires after the grounded tool runs. For a wrong-tool selection (e.g. `create_file` grounded for a `read_temp_file` abstract transition), the tool executes and writes a file before the gap is detected. The patch service returns `not_resolvable`. `abort_and_heal` fires. But the side effect (file created) already happened and is now in the filesystem.

**Question:** Does the DSTT Runtime heal service need to account for partial state mutations and side effects that occurred before `abort_and_heal`? Or is this an accepted risk — caller is responsible for idempotent task design? If side-effect rollback is required, a compensating transition registry may be needed.

**Related:** The transition2exec team's pre-dispatch output-overlap check (ISS-015) can catch obvious wrong-tool cases before execution. Consider whether both guards are needed — pre-dispatch for zero-overlap tools (no side effects), post-execution gap detection for compatible-but-different-shape outputs.

### Architects reponse

tool must assume side effects has occured as a result of the task being executed

---

### PATCH-Q3: "Another gap" in the no-recursion rule — when is it checked?
**Raised by:** transition2exec team
**Section:** Decisions — Patch depth

The spec states: "If a patch transition produces another gap, executor aborts — no second call." It is not clear when this check fires:

- **Option A:** After each individual `patch_transition` completes — if that single transition's outputs don't land, abort immediately.
- **Option B:** After all `patch_transitions` in the list complete — if abstract outputs are still not in state after the full patch sequence, abort.

Option A would break valid multi-step patch sequences where the first patch_transition produces an intermediate value consumed by the second. Option B is the safer interpretation.

**Question:** Please confirm Option B is the intended behaviour and update the executor pseudocode to reflect the check placement (after the `patch_transitions` loop, not inside it).

### Architects reponse

It is to be checked post the outcome , a consistency check is required by the implementer 

---

### PATCH-Q4: `filter_suffix` — source of suffix value
**Raised by:** transition2exec team
**Section:** Patching Tools

`filter_suffix` takes `suffix: str` as an input. For an abstract tool like `count_python_files`, the patch service must supply `suffix=".py"`. This value does not exist in state, in the abstract transition's declared inputs, or in the execution outcome.

**Question:** How does the patch service derive `.py`? Two candidate approaches:
1. **From task text** — patch service reads the `task` field and infers the suffix from natural language ("count Python files" → `.py`). This is LLM reasoning and may be unreliable for non-obvious suffixes.
2. **From abstract tool name convention** — `count_python_files` encodes `python` → `.py` via a lookup. Deterministic but requires a maintained mapping.

Please specify which approach is intended and whether the `patching_tools` catalog or the patch service's internal logic owns this mapping.

### Architects reponse

To be resolved , it is to be addressed by one of the transiton2exec or /patchTaskExecution if it is not. 

it would result in failure and future solution need to be explored

---

### PATCH-Q5: DSTT Runtime heal service — in scope for this sprint?
**Raised by:** transition2exec team
**Section:** Status semantics / Execution flow

`abort_and_heal` delegates to "DSTT Runtime repair service heals the abstract plan." This service is referenced but not specified. taskexecutor cannot be fully designed without knowing what `abort_and_heal` produces — does the caller receive a revised `abstract_dstt` to re-execute, a failure response, or something else?

**Question:** Is the DSTT Runtime heal service in scope for this sprint? If not, `abort_and_heal` should be treated as a terminal failure for now (same as `status: "failed"` in the current taskexecutor spec) and the heal path stubbed. Please confirm the interim behaviour so taskexecutor can proceed.

### Architects reponse
not in scope

---

### PATCH-Q6: Null inputs in `patch_transitions` — resolution from state
**Raised by:** transition2exec team
**Section:** Executor changes — post-abstract-transition gap check
**Evidence:** patch seeds P14, P15 (available_tool_fallback)

Patch seeds P14 and P15 show `patch_transitions` with explicit `null` input values — e.g.:
```json
{ "tool": "cast_int", "inputs": { "value": null, "result_key": "line_count" } }
```
The `null` indicates the value must be read from state at execution time (produced by a prior patch_transition or the original grounded tool). The original executor pseudocode used `state.update(pt.inputs)`, which would overwrite a valid state key with `null`, corrupting the value.

The updated pseudocode (see executor changes above) resolves this by skipping `null` inputs: for each `null` input, the executor reads the current state value rather than overwriting it. This is an implementer-side resolution.

**Question:** Is this the intended contract — `null` in `patch_transition.inputs` always means "read from state at dispatch time"? Or should the patch service always supply concrete values and `null` is a spec bug in P14/P15? Confirming the contract will lock the executor's null-resolution behaviour and the patch service's serialisation rules.

### Architects response

a smart llm would patch it to 0.  assume we will have a reviewer who reasons the execution. at every step along the way. 

---

### PATCH-Q7: Irreversible side effects before gap detection — heal service cannot restore lost artefacts
**Raised by:** transition2exec team
**Section:** When this is called / Execution flow
**Evidence:** patch seed P12 (`delete_file` before not_resolvable)
**Related:** PATCH-Q2 (side effects before gap detection — general case)

PATCH-Q2 covers the general case: architect confirmed that the tool must assume side effects have occurred. P12 introduces a sharper variant: the grounded tool is `delete_file`. The file is deleted, the gap is detected (deletion produces no output matching abstract outputs), the patch service returns `not_resolvable`, and `abort_and_heal` fires — but the file no longer exists. The DSTT Runtime heal service cannot recover it; it can at best revise the abstract plan for a future run, but the artefact is permanently gone.

PATCH-Q2's answer ("assume side effects occurred") is necessary but not sufficient here: the heal service needs to know that *the artefact it may depend on has been destroyed*, not merely modified.

**Question:** Is the DSTT Runtime heal service expected to receive information about which side effects occurred (e.g. which files were deleted) as part of the `abort_and_heal` payload, so it can make an informed decision about plan recovery? Or is the current design — heal service gets only the abstract plan, final state, and error code — accepted as sufficient, with irreversible data loss treated as a known risk of wrong-tool selection?

### Architects response

that is a n acceptable risk. and the execution is expected to happen in sandbox.  or with human approval.. once incorporated 