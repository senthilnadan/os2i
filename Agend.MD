# OS2I Project Agenda

## Reference Usage
- `references/` has been removed. `architecture_reference.md` is the sole architecture touchstone.
- The two-stage flow (feasibility → executable mapping) is implemented; see design notes below.

## Objective
Build a deterministic, stateless compiler component that converts one abstract DSTT transition into executable tool-grounded transitions.

## Scope
- In scope: Single-transition compilation, tool-semantic mapping, decomposition (max 3 steps), chain validation, and a two-stage feasibility+transition flow that mirrors Task2Plan.
- Out of scope: Multi-step planning across transitions, execution of produced transitions, tool discovery/invention.

## Milestones
1. **Formalize Contract**
   - Finalize strict input/output schema for `task_intent_description`, `abstract_transition`, `available_tools`, and `context`.
   - Lock status semantics: `ok`, `needs_decomposition`, `not_mappable`.
2. **Implement Compiler Core**
   - Direct semantic tool match.
   - Fallback decomposition pipeline: `locate -> filter -> verify` (when applicable).
   - Enforce max expansion of 3 transitions.
3. **Add Guardrails & Validation**
   - Reject non-concrete inputs.
   - Reject abstract/unsupported verbs unless concretely mapped.
   - Validate chain integrity (`next.inputs ⊆ previous.outputs`).
4. **Determinism & Retry**
   - Deterministic tie-breaking rules for tool selection.
   - Optional single retry with stricter decomposition.
5. **Verification & Test Suite**
   - Unit tests for all status paths and constraints.
   - Golden tests for deterministic outputs on fixed inputs.

## Deliverables
- `os2i_spec.md` as normative spec.
- Compiler module (single-transition transform).
- Validation module for inputs, chaining, and guardrails.
- Test suite covering success/decomposition/failure paths.

## Acceptance Criteria
- Uses only tools from `available_tools`.
- Produces at most 3 executable transitions.
- Never guesses when mapping fails.
- Produces deterministic output for identical input.
- Final transition is verifiable when applicable.

## Immediate Task Queue
1. Define machine-readable JSON Schema for OS2I input/output.
2. Implement semantic tool-matching strategy and deterministic tie-break rules.
3. Implement decomposition path with strict atomic transitions.
4. Implement validators for concreteness, chain integrity, and forbidden abstract verbs.
5. Add tests for each rule in `README.md`/`os2i_spec.md`.

## Risks / Open Questions
- How strict should semantic matching be when multiple tools are near-equivalent?
- What exact format defines a "verifiable output" across tool categories?
- Should retry be enabled by default or controlled by caller?

## Design Notes (Qwen 3B)
- **Target model**: qwen2.5:3b via local Ollama (`http://localhost:11434/v1`).
- **Temperature**: 0.0 for determinism.
- **Prompt budget**: Both prompts kept under 200 words. JSON output format is explicit.
- **Objection on two-stage LLM**: Running feasibility via DSPy ChainOfThought then a second raw LM call doubles latency on a 3B model. The `ABSTRACT_TOOL_MAPPING` dict in `mapping.py` already provides a deterministic feasibility answer for all known abstract tools. Consider making feasibility purely heuristic and collapsing to a single prompt call if latency is a concern.
- **`instructions` kwarg removed**: The previous code passed a formatted template as `instructions=` to DSPy ChainOfThought — `instructions` is not a declared field on the signature and was silently dropped. Fixed by removing the kwarg and using the signature `__doc__` for guidance instead.

## Working Agreement
- Keep OS2I compiler-only (no execution side effects).
- Keep behavior deterministic and auditable.
- Prefer explicit failure over implicit inference.

## Reference Contract
- The Task2Plan microservice still produces an abstract (non-executable) DSTT with its own `meta.status` field that signals `ok | ambiguous | low_confidence | error`.
- We can reuse the Task2Plan guidance on returning valid JSON even on failure, and on signaling ambiguity by including clarification transitions before retrying.
- Task2Plan enforces strict reasoning steps (`intent → inputs/outputs → constraints → operations → transitions → finalize JSON`), which maps cleanly to OS2I's demand for concrete inputs, semantic tool matches, and chained outputs.
