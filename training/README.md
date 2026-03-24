# Training Workflow for Transition2Exec

Use this folder to explore how the stub backend (and future LLM-based backends) handle batched inputs from `seed/batch_006_simple_tasks.jsonl`. The script below replays each task, feeds the abstract transition + available tool catalog into the service, and logs the resulting executable DSTT. This lets you tune prompts and compare stub vs. LLM executions without deploying the full API.

## Workflow
1. Activate the virtual environment: `source .venv/bin/activate`.
2. Run a batch: `python training/run_batch.py --seed seed/qwen_seed.jsonl --output training/results_qwen_3b_run01.jsonl`
3. Edit the context/constraints in the script if you need per-task overrides.
4. Switch backends via `.env`: `TRANSITION2EXEC_BACKEND=qwen` (default) or `stub`.

## Notes
- The stub backend already maps abstract transition names to the grounded tool catalog and returns deterministic outputs. Use this as your baseline before tuning prompts for real LLMs.
- You can also replay the Qwen-focused seed (`seed/qwen_seed.jsonl`) to capture how the actual backend behaves on a minimal test set (because Qwen has limited context about the repo, so start small).
- The script dumps each executable DSTT so you can compare the emitted actions against your expectations.

---

## Run 01 — qwen2.5:3b — `results_qwen_3b_run01.jsonl`

Seed: `seed/qwen_seed.jsonl` (3 tasks). Single-prompt mode (no feasibility stage).

### Task 1 — "Check whether hello.py exists in the project folder."

| | |
|---|---|
| Abstract tool | `check_python_file_existence` |
| Expected grounded tool | `exists` with `file_path` → `is_present` |
| Got | `exists` with `file_path: ".../hello.py"` → `is_present: false` |
| Source | **stub fallback** (Qwen's raw output failed to parse) |
| Pass? | ✅ correct tool and inputs — but came from stub, not Qwen |

**Note:** Qwen produced output that failed `json.loads` extraction. The stub rescued it and produced the right answer. We need to check whether Qwen is wrapping output in extra prose or producing malformed JSON.

---

### Task 2 — "List every file in the current project folder."

| | |
|---|---|
| Abstract tool | `list_files_in_directory` |
| Expected grounded tool | `list_directory_recursive` with `directory_path` → `entries` |
| Got | `list_directory_recursive` with `directory_path: ".../os2i"` → `entries: "file_list"` |
| Source | **Qwen** (parsed successfully, context is null) |
| Pass? | ⚠️ tool and inputs correct, but output value is wrong |

**Issue:** Qwen set `"entries": "file_list"` — it used the expected output key name as the value. This is a prompt confusion: the example format `{"<k>":"<v>"}` in the prompt is being interpreted literally. Qwen 3B needs a concrete example of what a real output value looks like (e.g. `{"entries": []}`).

---

### Task 3 — "Read the contents of hello.py."

| | |
|---|---|
| Abstract tool | `read_python_file` |
| Expected grounded tool | `read_file` with `file_path` → `text` |
| Got | `not_mappable` |
| Source | **Qwen** (parsed successfully, status=not_mappable) |
| Pass? | ❌ Qwen refused to map `read_python_file` → `read_file` |

**Issue:** Qwen 3B could not infer that `read_python_file` should map to `read_file`. The prompt gives Qwen the available tools list but no hint about the mapping. Qwen 3B doesn't generalise well across synonymous names without a nudge.

---

### Prompt issues identified

1. **Output value confusion** — The `{"<k>":"<v>"}` example in the prompt causes Qwen to treat key names as values. Fix: show a concrete output example or add a rule: _"output values must be the tool's actual return type defaults (e.g. empty list, false, empty string), not the key name."_
2. **Abstract→grounded name gap** — Qwen 3B cannot reliably bridge abstract names (e.g. `read_python_file`) to grounded names (e.g. `read_file`) without explicit guidance. Fix: either include the mapping as a hint in the prompt, or add a brief note that the abstract tool name is a semantic description, not a literal tool name.
3. **JSON parse failures** — At least one response (Task 1) failed to parse. Qwen 3B sometimes wraps output in prose or adds a preamble. The `_normalize_output` stripper handles code fences but may not handle all cases.

### Next prompt iteration

Candidate changes for Run 02:
- Add a rule: _"Use the closest matching tool name from available_tools — the abstract tool name is a description, not a literal name."_
- Change the output example to use real defaults: `{"entries":[],"text":"","is_present":false}`.
- Add: _"Output values must be default/empty — never copy a key name as a value."_
