# OS2I Issues

## Response to TaskExecutor Team — transition2exec Contract and Runtime Expectations

_Date: 2026-03-22 | v1.0 baseline: 12/17 field test seeds passing_
_Updated: 2026-03-28 | v1.1 stable: 14/16 downstream seeds passing — v1.1 architecture shipped_

### v1.1 Architecture (stable as of 2026-03-28)

- **Stage 1 (LLM):** tool selection + key bindings only. Prompt shows state key names, never values. Output: `TOOL: <name>` + `BIND: input_key <- state_key`.
- **Stage 1.5 (program):** value resolution — looks up each BIND key in state, falls back to direct state match, then `extract_from_task` (narrow LLM call), then marks ambiguous.
- **Stage 2 (eliminated):** `ExecutableTransition` constructed directly in Python. No LLM formatter.

**What this eliminates structurally:** silent value substitution (ISS-018 class) — LLM never touches state values, so it cannot corrupt them.

**Known open gaps:** ISS-017 (count/search → list instead of shell), ISS-019 (tool-selection regression for t2+ without context). Both surface as detectable failures, not silent wrong values.

---

### What transition2exec HONOURS (guaranteed)

1. **Grounded tool only.**
   Every executable transition references a tool that exists in the `available_tools` catalog supplied by the caller. We never hallucinate tool names.

2. **Inputs resolved from state.**
   Input values are drawn from context (state). If a value is not in state, it is synthesised from the task description. If it cannot be derived from either, it is emitted as `""`.

3. **Outputs are null slots.**
   Output keys match the grounded tool's signature and are set to `null`. taskexecutor fills them by running the tool.

4. **Status semantics.**
   - `ok` — grounded executable transition produced; tool is from the catalog.
   - `not_mappable` — no catalog tool matched the abstract transition.
   - `ambiguous` — task is underspecified; caller should provide more context.

5. **One transition at a time.**
   transition2exec maps exactly one abstract transition per call. It has no knowledge of prior or future transitions beyond what is in the current state.

---

### What transition2exec CANNOT honour (known gaps — design taskexecutor accordingly)

6. **Not a single canonical tool.**
   When multiple catalog tools can solve the same problem, either may be selected. Example: `write_stdout_to_file` may resolve to `create_file` or `run_shell_command` depending on context. **taskexecutor must accept any catalog tool that can produce the required output type — do not hard-code expected tool names.**

7. **Not exact command strings for `run_shell_command`.**
   The synthesised command is best-effort. Functional variants are expected:
   - Absolute path vs relative `.` with `working_directory`
   - `python` vs `python3`
   - Equivalent flag ordering
   **taskexecutor must surface `return_code != 0` as a recoverable interface mismatch, not a fatal failure.**

8. **Not reliable tool selection for count/search abstract tools (ISS-017).**
   Abstract tools like `count_python_files` or `find_files_with_import` may resolve to `list_directory_recursive` instead of `run_shell_command`. Both are in the catalog. The list-based approach is functional but slower.
   **taskexecutor should treat this as a valid (if suboptimal) grounding. The output type (`entries` vs `stdout`) will differ — state merge must be tolerant of output key name mismatches.**

9. **Not guaranteed correct tool for t2+ transitions when context is ambiguous (ISS-015).**
   When prior step outputs remain in state (e.g. `content: "hello"` from a create step), stage 1 may pick the tool that consumes those inputs rather than the tool that produces the required outputs. Example: `read_temp_file` resolves to `create_file` instead of `read_file`.
   **This is a genuine wrong-tool failure. The selected tool cannot produce `file_contents`. taskexecutor SHOULD detect this pre-dispatch: if the grounded tool's output keys have zero overlap with the abstract transition's `outputs`, fail immediately with status `tool_output_mismatch` and do not run the tool.**

10. **Empty string inputs are not failures.**
    `""` on an input means the value was not resolvable at grounding time. It is not an error from transition2exec's perspective.
    **taskexecutor should fail the transition with a clear `missing_input` error if the tool cannot proceed with an empty value, so the gap is traceable back to the abstract plan.**

---

### Design checklist for taskexecutor

| Scenario | taskexecutor behaviour |
|----------|----------------------|
| `return_code != 0` from `run_shell_command` | Surface error, allow retry with corrected command |
| Tool output keys differ from abstract transition outputs | Map by grounded tool schema, not by key name equality |
| Grounded tool output keys have zero overlap with abstract outputs | Fail pre-dispatch with `tool_output_mismatch` |
| Input value is `""` | Fail with `missing_input`, log which key |
| `status: not_mappable` from transition2exec | Fail transition, do not attempt dispatch |
| `status: ambiguous` from transition2exec | Surface to caller for context clarification |

---

## Issue Log

### ISS-001 — `shell` missing from `run_shell_command` catalog
**Status:** Fixed
Field test seed defines 3 inputs for `run_shell_command`: `command`, `working_directory`, `shell`. Catalog only had 2. Added `shell` to `DEFAULT_TOOLS`.

---

### ISS-002 — Batch runner did not handle top-level `available_tools`
**Status:** Fixed
Field test seed defines tools once at the top level, not per-entry. Batch runner now parses both JSON-with-seeds-array and JSONL formats, inheriting shared tools. Also added `expected` field validation (PASS/MISMATCH/FAIL verdict per seed).

---

### ISS-003 — Synthesise inputs from task when absent from state
**Status:** Fixed
Contract defined and prompt updated: if a required input has no state value, derive from task description; if task gives no value, emit `""`. Covers seeds 06, 12a, 15, 10a, 10b.

---

### ISS-004 — `content: ""` for create_file with no content in context
**Status:** Closed — covered by ISS-003

---

### ISS-005 — Type info not captured in GroundedTool model
**Status:** Open (P3 — low priority)
Seed tool definitions include `"type": "str"` on inputs/outputs. Our model ignores these. No impact on current pipeline. Useful for future runtime validation.

---

### ISS-006 — No strict expected validation in batch runner
**Status:** Fixed
Batch runner now reports PASS / MISMATCH (WRONG_TOOL, WRONG_INPUT) / FAIL per seed with full verdict.

---

### ISS-007 — Stage 1 planned the whole task instead of one transition
**Status:** Fixed
Prompt restructured: tool selection driven by `abstract_tool` + `required_outputs` only. Task text demoted to "value hint only". Over-generation resolved for 09b, 11a, 11b, 12a.

---

### ISS-008 — Stage 2 produced malformed JSON for run_shell_command
**Status:** Fixed
Root cause: stage 2 was a formatting LLM that had to fill blanks — it split transitions when values were empty. Fixed by making stage 1 + Python pre-fill all input values before stage 2. Stage 2 now just copies pre-populated templates.

---

### ISS-009 — `not_mappable` for trivial run_shell_command
**Status:** Fixed
Root cause: `working_directory` was required by seed tool signature but not emitted by stage 1. Fixed by merging stage 1 synthesised values into the resolved_tools template in Python (`_extract_resolved_tools`). Empty string kept as key rather than dropped.

---

### ISS-010 — Absolute vs relative path in shell commands
**Status:** Closed — best effort, runtime resolves
Model uses absolute paths; expected uses `.` relative to `working_directory`. Functionally equivalent. taskexecutor surfaces `return_code != 0` as recoverable mismatch.

---

### ISS-011 — Wrong tool for t2+ transitions
**Status:** Partially fixed
Fixed by: (a) Python output-match selection in `_extract_resolved_tools` — picks grounded tool whose name tokens overlap with abstract outputs; (b) stage 1 prompt restructure reducing task-driven planning.
- 11b: Fixed ✓
- 09b: Open (ISS-015)
- 12b: Closed as valid alternative (ISS-016)

---

### ISS-012 — Shell metacharacters broke stage 2 JSON parsing
**Status:** Fixed
Root cause: stage 2 was an LLM formatter that reinterpreted command strings. Fixed by moving all value resolution into Python before stage 2. Stage 2 copies verbatim.

---

### ISS-013 — Semantically equivalent command/content variants
**Status:** Closed — best effort, runtime resolves
`python` vs `python3`, `"line1"` vs `"line1\n"` — interface variants. Pipeline produces valid transitions. Runtime detects if the specific form fails.

---

### ISS-014 — `list_directory` vs `list_directory_recursive`
**Status:** Fixed
Required_outputs-driven selection and tool description improvement resolved this.

---

### ISS-015 — Wrong tool for read transition (seed 09b) — taskexecutor must guard
**Status:** Open — genuine wrong-tool failure, training data target
`read_temp_file` → stage 1 picks `create_file` instead of `read_file`. `create_file` cannot produce `file_contents`. This will fail at runtime with a type mismatch.
**taskexecutor action required:** before dispatching any tool, check that the grounded tool's output keys have at least one overlap with the abstract transition's `outputs`. If zero overlap → fail with `tool_output_mismatch`, do not run the tool.
Training fix: add `read_temp_file → read_file` as a labelled seed example.

---

### ISS-016 — Alternative tool for write transition (seed 12b)
**Status:** Closed — valid alternative
`write_stdout_to_file` → `run_shell_command` (via shell redirection). Both tools can write content to a file. Pipeline did not hallucinate. taskexecutor must tolerate output key name differences between the grounded tool and the abstract transition.

---

### ISS-018 — Input value resolved to wrong state key — outputs key used as value (seed ld_04) — P1
**Status:** Open — top priority
`inspect_directory` → `list_directory` tool selected correctly, but `directory_path` input is resolved to `"entries"` (the abstract transition's output key name) instead of `"/tmp/os2ie_sandbox/target"` (the state value for `directory_path`).
**Root cause hypothesis:** During state resolution, the model confuses the abstract transition's output key names with input values. It appears to scan the abstract transition outputs list and use those as values rather than looking up the input key in state/context.
**Reproduction:**
- Task: "Inspect the target directory and list what is inside it"
- State: `{ "directory_path": "/tmp/os2ie_sandbox/target" }`
- Abstract transition inputs: `["directory_path"]`, outputs: `["entries"]`
- Expected: `{ "directory_path": "/tmp/os2ie_sandbox/target" }`
- Actual: `{ "directory_path": "entries" }`

**Fix required:** State resolution must look up each input key in context and return its value. Abstract transition output keys must never be used as input values.

**Deeper diagnosis — stage 2 is the actual failure point:**
Python's `_extract_resolved_tools` correctly overrides stage 1's wrong value: `resolve_input("directory_path", context)` returns `"/tmp/os2ie_sandbox/target"` from state. The template passed to stage 2 is therefore correct. Stage 2 then re-introduces the wrong value despite being told to copy verbatim.

Materialized stage 2 prompt for seed ld_04 (the input the LLM receives — note the correct path is present):

```
Convert these resolved tool templates into an executable DSTT JSON.

resolved_tools (each entry is a fully-populated transition template — all values already resolved):
list_directory: {"id": "t?", "tool": "list_directory", "inputs": {"directory_path": "/tmp/os2ie_sandbox/target"}, "outputs": {"entries": null}}

Rules:
- Copy each tool's template exactly. Replace "t?" with sequential ids starting at t1, t2, etc.
- inputs: copy values exactly as given. Do not add, remove, or change any keys or values.
- outputs: all values must be null.
- milestone: list of output key names from the last transition's outputs.
- Only include tools from resolved_tools. No extra tools, no extra keys.
- Each tool produces exactly ONE transition object with id, tool, inputs, and outputs together. Never split a transition.
- If resolved_tools is "(none matched)" respond with: {"status":"not_mappable","segments":[]}

Respond with ONLY valid JSON, no extra text:
{"status":"ok","segments":[{"transitions":[{"id":"t1","tool":"<name>","inputs":{"<key>":"<value>"},"outputs":{"<key>":null}}],"milestone":["<output_key>"]}]}
```

Stage 2 LLM response (wrong — model ignores the correct value in the template):
```json
{"status":"ok","segments":[{"transitions":[{"id":"t1","tool":"list_directory","inputs":{"directory_path":"entries"},"outputs":{"entries":null}}],"milestone":["entries"]}]}
```

The model receives `"directory_path": "/tmp/os2ie_sandbox/target"` in the template but outputs `"directory_path": "entries"`. It is associating the output key name `entries` with the input value — an instruction-following failure in smaller models (qwen2.5:3b). The 7b model does not exhibit this on the same prompt.

**Revised fix (v1.1 architecture):** Adopt the programmatic transition construction pipeline:
- Stage 1 (LLM): tool selection + key binding only — LLM never sees state values, only key names
- Stage 1.5 (program): value resolution using bindings against state
- Stage 2: eliminated — `ExecutableTransition` constructed directly in Python

Resolution algorithm (stage 1.5):
```
for input_key in tool.input_signature:
    bind_key = BIND.get(input_key, input_key)    # default: same key name
    if bind_key in state:
        inputs[input_key] = state[bind_key]       # exact copy from state
    elif input_key in state:
        inputs[input_key] = state[input_key]      # direct state match fallback
    else:
        result = extract_from_task(input_key, task)
        if result is None or result == "" or result == input_key:
            mark ambiguous                         # key echo = same failure mode, explicit not a guess
        else:
            inputs[input_key] = result
```

**Open decision — `extract_from_task` null contract:**
The narrow extract LLM call must define what "nothing found" means. Defined as: returns `None` when the LLM returns empty string, null, or a value identical to the input key name (key echo — e.g. `directory_path="directory_path"`). Key echo is the same silent substitution failure seen in ISS-018, just from the extraction path. The extract call must NOT have an "always returns something" guarantee. This contract needs to be locked before the extract call is implemented.

---

### ISS-019 — v1.1 stage 1 tool-selection regression from removing context (seeds 10a, 11b)
**Status:** Open — known trade-off of v1.1 architecture
Removing context from stage 1 improves value-resolution reliability (eliminates silent substitution class) but reduces tool-selection quality for ambiguous tasks.

- **10a**: task "create log.txt, append line1, append line2" → stage 1 plans two `append_to_file` transitions instead of `create_file` for t1. Without context, the model over-plans from task text.
- **11b**: stage 1 hallucinates `create_file_in_directory` (not in catalog) instead of grounding to `create_file`. Context presence in v1.0 reduced hallucination rate.

**Trade-off accepted:** v1.1 eliminates the silent value-substitution failure class (ISS-018) structurally. Tool-selection regressions surface as `not_mappable` or wrong-tool — both are detectable and recoverable by the runtime. Silent wrong-value propagation (v1.0 failure mode) is not.

**Baseline:** v1.0 12/17 seeds → v1.1 10/17 seeds. Net: −2 on tool selection, +structural guarantee on value resolution.

**Possible fix:** Training data with `create_log_file → create_file` and `create_file_in_directory → create_file` examples would close this gap without reintroducing state values into stage 1.

---

### ISS-017 — Count/search abstract tools resolve to list_directory instead of run_shell_command (seeds 07, 08)
**Status:** Open — best effort, taskexecutor must handle output type mismatch
`count_python_files` → `list_directory_recursive` (outputs: `entries`). Expected: `run_shell_command` (outputs: `stdout`). The list-based approach is in the catalog and functional but produces a different output type.
**taskexecutor action required:** abstract transition output `python_file_count` (int) will not be directly in state — `entries` (list) will be. The kernel must be tolerant of grounded output key names differing from abstract output names. Map grounded outputs into state by grounded key name, then let the next transition consume whatever is available.
**Training fix:** add `count_python_files → run_shell_command` and `find_files_with_import → run_shell_command` as labelled seed examples. The `run_shell_command` preference for count/search should be in training data, not hard-coded in prompts.
