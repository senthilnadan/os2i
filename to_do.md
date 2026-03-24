# OS2I Development To-Do

## Vision for this sprint
- Keep `references/` read-only and rely on `architecture_reference.md` as the live contract.  Use the provided `references/pyproject.toml` and `references/Makefile` as inspiration for dependency pins, dev commands, and run/test workflows (stubs + optional LM backends).
- Build a deterministic transition compiler that runs a DSPy-based feasibility check, grounds the abstract transition against `grounded_tools.md`, and produces at most three executable segments while staying aligned with the `Agend.MD`/`architecture_reference.md` guardrails.
- Capture training expectations (seed batch + qwen2.5-7b tuning) inside `training/run_batch.py` and keep the `prompts/` folder as the shared source of truth for instructions.

## Implementation tasks
1. **Contract solidification** – Confirm API models + validation rules match `os2i_spec.md` and ensure the HTTP surface (`/transition2exec`, `/health`, `/version`) mirrors the reference FastAPI structure.  Document how inputs, outputs, context, and statuses flow through the service.
2. **Service plus guardrails** – Keep `Transition2ExecService` responsible for ambiguity detection, meta.status mappings, and feeding the right backend (stub vs. DSPy).  Adjust the clarifier to remind callers about `getOrAskContextAndConstraints` and keep low-confidence logic aligned with the original heuristics.
3. **Two-stage DSPy backend** – Extend `transition.dspy_module` with a feasibility `ChainOfThought` that loads `prompts/feasibility_check.md`, enforces tool grounding, and either returns a `not_mappable` DSTT or delegates to the transition prompt (augmented with the feasibility summary + sequence) to produce JSON output.  Keep failure fallbacks, stub heuristics, and prompt templating externalized.
4. **Validation, mapping, and training** – Make `validation.py` enforce tool catalog signatures and chaining constraints; keep the simple `transition.mapping` helpers for the stub but note those are only for deterministic, seed-driven runs.  Flag the training path (`training/run_batch.py`) as the place to replay `seed/batch_006_simple_tasks.jsonl` with different backends (qwen2.5-7b via Ollama, stub, etc.).
5. **Tests and documentation** – Add lightweight tests that cover new parsing helpers (feasibility summary parsing, prompt generation) and re-run `pytest`.  Document the updated prompts/process in `README.md`/`Agend.MD`/`architecture_reference.md` as needed.

## Known issues to fix upstream

- **`getOrAskContextAndConstraints` tasks (08/09/10/14)**: Tasks that are genuinely ambiguous are correctly flagged upstream by `/task2plan` as `ambiguous` status. However the 4 seed tasks that map to `getOrAskContextAndConstraints` should be treated as expected `not_mappable` in `transition2exec` — the pipeline should not attempt tool resolution for these. Currently they produce validation errors. The fix belongs upstream: either filter them before calling `transition2exec`, or handle the abstract tool name explicitly as a pass-through.

- **Validator chain check for constant inputs**: `validation.py` line 30 rejects inputs in t2+ that aren't in prior outputs or context keys. This is correct for dynamic bindings but too strict for constants like `working_directory` which are resolvable from context via `resolve_input` but not a direct context key. The validator should also accept inputs whose values can be resolved via `resolve_input`.

## Immediate checklist
- [ ] Refresh `Agend.MD` so it reiterates the no-references rule and captures the two-stage process plus tooling mindset.
- [ ] Wire the new DSPy feasibility + prompt logic in `src/transition2exec/transition/dspy_module.py` and update `prompts/transition2exec_prompt.md` to accept the feasibility placeholders.
- [ ] Extend or add tests that exercise the new helpers, especially the feasibility-output parser.
- [ ] Run `pytest` from the root and note the result.
- [ ] Capture any new training seeds/results (e.g., qwen2.5-7b) using `training/run_batch.py` once the backend is stable.
