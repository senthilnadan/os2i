# OS2I Architecture Reference

## Purpose
Capture the distilled design for the Transition2Exec API without editing the `references/` sources. This document now serves as the architecture touchstone for future implementation work.

## Core Components
1. **API Layer** — FastAPI-style service exposing `POST /transition2exec`, `GET /health`, `GET /version`. It wraps a service that delegates to a DSPy backend and normalizes errors using shared response models.
2. **DSPy Planner Backend** — Mirrors Task2Plan's pattern:
   - `Transition2ExecBackend` interface with `model_name` + `generate_executable_dstt`.
   - Concrete backends (`Stub`, OpenAI, Ollama) that run a DSPy `Module` with separate reasoning + formatting LMs.
   - DSPy instructions force grounding to `grounded_tools.md`, enforce ≤3 transitions, chain validation, and `meta.status` semantics.
3. **Tool Catalog & Validation** — The execution payload must reference only tools listed in the catalog. Use the Pydantic schema (`ToolSignature` + `GroundedTool`) to validate tool names, signatures, and input/output matches before returning the DSTT.
4. **Context Resolver** — Each task feeds a resolved context (e.g., repository path, target file, language) so the DSPy program can concretely fill tool inputs; unresolved tasks use the clarification transition pattern from Task2Plan.
5. **Service Layer** — Handles status evaluation (ok/ambiguous/error), fallback clarity prompts, and wraps backend exceptions into structured `TaskResponse` objects aligned with `Task2Plan` models.

## Data Flow
- Client POSTs task/context/constraints.
- Service determines if clarification is needed; if yes, returns ambiguity DSTT referencing `getOrAskContextAndConstraints` + `task2Plan` (mirroring Task2Plan logic).
- If ready, backend generates an abstract DSTT, DSPy program maps to grounded tools, returns executable `segments` with `status`, `meta`, and diagnostics.
- Validator ensures tool names/signatures match catalog and `next.inputs ⊆ previous.outputs`.

## DSPy Instruction Highlights
- Provide the entire grounded tool catalog and a reminder that no new tool names or behaviors can be invented.
- Request JSON output with `status`, `segments`, and optional `meta.detail` explaining ambiguity or missing inputs.
- Emphasize determinism: same task/context must yield the same DSTT, unless context changes.

## Implementation Notes
- `references/` has been removed. This document is the sole architecture touchstone.
- Use the existing seed feed (`seed/batch_006_simple_tasks.jsonl`) to exercise the mapping pipeline before hooking into live DSPy.
- The `grounded_tools.md` catalog and example outputs should guide how transitions map to actual tools.
- Provide `training/run_batch.py` so the stub/LLM engines can replay seed batches during tuning and capture their executable DSTT outputs.
- Target model: qwen2.5:3b via local Ollama. Prompts are kept under 200 words with explicit JSON output format.
